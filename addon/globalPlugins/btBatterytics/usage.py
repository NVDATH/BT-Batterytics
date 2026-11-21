"""The record of how long each device is used between two recharges (UsageTracker)."""

from __future__ import annotations


import json
import shutil
import statistics
import threading
import time
from datetime import datetime
import os
import logHandler
import config
import globalVars

from .bluetooth import CONNECTION_CONNECTED, CONNECTION_DISCONNECTED


log = logHandler.log


# Usage tracking (connected time between two recharges)
_USAGE_FILE_NAME = "btBatterytics_usage.json"
# The names used before the add-on was renamed: the data and the settings under them are taken over.
_LEGACY_USAGE_FILE_NAME = "blueToothBatteryReport_usage.json"
# Gaps between two observations longer than this are not counted (PC asleep, NVDA closed, ...)
_USAGE_MAX_GAP_SECONDS = 15 * 60
# The device counts as recharged when its battery is at least this many points above the
# lowest level seen in the current cycle (works for devices that never reach 100%)
_USAGE_RECHARGE_RISE = 15
# A finished cycle shorter than this is not stored as "last cycle" (e.g. steps seen while charging)
_USAGE_MIN_CYCLE_SECONDS = 30 * 60

# Charging case of true wireless earbuds. Windows does not report the battery of the case, so the number of
# times the case has charged the earbuds is estimated from the battery points the earbuds gained at each
# recharge (100 points are one charge).
# Finished rounds of the case (from one "case charged" to the next) that are remembered
_CASE_MAX_ROUNDS = 20
# A finished round in which the case charged the earbuds fewer times than this is not used for learning
_CASE_ROUND_MIN_USED = 1.0
# The typical size of the case is learned from the latest rounds, once there are enough of them
_CASE_LEARN_MIN_ROUNDS = 3
_CASE_LEARN_LATEST = 5
# Alert when the case is estimated to have fewer charges left than this (default)
_CASE_DEFAULT_ALERT_LEFT = 1.0
# The columns of the summary list about the case
_CASE_COLUMNS = ("case_used", "case_left")


def _case_defaults() -> dict:
	"""The charging case fields of a device that has none yet."""
	return {
		"case_enabled": False,
		"case_hours": None,
		"case_total": None,
		"case_alert": _CASE_DEFAULT_ALERT_LEFT,
		"case_used": 0.0,
		"case_rounds": [],
		# The alert was given and the earbuds were not recharged since, then the earbuds were recharged: ask the user
		"case_pending": False,
		"case_ask": False,
	}


