"""BT-Batterytics: global plugin for Bluetooth battery levels, connection times and statistics."""

from __future__ import annotations


import threading
import time
from datetime import datetime
import os
import addonHandler
import api
import globalPluginHandler
import logHandler
import ui
import wx
import gui
import config
from scriptHandler import script, getLastScriptRepeatCount
import tones
import nvwave

from . import shared
from .bluetooth import (
	BluetoothDevice,
	CONNECTION_CONNECTED,
	CONNECTION_DISCONNECTED,
	CONNECTION_UNKNOWN,
	_has_system_battery,
	collect_bluetooth_battery,
)
from .settings import BtBatteryticsSettingsPanel
from .sounds import _FALLBACK_BEEPS, _SOUND_FILES, _sounds_dir
from .stats import _format_count, _format_duration
from .statswindow import _show_usage_statistics
from .usage import UsageTracker, _case_left

addonHandler.initTranslation()

log = logHandler.log


SCRIPT_CATEGORY = _("BT-Batterytics")

# Low battery monitor interval: 5 minutes
_MONITOR_INTERVAL_MS = 5 * 60 * 1000


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Reports Bluetooth battery percentages for local devices based on user settings."""

	def __init__(self):
		super().__init__()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(BtBatteryticsSettingsPanel)
		# NVDA+Shift+B is NVDA's own battery command: leave it alone on computers that have a battery.
		self.bindGesture(
			"kb:NVDA+alt+b" if _has_system_battery() else "kb:NVDA+shift+b",
			"reportBluetoothBattery",
		)
		self._monitor_timer: wx.CallLater | None = None
		self._alerted_devices: set[str] = set()
		# The earbuds whose charging case alert was given, until their battery recovers.
		self._alerted_cases: set[str] = set()
		self._case_question_open = False
		# The devices that got a low battery alert in the latest check: they get no level drop alert with it.
		self._low_keys_now: set[str] = set()
		# The battery level from which the next drop of each device is counted for the level drop alerts.
		self._drop_baseline: dict[str, int] = {}
		# Whether each device was connected at the previous check, for the connection alerts.
		self._last_connected: dict[str, bool] = {}
		# When the checks that do not need to be frequent (times, low batteries, level drops) were last done.
		self._last_slow_check = float("-inf")
		self._gesture_timer: wx.CallLater | None = None
		self._usage_tracker = UsageTracker()
		self._start_monitor()
		shared.plugin = self

	def terminate(self):
		shared.plugin = None
		self._stop_monitor()
		if self._gesture_timer is not None:
			self._gesture_timer.Stop()
			self._gesture_timer = None
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(BtBatteryticsSettingsPanel)
		except ValueError:
			pass
		super().terminate()

	def _start_monitor(self):
		self._monitor_timer = wx.CallLater(_MONITOR_INTERVAL_MS, self._monitor_tick)

	def _stop_monitor(self):
		if self._monitor_timer is not None:
			self._monitor_timer.Stop()
			self._monitor_timer = None

	def restart_monitor(self):
		"""Start checking again soon, after a setting or an alert that changes how often to check."""
		self._stop_monitor()
		self._monitor_timer = wx.CallLater(1000, self._monitor_tick)

	def _monitor_tick(self):
		conf = config.conf["btBatterytics"]
		tracker = self._usage_tracker
		watch_connections = tracker.has_alert_flag("connect_alert") or tracker.has_alert_flag(
			"disconnect_alert",
		)
		# Connections are checked often, the rest only every few minutes.
		interval = conf["connectionCheckSeconds"] * 1000 if watch_connections else _MONITOR_INTERVAL_MS
		self._monitor_timer = wx.CallLater(interval, self._monitor_tick)
		if (
			conf["enableLowBatteryAlert"]
			or conf["enableUsageTracking"]
			or watch_connections
			or tracker.has_alert_flag("drop_alert")
			or tracker.has_own_low_alert()
			or tracker.has_case_alert()
		):
			threading.Thread(target=self._monitor_scan, daemon=True).start()

	def _monitor_scan(self):
		try:
			results = collect_bluetooth_battery()
		except Exception:
			log.exception("BT-Batterytics: background monitor scan failed")
			return

		self._usage_tracker.note_status(results)
		conf = config.conf["btBatterytics"]
		alerts = {event: [] for event in _SOUND_FILES}
		self._find_connection_changes(results, alerts)
		if time.monotonic() - self._last_slow_check >= _MONITOR_INTERVAL_MS / 1000 - 1:
			self._last_slow_check = time.monotonic()
			self._usage_tracker.update(results, count=conf["enableUsageTracking"])
			# Devices without a level of their own use the default: none if the low battery alert is off.
			default_level = conf["lowBatteryThreshold"] if conf["enableLowBatteryAlert"] else 0
			alerts["low_battery"] = self._find_low_batteries(results, default_level)
			# A level drop that comes with a low battery alert of the same device is not given twice.
			alerts["level_drop"] = self._find_level_drops(results, conf["dropAlertStep"])
			alerts["case"] = self._find_case_alerts(results, conf["lowBatteryThreshold"])
			self._queue_case_questions()
		if any(alerts.values()):
			wx.CallAfter(self._show_alerts, alerts)

	def _find_connection_changes(self, results, alerts):
		"""Add to alerts the devices, with the connect or disconnect alert on, that changed since the last check.

		A device counts as connected unless it is known to be disconnected, as for the connection time.
		"""
		connected_now: dict[str, bool] = {}
		for device in results:
			connected = device.sort_rank != CONNECTION_DISCONNECTED
			connected_now[device.key] = connected
			previous = self._last_connected.get(device.key)
			if previous is None or previous == connected:
				continue
			flag = "connect_alert" if connected else "disconnect_alert"
			if self._usage_tracker.alert_flag(device.key, flag):
				name = self._usage_tracker.display_name(device.key, device.name)
				if connected:
					alerts["connected"].append(_("{name} connected").format(name=name))
				else:
					alerts["disconnected"].append(_("{name} disconnected").format(name=name))
		self._last_connected = connected_now

	def _find_low_batteries(self, results, default_threshold):
		"""Texts of the connected devices whose battery just got low. A device alerts once until it recovers."""
		# The level of each device: its own, or the default. 0 means no alert for the device.
		thresholds = {
			device.key: self._usage_tracker.alert_level(device.key, default_threshold) for device in results
		}
		alerts: list[str] = []
		current_names: set[str] = set()
		self._low_keys_now = set()

		for device in results:
			current_names.add(device.key)
			threshold = thresholds[device.key]
			if threshold and device.battery <= threshold and device.sort_rank == CONNECTION_CONNECTED:
				if device.key not in self._alerted_devices:
					name = self._usage_tracker.display_name(device.key, device.name)
					alerts.append(
						_("{name} battery low: {battery}%").format(name=name, battery=device.battery),
					)
					self._alerted_devices.add(device.key)
					self._low_keys_now.add(device.key)

		stale = {n for n in self._alerted_devices if n not in current_names}
		for device in results:
			threshold = thresholds[device.key]
			if (not threshold or device.battery > threshold) and device.key in self._alerted_devices:
				stale.add(device.key)
		self._alerted_devices -= stale
		return alerts

	def _queue_case_questions(self):
		"""Ask the user, on the main thread, about the charging cases that were probably charged."""
		if self._case_question_open or not self._usage_tracker.pending_case_questions():
			return
		self._case_question_open = True
		wx.CallAfter(self._ask_case_questions)

	def _ask_case_questions(self):
		"""One question for each device whose earbuds were recharged after the charging case alert.

		Yes counts the charges of the case from zero again. No keeps counting, and is the default answer:
		a wrong No only makes the next alert come a little early.
		"""
		try:
			for key, name in self._usage_tracker.pending_case_questions():
				answer = gui.messageBox(
					# Translators: question about the charging case. {name} is the name of the earbuds.
					_(
						"Did you charge the charging case of {name}?\n\n"
						"The case was estimated to be nearly empty, and the earbuds have been recharged since. "
						"Choose Yes to count the charges of the case from zero again, or No to keep counting.",
					).format(name=name),
					# Translators: title of the question about the charging case
					_("Charging case"),
					wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
				)
				self._usage_tracker.answer_case_question(key, answer == wx.YES)
				if answer == wx.YES:
					# Translators: spoken after the user said that the charging case was charged
					ui.message(_("Case marked as charged"))
		finally:
			self._case_question_open = False

	def _find_case_alerts(self, results, default_threshold):
		"""Texts for the earbuds, with the charging case alert on, whose battery is low while the case is
		estimated to be nearly empty: the case should be charged together with the earbuds.

		The battery is low at the low battery level of the device, or at the default level. An alert is
		given once, until the battery of the earbuds recovers or the case is marked as charged.
		"""
		texts: list[str] = []
		wanted: set[str] = set()
		for device in results:
			case = self._usage_tracker.case_snapshot(device.key)
			if case is None or not case["case_enabled"]:
				continue
			left = _case_left(case)
			level = self._usage_tracker.alert_level(device.key, default_threshold) or default_threshold
			if (
				left is None
				or left >= case["case_alert"]
				or device.battery > level
				or device.sort_rank == CONNECTION_DISCONNECTED
			):
				continue
			wanted.add(device.key)
			if device.key not in self._alerted_cases:
				self._alerted_cases.add(device.key)
				self._usage_tracker.set_case_pending(device.key)
				name = self._usage_tracker.display_name(device.key, device.name)
				texts.append(
					# Translators: charging case alert. {count} is a number of charges, for example 0.2
					_(
						"{name} charging case may be nearly empty, charges left: about {count}. "
						"Charge it together with the earbuds.",
					).format(name=name, count=_format_count(left)),
				)
		self._alerted_cases &= wanted
		return texts

	def _find_level_drops(self, results, step):
		"""Texts of the devices, with the level drop alert on, whose battery dropped by at least `step`
		points since their last alert. The count starts when the device is first seen and again whenever
		the battery level rises (charging).
		"""
		texts: list[str] = []
		wanted: set[str] = set()
		for device in results:
			if not self._usage_tracker.alert_flag(device.key, "drop_alert"):
				continue
			wanted.add(device.key)
			if device.sort_rank == CONNECTION_DISCONNECTED:
				continue
			baseline = self._drop_baseline.get(device.key)
			if baseline is None or device.battery > baseline:
				self._drop_baseline[device.key] = device.battery
			elif device.battery <= baseline - step:
				self._drop_baseline[device.key] = device.battery
				if device.key in self._low_keys_now:
					# The low battery alert of this check already says it.
					continue
				name = self._usage_tracker.display_name(device.key, device.name)
				texts.append(_("{name} battery {battery}%").format(name=name, battery=device.battery))
		for key in [key for key in self._drop_baseline if key not in wanted]:
			del self._drop_baseline[key]
		return texts

	def _show_alerts(self, alerts):
		"""Give the alerts (on the main thread): the alert methods, then the dialog of the low batteries."""
		self._notify(alerts)
		warnings = alerts["low_battery"] + alerts["case"]
		if warnings:
			gui.messageBox(
				"\n".join(warnings),
				# Translators: Title of the low battery alert dialog
				_("Bluetooth Battery Low"),
				wx.OK | wx.ICON_WARNING,
			)

	def _notify(self, alerts):
		"""Give the alerts by every method the user checked: speech, a double beep, the sound of each alert."""
		conf = config.conf["btBatterytics"]
		events = [event for event in _SOUND_FILES if alerts[event]]
		if conf["alertSpeech"]:
			ui.message("; ".join(text for event in events for text in alerts[event]))
		if conf["alertBeep"]:
			self._play_double_beep()
		if conf["alertCustomSound"]:
			# NVDA plays one wave file at a time and stops the one that is playing when another starts,
			# so the sounds are played one after another, in a background thread.
			threading.Thread(target=self._play_sounds, args=(events,), daemon=True).start()

	def _play_sounds(self, events):
		"""Play the sounds of the alerts one after another. Runs in a background thread."""
		for event in events:
			self._play_sound(event)

	def _play_double_beep(self):
		tones.beep(880, 70)
		wx.CallLater(150, tones.beep, 880, 70)

	def _play_sound(self, event):
		"""Play the sound file of an alert. A beep is played if the file is missing."""
		path = os.path.join(_sounds_dir(), _SOUND_FILES[event])
		if os.path.isfile(path):
			try:
				# Wait for the end of the sound, so that the next one does not stop it (this is a background thread).
				nvwave.playWaveFile(path, asynchronous=False)
				return
			except Exception:
				log.exception("BT-Batterytics: could not play the sound of an alert")
		hz, length = _FALLBACK_BEEPS[event]
		tones.beep(hz, length)

	def _build_allowed_ranks(self) -> set[int]:
		conf = config.conf["btBatterytics"]
		ranks: set[int] = set()
		if conf["reportConnected"]:
			ranks.add(CONNECTION_CONNECTED)
		if conf["reportUnknown"]:
			ranks.add(CONNECTION_UNKNOWN)
		if conf["reportDisconnected"]:
			ranks.add(CONNECTION_DISCONNECTED)
		return ranks

	def _format_report(
		self,
		results: list[BluetoothDevice],
		allowed_ranks: set[int],
	) -> str | None:
		conf = config.conf["btBatterytics"]
		show_type = conf["showConnectionType"]
		show_duration = conf["showConnectionDuration"]
		show_usage = conf["enableUsageTracking"]
		now_local = datetime.now()
		lines: list[str] = []

		for device in results:
			sort_rank = device.sort_rank
			if sort_rank not in allowed_ranks:
				continue

			name = self._usage_tracker.display_name(device.key, device.name)
			if show_type and device.conn_type:
				base = _("{name} ({conn_type}) battery {battery}%").format(
					name=name,
					conn_type=device.conn_type,
					battery=device.battery,
				)
			else:
				base = _("{name} battery {battery}%").format(name=name, battery=device.battery)

			# Append duration for connected devices when requested.
			# Sanity-check: only show if elapsed is positive and less than 7 days,
			# to guard against stale or reset Registry values.
			elapsed_secs: float | None = None
			# Translators: label shown before connection duration, e.g. 'connected 43 min'
			duration_label = _("connected")
			since_recharge = self._usage_tracker.secs_since_recharge(device.key) if show_duration else None
			if since_recharge is not None:
				# A device that counts elapsed time: the time since its last recharge, connected or not.
				elapsed_secs = since_recharge
				# Translators: label shown before the time since the last recharge, e.g. 'since the last recharge 12 days'
				duration_label = _("since the last recharge")
			elif show_duration and show_usage and self._usage_tracker.is_measured(device.key):
				# Total connection time since the last recharge, remembered across disconnections.
				if sort_rank != CONNECTION_DISCONNECTED:
					elapsed_secs = self._usage_tracker.get_info(device.key)[1]
			elif show_duration and sort_rank == CONNECTION_CONNECTED and device.last_used is not None:
				# Time since the current connection started, as reported by Windows.
				elapsed_secs = (now_local - device.last_used).total_seconds()
				if not 0 < elapsed_secs < 86400 * 7:
					elapsed_secs = None
			if elapsed_secs is not None and elapsed_secs > 0:
				duration_str = _format_duration(elapsed_secs)
				# Translators: appended to a device line, e.g. 'FIIO EH11 battery 85% (connected 43 min)'
				base = _("{device_info} ({connected_label} {duration})").format(
					device_info=base,
					connected_label=duration_label,
					duration=duration_str,
				)

			if conf["reportCaseLeft"]:
				case = self._usage_tracker.case_snapshot(device.key)
				case_left = _case_left(case) if case else None
				if case_left is not None:
					# Translators: appended to a device line. {count} is a number of charges, for example 2.2
					base = _("{device_info} (case charges left: about {count})").format(
						device_info=base,
						count=_format_count(case_left),
					)

			lines.append(base)

		return "; ".join(lines) if lines else None

	def _handle_scan_action(self, repeat_count: int):
		"""Background thread: collect data and speak or copy."""
		try:
			results = collect_bluetooth_battery()
		except Exception:
			log.exception("BT-Batterytics: battery detection failed")
			wx.CallAfter(ui.message, _("Bluetooth battery detection failed."))
			return

		self._usage_tracker.note_status(results)
		if results:
			self._usage_tracker.update(results, count=config.conf["btBatterytics"]["enableUsageTracking"])
			self._queue_case_questions()

		allowed_ranks = self._build_allowed_ranks()

		if not results:
			wx.CallAfter(ui.message, _("No Bluetooth battery information is available."))
			return

		report = self._format_report(results, allowed_ranks)
		if report is None:
			wx.CallAfter(ui.message, _("No matching Bluetooth devices found based on your settings."))
			return

		if repeat_count == 1:
			wx.CallAfter(self._copy_to_clipboard, report)
		else:
			wx.CallAfter(ui.message, report)

	def _copy_to_clipboard(self, text: str):
		if api.copyToClip(text):
			ui.message(_("Battery report copied to clipboard."))
		else:
			ui.message(_("Failed to copy to clipboard."))

	@script(
		# Translators: description shown in NVDA Input Gestures dialog
		description=_("Open the Bluetooth battery statistics."),
		category=SCRIPT_CATEGORY,
		# No gesture is assigned by default: the user can assign one in the Input Gestures dialog.
	)
	def script_openBatteryStatistics(self, gesture):
		# The window is modal, so it is not opened directly from the script.
		wx.CallAfter(_show_usage_statistics)

	@script(
		# Translators: description shown in NVDA Input Gestures dialog
		description=_(
			"Press once to report battery, twice to copy to clipboard, three times to open settings.",
		),
		category=SCRIPT_CATEGORY,
		# The default gesture is bound in __init__, because it depends on the computer.
	)
	def script_reportBluetoothBattery(self, gesture):
		repeat_count = getLastScriptRepeatCount()

		if self._gesture_timer is not None:
			self._gesture_timer.Stop()
			self._gesture_timer = None

		self._gesture_timer = wx.CallLater(20, self._execute_gesture, repeat_count)

	def _execute_gesture(self, repeat_count: int):
		self._gesture_timer = None
		if repeat_count == 2:
			wx.CallAfter(
				gui.mainFrame.popupSettingsDialog,
				gui.settingsDialogs.NVDASettingsDialog,
				BtBatteryticsSettingsPanel,
			)
			return
		threading.Thread(
			target=self._handle_scan_action,
			args=(repeat_count,),
			daemon=True,
		).start()