class UsageTracker:
	"""Measures how long each device is connected between two recharges.

	Counting starts the first time a device is seen (at any battery level). Only time during
	which the device was observed as not disconnected is counted, and it is kept (persisted as
	JSON in NVDA's config folder) even while the device is disconnected or NVDA is restarted.
	Gaps longer than _USAGE_MAX_GAP_SECONDS between two observations are skipped, so PC sleep
	does not inflate the result.

	A recharge is detected when the battery is at least _USAGE_RECHARGE_RISE points above the
	lowest level seen in the current cycle. The finished cycle is stored in the history and
	counting restarts from zero. Time is not added while the battery level is rising (device charging).

	For classic devices Windows reports how long the current connection has lasted. The counted
	total is never smaller than that (within the current cycle), so a device that was already
	connected for hours when first seen is not under-reported. LE devices have no such value:
	their total only covers the time this add-on has observed.

	Devices are identified by their key (the Bluetooth address), so two devices with the same name
	do not share data and a renamed device keeps its data. The first versions used the name as the
	key: such data moves to the key of the device with that name the first time it is seen.

	Per device (keyed by device key):
		name          - the name Windows gave the device when it was last seen
		alias         - a name chosen by the user, shown instead of the name (or None)
		ignored       - True if the connection time of the device is not measured
		alert         - low battery alert level in percent, 0 for no alert, None for the default level
		drop_alert    - True if the user wants an alert each time the battery level of the device drops
		connect_alert - True if the user wants an alert when the device connects
		disconnect_alert - True if the user wants an alert when the device disconnects
		active        - connected seconds counted in the current cycle
		level         - battery level at the previous observation
		min_level     - lowest battery level seen in the current cycle
		start_level   - battery level when the current cycle started
		history       - finished cycles, oldest first: {"end": epoch, "secs": connected seconds,
						"from": battery level at start, "to": lowest battery level}
		cycle_start   - epoch time when the current cycle started (may precede the first observation)
		last_seen     - epoch time of the previous observation while connected
	"""

	# The running instance, so the settings panel can show its statistics.
	current: UsageTracker | None = None

	def __init__(self):
		UsageTracker.current = self
		self._lock = threading.Lock()
		self._path = os.path.join(globalVars.appArgs.configPath, _USAGE_FILE_NAME)
		self._take_over_legacy_file()
		self._data: dict[str, dict] = self._load()
		# Connection status (sort rank) of every device in the latest scan, for the order of the statistics.
		self._ranks: dict[str, int] = {}
		self.prune_history()

	def _take_over_legacy_file(self) -> None:
		"""Copy, once, the data saved under the former name of the add-on. The old file is left as it is."""
		legacy_path = os.path.join(os.path.dirname(self._path), _LEGACY_USAGE_FILE_NAME)
		if not os.path.exists(self._path) and os.path.exists(legacy_path):
			try:
				shutil.copy2(legacy_path, self._path)
			except OSError:
				log.exception("BT-Batterytics: could not take over the data saved under the former name")

	@staticmethod
	def _optional_number(value, cast):
		return cast(value) if value is not None else None

	@staticmethod
	def _load_case(entry: dict) -> dict:
		"""The charging case fields of a saved entry. Entries of earlier versions have none."""
		case = _case_defaults()
		case["case_enabled"] = bool(entry.get("case_enabled", False))
		case["case_pending"] = bool(entry.get("case_pending", False))
		case["case_ask"] = bool(entry.get("case_ask", False))
		for name in ("case_hours", "case_total"):
			value = entry.get(name)
			if isinstance(value, (int, float)) and value > 0:
				case[name] = float(value)
		alert = entry.get("case_alert")
		if isinstance(alert, (int, float)) and alert > 0:
			case["case_alert"] = float(alert)
		used = entry.get("case_used")
		if isinstance(used, (int, float)) and used > 0:
			case["case_used"] = float(used)
		rounds = entry.get("case_rounds")
		if isinstance(rounds, list):
			case["case_rounds"] = [
				float(value) for value in rounds if isinstance(value, (int, float)) and value > 0
			][-_CASE_MAX_ROUNDS:]
		return case

	def _load(self) -> dict[str, dict]:
		try:
			with open(self._path, "r", encoding="utf-8") as f:
				data = json.load(f)
			if isinstance(data, dict):
				cleaned: dict[str, dict] = {}
				for key, entry in data.items():
					if isinstance(entry, dict):
						history = []
						for record in entry.get("history") or []:
							if isinstance(record, dict) and record.get("secs") is not None:
								history.append(
									{
										"end": self._optional_number(record.get("end"), float),
										"secs": float(record["secs"]),
										"from": self._optional_number(record.get("from"), int),
										"to": self._optional_number(record.get("to"), int),
										"pos": self._optional_number(record.get("pos"), float),
										"elapsed": bool(record.get("elapsed", False)),
									},
								)
						if not history and entry.get("last") is not None:
							# Written before the history existed: keep its last finished cycle.
							history.append(
								{
									"end": None,
									"secs": float(entry["last"]),
									"from": self._optional_number(entry.get("last_from"), int),
									"to": None,
								},
							)
						# Cycles saved before the manual order existed: the newest first.
						for index, record in enumerate(history):
							if record.get("pos") is None:
								record["pos"] = -float(index)
						# Entries written by earlier versions lack some fields;
						# they are filled in at the next observation. Without a name, the key is the name.
						cleaned[key] = {
							"name": entry.get("name") or None,
							"alias": entry.get("alias") or None,
							"ignored": bool(entry.get("ignored", False)),
							"alert": self._optional_number(entry.get("alert"), int),
							"drop_alert": bool(entry.get("drop_alert", False)),
							"connect_alert": bool(entry.get("connect_alert", False)),
							"disconnect_alert": bool(entry.get("disconnect_alert", False)),
							"active": float(entry.get("active") or 0.0),
							"level": self._optional_number(entry.get("level"), int),
							"min_level": self._optional_number(entry.get("min_level"), int),
							"start_level": self._optional_number(entry.get("start_level"), int),
							"cycle_start": self._optional_number(entry.get("cycle_start"), float),
							"history": history,
							"last_seen": self._optional_number(entry.get("last_seen"), float),
							**self._load_case(entry),
							"order": self._optional_number(entry.get("order"), float),
							"elapsed": bool(entry.get("elapsed", False)),
							"last_obs": self._optional_number(entry.get("last_obs"), float),
							"charge_at": min(
								max(self._optional_number(entry.get("charge_at"), int) or 0, 0),
								95,
							),
						}
				return cleaned
		except FileNotFoundError:
			pass
		except Exception:
			log.exception("BT-Batterytics: failed to load usage data")
		return {}

	def _save(self):
		tmp_path = self._path + ".tmp"
		try:
			with open(tmp_path, "w", encoding="utf-8") as f:
				json.dump(self._data, f, ensure_ascii=False, indent=1)
			os.replace(tmp_path, self._path)
		except Exception:
			log.exception("BT-Batterytics: failed to save usage data")

	def _next_top_order(self) -> float:
		"""The manual position of a device that is seen for the first time: before all the others."""
		orders = [entry["order"] for entry in self._data.values() if entry.get("order") is not None]
		return min(orders) - 1 if orders else 0.0

	def _entry_for(self, device):
		"""The entry of a device, or None. Data of the first versions, keyed by name, moves to the key."""
		entry = self._data.get(device.key)
		if entry is None:
			legacy = self._data.get(device.name)
			if legacy is not None and legacy["name"] is None and device.name != device.key:
				entry = self._data[device.key] = self._data.pop(device.name)
		return entry

	def _prune_locked(self, now: float) -> bool:
		"""Drop the oldest finished cycles beyond the limits of the settings. Return whether any was dropped."""
		section = config.conf["btBatterytics"]
		max_cycles = section["historyMaxCycles"]
		max_days = section["historyMaxDays"]
		cutoff = now - max_days * 86400 if max_days else None
		changed = False
		for entry in self._data.values():
			history = entry["history"]
			kept = [r for r in history if cutoff is None or r["end"] is None or r["end"] >= cutoff]
			kept = kept[-max_cycles:]
			if len(kept) != len(history):
				entry["history"] = kept
				changed = True
		return changed

	def prune_history(self) -> None:
		"""Apply the limits of the settings to the stored cycles."""
		with self._lock:
			if self._prune_locked(time.time()):
				self._save()

	def update(self, results, now: float | None = None, count: bool = True):
		"""Feed one scan (the output of collect_bluetooth_battery) into the tracker.

		With count False, devices are only made known (so their alerts can be chosen): no time is counted.
		"""
		now = time.time() if now is None else now
		changed = False
		with self._lock:
			for device in results:
				battery = device.battery
				entry = self._entry_for(device)
				if entry is not None and entry["name"] != device.name:
					entry["name"] = device.name
					changed = True
				if not count:
					if entry is None:
						self._data[device.key] = {
							"name": device.name,
							"alias": None,
							"ignored": False,
							"alert": None,
							"drop_alert": False,
							"connect_alert": False,
							"disconnect_alert": False,
							"active": 0.0,
							"level": battery,
							"min_level": battery,
							"start_level": battery,
							"cycle_start": None,
							"history": [],
							"last_seen": None,
							**_case_defaults(),
							"order": self._next_top_order(),
							"elapsed": False,
							"last_obs": None,
							"charge_at": 0,
						}
						changed = True
					continue
				if entry is not None and entry["ignored"]:
					# Not measured: no time is counted and the connection is not continuous.
					if entry["last_seen"] is not None:
						entry["last_seen"] = None
						changed = True
					continue
				if device.sort_rank == CONNECTION_DISCONNECTED:
					# The connection is over; the counted time is kept.
					if entry is not None and entry["last_seen"] is not None:
						entry["last_seen"] = None
						changed = True
					continue

				# How long Windows says the current connection has lasted (classic devices only).
				connection_secs = None
				if (
					device.sort_rank == CONNECTION_CONNECTED
					and device.last_used is not None
					and not (entry is not None and entry["elapsed"])
				):
					secs = (datetime.fromtimestamp(now) - device.last_used).total_seconds()
					if 0 < secs < 86400 * 7:
						connection_secs = secs

				if entry is None:
					# First time this device is seen: start counting from here, whatever its level.
					self._data[device.key] = {
						"name": device.name,
						"alias": None,
						"ignored": False,
						"alert": None,
						"drop_alert": False,
						"connect_alert": False,
						"disconnect_alert": False,
						"active": connection_secs or 0.0,
						"level": battery,
						"min_level": battery,
						"start_level": battery,
						"cycle_start": now - (connection_secs or 0.0),
						"history": [],
						"last_seen": now,
						**_case_defaults(),
						"order": self._next_top_order(),
						"elapsed": False,
						"last_obs": now,
						"charge_at": 0,
					}
					changed = True
					continue

				before = dict(entry)
				last_seen = entry["last_seen"]
				continuous = last_seen is not None and 0 <= now - last_seen <= _USAGE_MAX_GAP_SECONDS
				delta = now - last_seen if continuous else 0.0
				entry["last_seen"] = now

				if entry["min_level"] is None:
					entry["min_level"] = entry["start_level"] = battery
				if entry["level"] is None:
					entry["level"] = battery
				if battery >= entry["min_level"] + _USAGE_RECHARGE_RISE:
					# Clearly higher than the lowest level of this cycle: the device was recharged.
					recharged_at = now
					if entry["elapsed"] and entry["last_obs"] is not None:
						# The device was away between two readings: the recharge was somewhere in between.
						recharged_at = (entry["last_obs"] + now) / 2
					if entry["case_enabled"]:
						# The earbuds were charged by their case: count the battery points they gained.
						entry["case_used"] += (battery - entry["min_level"]) / 100
						if entry["case_pending"]:
							# The earbuds were recharged since the alert: the case was probably charged too. Ask the user.
							entry["case_pending"] = False
							entry["case_ask"] = True
					if entry["active"] >= _USAGE_MIN_CYCLE_SECONDS:
						entry["history"].append(
							{
								"end": recharged_at,
								"elapsed": entry["elapsed"],
								"pos": min((record["pos"] for record in entry["history"]), default=1.0) - 1,
								"secs": entry["active"],
								"from": entry["start_level"],
								"to": entry["min_level"],
							},
						)
						changed = True
					entry["active"] = 0.0
					entry["cycle_start"] = recharged_at
					entry["min_level"] = entry["start_level"] = battery
				else:
					if entry["elapsed"]:
						if battery < entry["min_level"]:
							# The level is only known when it is read, and Windows can show an old one for a
							# device that is away. So the cycle lasted at least until the level was seen dropping.
							if entry["cycle_start"] is None:
								entry["cycle_start"] = now
							entry["active"] = max(entry["active"], now - entry["cycle_start"])
					elif battery <= entry["level"]:
						entry["active"] += delta
					entry["min_level"] = min(entry["min_level"], battery)
				if connection_secs is not None:
					# Windows knows the current connection lasted at least this long, so the total
					# of this cycle cannot be smaller (unless a recharge just started a new cycle).
					if entry["cycle_start"] is None:
						entry["cycle_start"] = now - max(entry["active"], connection_secs)
					entry["active"] = max(entry["active"], min(connection_secs, now - entry["cycle_start"]))
				entry["level"] = battery
				entry["last_obs"] = now
				if entry != before:
					changed = True
			if self._prune_locked(now):
				changed = True
			if changed:
				self._save()

	def note_status(self, results) -> None:
		"""Remember the connection status of every device of the latest scan (any scan, tracking or not)."""
		with self._lock:
			self._ranks = {device.key: device.sort_rank for device in results}

	def get_rows(self) -> list[tuple[str, list[dict], dict]]:
		"""Snapshot for the statistics dialog: (device key, finished cycles oldest first, current cycle).

		Devices come in the same order as in the spoken report (connected, unknown, disconnected, then by
		name). Devices that were not in the latest scan come last.
		"""
		with self._lock:

			def display(item):
				key, entry = item
				return (entry["alias"] or entry["name"] or key).lower()

			ordered = sorted(
				self._data.items(),
				key=lambda item: (self._ranks.get(item[0], CONNECTION_DISCONNECTED + 1), display(item)),
			)
			return [
				(
					key,
					[dict(record) for record in entry["history"]],
					{
						"name": entry["name"] or key,
						"alias": entry["alias"],
						"ignored": entry["ignored"],
						"alert": entry["alert"],
						"drop_alert": entry["drop_alert"],
						"connect_alert": entry["connect_alert"],
						"disconnect_alert": entry["disconnect_alert"],
						"secs": entry["active"],
						"from": entry["start_level"],
						"to": entry["min_level"],
						"level": entry["level"],
						"rank": self._ranks.get(key),
						"order": entry["order"],
						"elapsed": entry["elapsed"],
						"charge_at": entry["charge_at"],
						**{
							name: (list(value) if isinstance(value, list) else value)
							for name, value in entry.items()
							if name.startswith("case_")
						},
					},
				)
				for key, entry in ordered
			]

	def display_name(self, key: str, name: str) -> str:
		"""The name to speak and show for a device: its alias if the user chose one."""
		with self._lock:
			entry = self._data.get(key)
			return (entry["alias"] if entry else None) or name

	def is_measured(self, key: str) -> bool:
		with self._lock:
			entry = self._data.get(key)
			return entry is None or not entry["ignored"]

	def set_alias(self, key: str, alias: str) -> None:
		"""Choose a name for a device. An empty name goes back to the name Windows gave."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry["alias"] = alias.strip() or None
			self._save()

	def set_ignored(self, key: str, ignored: bool) -> None:
		"""Stop or start measuring the connection time of a device. The data is kept."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry["ignored"] = ignored
			entry["last_seen"] = None
			self._save()

	def set_alert(self, key: str, level: int | None) -> None:
		"""Choose the low battery alert level of a device: a percentage, 0 for no alert, None for the default."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry["alert"] = level
			self._save()

	def alert_level(self, key: str, default: int) -> int:
		"""The low battery alert level of a device: its own, or the default. 0 means no alert."""
		with self._lock:
			entry = self._data.get(key)
			level = entry["alert"] if entry else None
			return default if level is None else level

	def set_alert_flag(self, key: str, flag: str, enabled: bool) -> None:
		"""Turn an alert of a device on or off. The flags are drop_alert, connect_alert and disconnect_alert."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry[flag] = enabled
			self._save()

	def alert_flag(self, key: str, flag: str) -> bool:
		with self._lock:
			entry = self._data.get(key)
			return bool(entry and entry[flag])

	def has_alert_flag(self, flag: str) -> bool:
		"""Whether any device has this alert turned on."""
		with self._lock:
			return any(entry[flag] for entry in self._data.values())

	def has_own_low_alert(self) -> bool:
		"""Whether any device has a low battery level of its own (it alerts even if the default is off)."""
		with self._lock:
			return any(entry["alert"] for entry in self._data.values())

	def has_case_alert(self) -> bool:
		"""Whether any device has the charging case alert turned on."""
		with self._lock:
			return any(entry["case_enabled"] for entry in self._data.values())

	def case_snapshot(self, key: str) -> dict | None:
		"""The charging case fields (case_...) of a device, or None if the device is not known."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return None
			return {
				name: (list(value) if isinstance(value, list) else value)
				for name, value in entry.items()
				if name.startswith("case_")
			}

	def set_case(self, key: str, enabled: bool, hours: float, total: float, alert_left: float) -> None:
		"""Turn the charging case of a device on or off and set its runtimes (hours) and alert level."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry["case_enabled"] = bool(enabled)
			if not enabled:
				entry["case_pending"] = entry["case_ask"] = False
			entry["case_hours"] = float(hours)
			entry["case_total"] = float(total)
			entry["case_alert"] = float(alert_left)
			self._save()

	def mark_case_charged(self, key: str) -> None:
		"""The case was charged: remember how many charges it gave in this round, then count from zero."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			if entry["case_used"] > 0:
				rounds = entry["case_rounds"] + [round(entry["case_used"], 2)]
				entry["case_rounds"] = rounds[-_CASE_MAX_ROUNDS:]
			entry["case_used"] = 0.0
			entry["case_pending"] = entry["case_ask"] = False
			self._save()

	def set_case_pending(self, key: str) -> None:
		"""The charging case alert was given: the next recharge of the earbuds leads to a question."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None or entry["case_pending"]:
				return
			entry["case_pending"] = True
			self._save()

	def pending_case_questions(self) -> list[tuple[str, str]]:
		"""(key, name) of the devices whose user should be asked whether the charging case was charged."""
		with self._lock:
			return [
				(key, entry["alias"] or entry["name"] or key)
				for key, entry in self._data.items()
				if entry["case_enabled"] and entry["case_ask"]
			]

	def answer_case_question(self, key: str, charged: bool) -> None:
		"""The user said whether the case was charged: count from zero again if it was, else keep counting."""
		if charged:
			self.mark_case_charged(key)
			return
		with self._lock:
			entry = self._data.get(key)
			if entry is not None and entry["case_ask"]:
				entry["case_ask"] = False
				self._save()

	def delete_cycles(self, key: str, numbers) -> None:
		"""Delete finished cycles of a device. The numbers are the cycle numbers shown (1 is the oldest)."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			for number in sorted(set(numbers), reverse=True):
				if 1 <= number <= len(entry["history"]):
					del entry["history"][number - 1]
			self._save()

	def reset_current(self, key: str) -> None:
		"""Restart the current cycle of a device from zero."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry["active"] = 0.0
			entry["cycle_start"] = time.time()
			if entry["level"] is not None:
				entry["min_level"] = entry["start_level"] = entry["level"]
			self._save()

	def set_elapsed(self, key: str, elapsed: bool) -> None:
		"""Count the elapsed time since the last recharge (True) or the connected time (False) of a device.

		The cycle in progress starts again, because its time is counted in another way. Finished cycles stay.
		"""
		with self._lock:
			entry = self._data.get(key)
			if entry is None or entry["elapsed"] == elapsed:
				return
			entry["elapsed"] = elapsed
			entry["active"] = 0.0
			entry["cycle_start"] = time.time()
			entry["last_seen"] = None
			entry["last_obs"] = None
			if entry["level"] is not None:
				entry["min_level"] = entry["start_level"] = entry["level"]
			self._save()

	def set_charge_at(self, key: str, level: int) -> None:
		"""Set the battery level at which the user usually recharges a device, 0 for none."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			entry["charge_at"] = min(max(int(level), 0), 95)
			self._save()

	def secs_since_recharge(self, key: str) -> float | None:
		"""Seconds since the last recharge of a device that counts elapsed time, None for the other devices."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None or not entry["elapsed"] or entry["cycle_start"] is None:
				return None
			return max(time.time() - entry["cycle_start"], 0.0)

	def init_manual_order(self, keys) -> None:
		"""Give a manual position, in this order, to the devices that have none, after those that have one."""
		with self._lock:
			missing = [key for key in keys if key in self._data and self._data[key]["order"] is None]
			if not missing:
				return
			orders = [entry["order"] for entry in self._data.values() if entry["order"] is not None]
			base = max(orders) + 1 if orders else 0.0
			for index, key in enumerate(missing):
				self._data[key]["order"] = base + index
			self._save()

	def set_device_order(self, keys) -> None:
		"""The manual order of the devices: the first key comes first."""
		with self._lock:
			for index, key in enumerate(keys):
				if key in self._data:
					self._data[key]["order"] = float(index)
			self._save()

	def set_cycle_order(self, key: str, numbers) -> None:
		"""The manual order of the finished cycles of a device. The numbers are the cycle numbers shown."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return
			for position, number in enumerate(numbers):
				if 1 <= number <= len(entry["history"]):
					entry["history"][number - 1]["pos"] = float(position)
			self._save()

	def delete_device(self, key: str) -> None:
		"""Delete everything recorded about a device."""
		with self._lock:
			self._ranks.pop(key, None)
			if self._data.pop(key, None) is not None:
				self._save()

	def get_info(self, key: str) -> tuple[float | None, float | None]:
		"""Return (last_finished_cycle_seconds, current_cycle_seconds) for a device."""
		with self._lock:
			entry = self._data.get(key)
			if entry is None:
				return None, None
			return (entry["history"][-1]["secs"] if entry["history"] else None), entry["active"]


def _case_capacity(case: dict) -> tuple[float | None, int]:
	"""How many times the charging case can charge the earbuds, and from how many finished rounds it was learned.

	Until enough rounds are finished (a round ends when the user marks the case as charged), the figure comes
	from the runtimes the user gave: the runtime with the case divided by the runtime of the earbuds, minus
	the first charge, which the earbuds have in themselves. Then the typical figure of the latest rounds is used.
	"""
	rounds = [used for used in case["case_rounds"] if used >= _CASE_ROUND_MIN_USED][-_CASE_LEARN_LATEST:]
	if len(rounds) >= _CASE_LEARN_MIN_ROUNDS:
		return statistics.median(rounds), len(rounds)
	hours = case["case_hours"]
	total = case["case_total"]
	if hours and total and total > hours:
		return total / hours - 1, 0
	return None, 0


def _case_left(case: dict) -> float | None:
	"""Charges the case is estimated to have left, None if the case is not turned on or its size is unknown."""
	if not case["case_enabled"]:
		return None
	capacity, rounds = _case_capacity(case)
	if capacity is None:
		return None
	return max(capacity - case["case_used"], 0.0)
