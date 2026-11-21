"""The statistics: estimates, rows and columns of the lists, sorting and exports."""

from __future__ import annotations


import csv
import html
import io
import json
from datetime import datetime
from typing import NamedTuple
import addonHandler
import config

from .bluetooth import CONNECTION_CONNECTED, CONNECTION_DISCONNECTED, CONNECTION_UNKNOWN
from .usage import _CASE_COLUMNS, _case_capacity, _case_left

addonHandler.initTranslation()


def _format_duration(seconds: float) -> str:
	"""Return a human-readable duration string from a number of seconds.

	Examples: '3 min', '1 hr 25 min', '2 hr'
	"""
	if seconds >= 2 * 86400:
		# Translators: a duration in days, e.g. '2.5 days'
		days = round(seconds / 86400, 1)
		return _("{days} days").format(days=int(days) if days == int(days) else days)
	total_minutes = int(seconds // 60)
	hours = total_minutes // 60
	minutes = total_minutes % 60
	if hours == 0:
		# Translators: duration in minutes only, e.g. '45 min'
		return _("{minutes} min").format(minutes=minutes)
	if minutes == 0:
		# Translators: duration in whole hours only, e.g. '2 hr'
		return _("{hours} hr").format(hours=hours)
	# Translators: duration in hours and minutes, e.g. '1 hr 25 min'
	return _("{hours} hr {minutes} min").format(hours=hours, minutes=minutes)


# Cycles that used fewer battery points than this are too coarse for runtime estimates
_STATS_MIN_DROP = 10
# The latest cycles compared with the earlier ones for the trend
_STATS_TREND_RECENT = 3
# A change smaller than this (fraction) is reported as "stable"
_STATS_STABLE_RANGE = 0.05


def _format_battery_range(start: int | None, end: int | None) -> str:
	if start is None or end is None:
		return ""
	# Translators: battery level range of one cycle, from the level at its start to the lowest level, e.g. '100% to 23%'
	return _("{start}% to {end}%").format(start=start, end=end)


def _format_long_duration(seconds: float) -> str:
	"""Like _format_duration, but in days from two days on."""
	if seconds >= 2 * 86400:
		# Translators: a duration in days, e.g. '2.5 days'
		days = round(seconds / 86400, 1)
		return _("{days} days").format(days=int(days) if days == int(days) else days)
	return _format_duration(seconds)


def _format_timestamp(epoch: float | None) -> str:
	if epoch is None:
		return ""
	return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _charge_span(current: dict) -> int:
	"""The battery points between a full battery and the level at which the user usually recharges the device.

	That is 100 (the whole battery), unless the user gave a recharge level for a device whose reported level
	does not go down evenly, for example one that stops working at 55 percent.
	"""
	return 100 - current["charge_at"]


def _full_charge_seconds(secs: float, start: int | None, end: int | None, span: int = 100) -> float | None:
	"""Estimated runtime on a full charge, from the battery points used during `secs` seconds.

	With a span smaller than 100, it is the runtime from a full battery down to the usual recharge level.
	"""
	if start is None or end is None or secs <= 0:
		return None
	drop = start - end
	if drop < _STATS_MIN_DROP:
		return None
	return secs * span / drop


def _format_full_charge(secs: float, start: int | None, end: int | None, span: int = 100) -> str:
	life = _full_charge_seconds(secs, start, end, span)
	return _format_duration(life) if life is not None else ""


def _describe_trend(lives: list[float]) -> str:
	"""Compare the latest cycles with the earlier ones (full-charge runtimes, oldest first)."""
	if len(lives) <= _STATS_TREND_RECENT:
		return ""
	recent = lives[-_STATS_TREND_RECENT:]
	earlier = lives[:-_STATS_TREND_RECENT]
	change = (sum(recent) / len(recent)) / (sum(earlier) / len(earlier)) - 1
	if abs(change) < _STATS_STABLE_RANGE:
		# Translators: battery life trend, recent cycles are about as long as earlier ones
		return _("stable")
	percent = round(abs(change) * 100)
	if change < 0:
		# Translators: battery life trend, recent cycles are shorter than earlier ones, e.g. '12% shorter'
		return _("{percent}% shorter").format(percent=percent)
	# Translators: battery life trend, recent cycles are longer than earlier ones, e.g. '8% longer'
	return _("{percent}% longer").format(percent=percent)


def _cycle_drain_rate(secs: float, start: int | None, end: int | None) -> float | None:
	"""Battery points used per hour during a cycle, or None if too little battery was used to tell."""
	if _full_charge_seconds(secs, start, end) is None:
		return None
	return (start - end) * 3600 / secs


def _usable_records(history: list[dict], current: dict) -> list[tuple[float, int]]:
	"""(connected seconds, battery points used) of the cycles that used enough battery for estimates.

	These are the finished cycles or, if there are none, the cycle in progress.
	"""
	records = [
		(r["secs"], r["from"] - r["to"])
		for r in history
		if _full_charge_seconds(r["secs"], r["from"], r["to"]) is not None
	]
	if not records and _full_charge_seconds(current["secs"], current["from"], current["to"]) is not None:
		records = [(current["secs"], current["from"] - current["to"])]
	return records


def _drain_rate(history: list[dict], current: dict) -> float | None:
	"""The usual battery points used per hour of connection."""
	records = _usable_records(history, current)
	if not records:
		return None
	return sum(used for secs, used in records) * 3600 / sum(secs for secs, used in records)


def _format_drain_rate(rate: float | None) -> str:
	if rate is None:
		return ""
	if rate < 0.5:
		# Translators: battery points used per day, for devices that drain slowly, for example '7.2%/day'
		return _("{rate}%/day").format(rate=f"{rate * 24:.1f}")
	# Translators: battery points used per hour, for example '4.5%/hr'
	return _("{rate}%/hr").format(rate=f"{rate:.1f}")


def _rounded(value, digits=2):
	return None if value is None else round(value, digits)


def _default_low_level() -> int:
	"""The low battery level devices use when they have none of their own: 0 (no alert) if the alert is off."""
	section = config.conf["btBatterytics"]
	return section["lowBatteryThreshold"] if section["enableLowBatteryAlert"] else 0


def _describe_alerts(current: dict) -> str:
	"""Text for the alerts of a device, in the summary list."""
	parts = []
	level = current["alert"]
	if level is None:
		level = _default_low_level()
	if level:
		# Translators: the low battery alert of a device and its level, for example 'low battery 20%'
		parts.append(_("low battery {level}%").format(level=level))
	if current["drop_alert"]:
		# Translators: the level drop alert of a device is on, in the list of its alerts
		parts.append(_("level drop"))
	if current["connect_alert"]:
		# Translators: the connect alert of a device is on, in the list of its alerts
		parts.append(_("connect"))
	if current["disconnect_alert"]:
		# Translators: the disconnect alert of a device is on, in the list of its alerts
		parts.append(_("disconnect"))
	if current["case_enabled"]:
		# Translators: the charging case alert of a device is on, in the list of its alerts
		parts.append(_("charging case"))
	# Translators: a device has no alert, in the summary list
	return ", ".join(parts) if parts else _("none")


def _effective_alert(current: dict):
	"""The alert level in percent that applies to a device, None if it has no alert."""
	level = current["alert"]
	if level is None:
		level = _default_low_level()
	return level or None


def _matching_history(history: list[dict], current: dict) -> list[dict]:
	"""The finished cycles whose time was counted as it is counted now for the device (connected or elapsed)."""
	return [record for record in history if bool(record.get("elapsed", False)) == current["elapsed"]]


def _describe_basis(elapsed: bool) -> str:
	"""Text for the way the time of a cycle was counted."""
	# Translators: how the time of a cycle was counted: the time since the last recharge
	# (for devices that are not always connected), or the time the device was connected
	return _("elapsed time") if elapsed else _("connected time")


def _format_count(value) -> str:
	"""A number of charges for the lists and the messages: one decimal at most, empty for no value."""
	if value is None:
		return ""
	text = f"{value:.1f}"
	return text[:-2] if text.endswith(".0") else text


def _average_full_charge_seconds(history: list[dict]) -> float | None:
	"""The average estimated runtime on a full charge of the finished cycles, None if there is no estimate."""
	runtimes = [
		runtime
		for runtime in (_full_charge_seconds(r["secs"], r["from"], r["to"]) for r in history)
		if runtime is not None
	]
	return sum(runtimes) / len(runtimes) if runtimes else None


def _time_left_seconds(history: list[dict], current: dict) -> float | None:
	"""Connected seconds left at the usual drain rate, from the battery level seen last."""
	level = current["level"]
	if level is None or level <= 0:
		return None
	records = _usable_records(history, current)
	if not records:
		return None
	# Down to the level at which the user usually recharges, not down to 0.
	return (
		max(level - current["charge_at"], 0)
		* sum(secs for secs, used in records)
		/ sum(used for secs, used in records)
	)


def _estimate_time_left(history: list[dict], current: dict) -> str:
	seconds = _time_left_seconds(history, current)
	return _format_duration(seconds) if seconds is not None else ""


def _order_history(history, mode):
	"""The finished cycles as (number, record) pairs in the chosen order.

	The number is the position in the history, 1 for the oldest cycle, as shown in the cycle list.
	"""
	numbered = list(enumerate(history, start=1))
	if mode == "oldest":
		return numbered
	if mode == "manual":
		return sorted(numbered, key=lambda pair: pair[1]["pos"])
	if mode == "longest":
		return sorted(numbered, key=lambda pair: pair[1]["secs"], reverse=True)
	if mode == "shortest":
		return sorted(numbered, key=lambda pair: pair[1]["secs"])
	return numbered[::-1]


def _whole(value):
	"""A number of seconds (or any other value) rounded to a whole number, None stays None."""
	return None if value is None else int(round(value))


def _iso(epoch):
	return None if epoch is None else datetime.fromtimestamp(epoch).isoformat(timespec="seconds")


def _display_name(current: dict) -> str:
	"""The name shown for a device: its alias if the user chose one."""
	return current["alias"] or current["name"]


class _StatsRow(NamedTuple):
	"""A row of a statistics list.

	key is (device key, cycle number); the number is None for the summary row and for the cycle in progress.
	text is the text of the columns, detail the extra values of the exports with detailed values.
	"""

	key: tuple
	text: tuple
	detail: tuple


# The columns that cannot be hidden.
_REQUIRED_COLUMNS = ("device", "cycle")
# Columns that are not shown until the user turns on what they are about (the charging case).
_DEFAULT_HIDDEN_COLUMNS = _CASE_COLUMNS + ("basis",)


def _summary_columns():
	# Translators: column headers of the summary list of the statistics
	return (
		("device", _("Device"), 200),
		("status", _("Status"), 100),
		("measuring", _("Measuring"), 90),
		("alerts", _("Alerts"), 200),
		("cycles", _("Cycles"), 70),
		("average", _("Average"), 100),
		("shortest", _("Shortest"), 100),
		("longest", _("Longest"), 100),
		("full_charge", _("Full charge (est.)"), 130),
		("drain", _("Drain rate"), 100),
		("recharged_every", _("Recharged every"), 130),
		("last_recharge", _("Last recharge"), 150),
		("trend", _("Trend"), 110),
		("left_now", _("Left now (est.)"), 130),
		# Translators: column headers of the summary list: the charges of the charging case of earbuds
		("case_used", _("Case used (charges, est.)"), 150),
		("case_left", _("Case left (charges, est.)"), 150),
	)


def _cycle_columns():
	# Translators: column headers of the cycle list of the statistics
	return (
		("device", _("Device"), 200),
		("cycle", _("Cycle"), 80),
		("state", _("State"), 90),
		("duration", _("Duration"), 110),
		("battery", _("Battery"), 140),
		("drain", _("Drain rate"), 100),
		("full_charge", _("Full charge (est.)"), 130),
		("ended", _("Ended"), 150),
		# Translators: column header of the cycle list: how the time of the cycle was counted
		("basis", _("Time counted"), 120),
	)


def _summary_detail_headers():
	# Translators: extra column headers of the exports with detailed values. (s) means seconds.
	return (
		_("Device ID"),
		_("Device name"),
		_("Alias"),
		_("Battery level (%)"),
		_("Current cycle (s)"),
		_("Average (s)"),
		_("Shortest (s)"),
		_("Longest (s)"),
		_("Full charge estimate (s)"),
		_("Recharge interval (s)"),
		_("Last recharge (ISO 8601)"),
		_("Left now (s)"),
		_("Drain rate (points/hour)"),
		_("Alert level (%)"),
		_("Level drop alert"),
		_("Connect alert"),
		_("Disconnect alert"),
		# Translators: extra column headers of the exports with detailed values (charges of the charging case)
		_("Case used (charges)"),
		_("Case capacity (charges)"),
		_("Case left (charges)"),
		# Translators: extra column header of the exports with detailed values
		_("Recharge level (%)"),
	)


def _cycle_detail_headers():
	# Translators: extra column headers of the exports with detailed values. (s) means seconds.
	return (
		_("Device ID"),
		_("Device name"),
		_("Alias"),
		_("Duration (s)"),
		_("Battery at start (%)"),
		_("Lowest battery (%)"),
		_("Battery used (points)"),
		_("Full charge estimate (s)"),
		_("Ended (ISO 8601)"),
		_("Drain rate (points/hour)"),
	)


def _visible_columns(config_key, columns):
	"""Ids of the columns to show, in order: the required columns, then the choice of the user.

	Without a saved choice, every column is shown, except those that are hidden until they are needed.
	"""
	saved = [part for part in config.conf["btBatterytics"][config_key].split(",") if part]
	ids = [column[0] for column in columns]
	if not saved:
		return [column_id for column_id in ids if column_id not in _DEFAULT_HIDDEN_COLUMNS]
	chosen = []
	for column_id in saved:
		if column_id in ids and column_id not in _REQUIRED_COLUMNS and column_id not in chosen:
			chosen.append(column_id)
	return [column_id for column_id in ids if column_id in _REQUIRED_COLUMNS] + chosen


def _build_usage_cycle_blocks(devices, cycle_order="newest"):
	"""Rows of the cycle list, grouped by device.

	For each device: its key, the row of the cycle in progress, and the rows of the finished cycles in the
	chosen order. The text of a row is (device, cycle, duration, battery, drain rate, full charge, ended).
	"""
	blocks = []
	for key, history, current in devices:
		name = _display_name(current)
		span = _charge_span(current)
		who = (key, current["name"], current["alias"])
		used = None
		if current["from"] is not None and current["to"] is not None:
			used = current["from"] - current["to"]
		current_row = _StatsRow(
			(key, None),
			(
				name,
				# Translators: value in the 'Cycle' column for the cycle that has not finished yet
				_("current"),
				_format_duration(current["secs"]),
				_format_battery_range(current["from"], current["to"]),
				_format_drain_rate(_cycle_drain_rate(current["secs"], current["from"], current["to"])),
				_format_full_charge(current["secs"], current["from"], current["to"], span),
				"",
				_describe_basis(current["elapsed"]),
			),
			who
			+ (
				_whole(current["secs"]),
				current["from"],
				current["to"],
				used,
				_whole(_full_charge_seconds(current["secs"], current["from"], current["to"], span)),
				None,
				_rounded(_cycle_drain_rate(current["secs"], current["from"], current["to"])),
			),
		)
		finished_rows = []
		for number, record in _order_history(history, cycle_order):
			used = None
			if record["from"] is not None and record["to"] is not None:
				used = record["from"] - record["to"]
			finished_rows.append(
				_StatsRow(
					(key, number),
					(
						name,
						str(number),
						_format_duration(record["secs"]),
						_format_battery_range(record["from"], record["to"]),
						_format_drain_rate(_cycle_drain_rate(record["secs"], record["from"], record["to"])),
						_format_full_charge(record["secs"], record["from"], record["to"], span),
						_format_timestamp(record["end"]),
						_describe_basis(bool(record.get("elapsed", False))),
					),
					who
					+ (
						_whole(record["secs"]),
						record["from"],
						record["to"],
						used,
						_whole(_full_charge_seconds(record["secs"], record["from"], record["to"], span)),
						_iso(record["end"]),
						_rounded(_cycle_drain_rate(record["secs"], record["from"], record["to"])),
					),
				),
			)
		blocks.append((key, current_row, finished_rows))
	return blocks


def _flatten_cycle_blocks(blocks, expanded):
	"""Rows shown in the cycle list, and a key for each row: (device key, cycle number), the number is None
	for the cycle in progress.

	For each device the cycle in progress is shown, then, if the device is expanded, its finished cycles.
	A State column is added after the cycle number: it says whether the device is collapsed or expanded,
	and is empty for the rows of finished cycles and for devices that have none.
	"""
	rows = []
	keys = []
	for key, current_row, finished_rows in blocks:
		if not finished_rows:
			state = ""
		elif key in expanded:
			# Translators: state of a device in the cycle list, its finished cycles are shown
			state = _("expanded")
		else:
			# Translators: state of a device in the cycle list, its finished cycles are hidden
			state = _("collapsed")
		text = current_row.text
		rows.append(text[:2] + (state,) + text[2:])
		keys.append(current_row.key)
		if key in expanded:
			for row in finished_rows:
				rows.append(row.text[:2] + ("",) + row.text[2:])
				keys.append(row.key)
	return rows, keys


def _describe_measuring(current: dict) -> str:
	"""Text for the Measuring column: off, or on with the way the time is counted and the usual recharge level."""
	if current["ignored"]:
		return _("off")
	parts = [_("on, elapsed time") if current["elapsed"] else _("on")]
	if current["charge_at"]:
		# Translators: the level at which a device is usually recharged, in the summary list, e.g. 'recharge at 70%'
		parts.append(_("recharge at {level}%").format(level=current["charge_at"]))
	return ", ".join(parts)


def _describe_status(rank: int | None) -> str:
	"""Text for the connection status (sort rank) of a device, empty if it was not in the latest scan."""
	if rank == CONNECTION_CONNECTED:
		# Translators: connection status shown in the statistics
		return _("connected")
	if rank == CONNECTION_UNKNOWN:
		# Translators: connection status shown in the statistics
		return _("unknown")
	if rank == CONNECTION_DISCONNECTED:
		# Translators: connection status shown in the statistics
		return _("disconnected")
	return ""


def _build_usage_summary_rows(devices):
	"""The rows of the summary list, one per device."""
	rows = []
	for key, history, current in devices:
		# The statistics use the cycles counted as the device is counted now (connected or elapsed time).
		history = _matching_history(history, current)
		span = _charge_span(current)
		durations = [record["secs"] for record in history]
		runtimes = [
			runtime
			for runtime in (_full_charge_seconds(r["secs"], r["from"], r["to"], span) for r in history)
			if runtime is not None
		]
		ends = [record["end"] for record in history if record["end"] is not None]
		average = sum(durations) / len(durations) if durations else None
		shortest = min(durations) if durations else None
		longest = max(durations) if durations else None
		full_charge = sum(runtimes) / len(runtimes) if runtimes else None
		interval = (ends[-1] - ends[0]) / (len(ends) - 1) if len(ends) >= 2 else None
		last_recharge = ends[-1] if ends else None
		time_left = _time_left_seconds(history, current)
		drain = _drain_rate(history, current)
		case_left = _case_left(current)
		case_capacity = _case_capacity(current)[0] if current["case_enabled"] else None
		case_used = current["case_used"] if current["case_enabled"] else None
		text = (
			_display_name(current),
			_describe_status(current["rank"]),
			# Translators: whether the connection time of a device is measured, in the summary list
			_describe_measuring(current),
			_describe_alerts(current),
			str(len(history)),
			_format_duration(average) if average is not None else "",
			_format_duration(shortest) if shortest is not None else "",
			_format_duration(longest) if longest is not None else "",
			_format_duration(full_charge) if full_charge is not None else "",
			_format_drain_rate(drain),
			_format_long_duration(interval) if interval is not None else "",
			_format_timestamp(last_recharge),
			_describe_trend(runtimes),
			_format_duration(time_left) if time_left is not None else "",
			_format_count(case_used),
			_format_count(case_left),
		)
		detail = (
			key,
			current["name"],
			current["alias"],
			current["level"],
			_whole(current["secs"]),
			_whole(average),
			_whole(shortest),
			_whole(longest),
			_whole(full_charge),
			_whole(interval),
			_iso(last_recharge),
			_whole(time_left),
			_rounded(drain),
			_effective_alert(current),
			current["drop_alert"],
			current["connect_alert"],
			current["disconnect_alert"],
			_rounded(case_used),
			_rounded(case_capacity),
			_rounded(case_left),
			current["charge_at"] or None,
		)
		rows.append(_StatsRow((key, None), text, detail))
	return rows


def _format_row_text(headers, row) -> str:
	"""Text of one row of a statistics list, as 'Header: value' pairs. Empty values are left out."""
	return "; ".join(f"{header}: {value}" for header, value in zip(headers, row) if value)


def _device_sort_choices():
	return (
		# Translators: ways to sort the devices of the statistics, in the Sort menu
		("report", _("Report order (connected first)")),
		("name", _("Name")),
		("cycles", _("Number of cycles")),
		("average", _("Average time")),
		("full_charge", _("Full charge estimate")),
		("last_recharge", _("Last recharge")),
		("current", _("Current cycle time")),
		("drain", _("Drain rate")),
		# Translators: a way to sort the devices in the Sort menu: the user moves them with Control+Shift+Up or Down
		("manual", _("Manual (Control+Shift+Up or Down moves a device)")),
	)


def _cycle_sort_choices():
	return (
		# Translators: ways to sort the finished cycles of each device, in the Sort menu
		("newest", _("Newest first")),
		("oldest", _("Oldest first")),
		("longest", _("Longest first")),
		("shortest", _("Shortest first")),
		# Translators: a way to sort the finished cycles in the Sort menu: the user moves them with Control+Shift+Up or Down
		("manual", _("Manual (Control+Shift+Up or Down moves a cycle)")),
	)


def _sort_devices(devices, mode):
	"""The devices in the chosen order. They come in report order, which also decides ties."""
	if mode == "manual":
		# The order of the user. A device without a position comes last.
		return sorted(devices, key=lambda device: (device[2]["order"] is None, device[2]["order"] or 0.0))
	if mode == "name":
		return sorted(devices, key=lambda device: _display_name(device[2]).lower())

	def metric(device):
		key, history, current = device
		history = _matching_history(history, current)
		span = _charge_span(current)
		if mode == "cycles":
			return len(history)
		if mode == "current":
			return current["secs"]
		if mode == "average":
			return sum(record["secs"] for record in history) / len(history) if history else None
		if mode == "full_charge":
			runtimes = [
				runtime
				for runtime in (_full_charge_seconds(r["secs"], r["from"], r["to"], span) for r in history)
				if runtime is not None
			]
			return sum(runtimes) / len(runtimes) if runtimes else None
		if mode == "last_recharge":
			ends = [record["end"] for record in history if record["end"] is not None]
			return max(ends) if ends else None
		if mode == "drain":
			return _drain_rate(history, current)
		return None

	if mode not in ("cycles", "current", "average", "full_charge", "last_recharge", "drain"):
		return list(devices)
	# The highest value first; devices without a value come last.
	with_value = sorted((d for d in devices if metric(d) is not None), key=metric, reverse=True)
	return with_value + [d for d in devices if metric(d) is None]


def _export_formats():
	return (
		# Translators: file formats in the Export menu of the statistics
		("text", _("Plain text"), "txt"),
		("markdown", _("Markdown table"), "md"),
		("csv", _("CSV"), "csv"),
		("tsv", _("Tab-separated values (for spreadsheets)"), "tsv"),
		("json", _("JSON"), "json"),
		("html", _("HTML table"), "html"),
	)


def _cell_text(value) -> str:
	return "" if value is None else str(value)


def _format_export(fmt, title, headers, rows) -> str:
	"""The rows of a statistics list in one of the export formats. Only the standard library is used.

	The values can be numbers or None (an empty cell): JSON keeps the numbers.
	"""
	if fmt == "json":
		data = {
			"title": title,
			"exported": datetime.now().isoformat(timespec="seconds"),
			"rows": [dict(zip(headers, row)) for row in rows],
		}
		return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
	cells = [[_cell_text(value) for value in row] for row in rows]
	if fmt == "csv":
		buffer = io.StringIO()
		writer = csv.writer(buffer, lineterminator="\r\n")
		writer.writerow(headers)
		writer.writerows(cells)
		return buffer.getvalue()
	if fmt == "tsv":

		def clean(cell):
			return cell.replace("\t", " ").replace("\r", " ").replace("\n", " ")

		return "".join("\t".join(clean(cell) for cell in row) + "\r\n" for row in [headers, *cells])
	if fmt == "markdown":

		def cell_text(cell):
			return cell.replace("|", "\\|").replace("\n", " ")

		lines = [
			f"# {title}",
			"",
			"| " + " | ".join(cell_text(header) for header in headers) + " |",
			"| " + " | ".join("---" for header in headers) + " |",
		]
		lines += ["| " + " | ".join(cell_text(cell) for cell in row) + " |" for row in cells]
		return "\n".join(lines) + "\n"
	if fmt == "html":
		escape = html.escape
		head = "".join(f'<th scope="col">{escape(header)}</th>' for header in headers)
		body = "".join(
			"<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>\n" for row in cells
		)
		# Translators: title of the HTML report of the statistics
		page_title = escape(_("Bluetooth battery statistics"))
		# Translators: line below the title of the HTML report, with the date and time
		exported = escape(_("Exported {date}").format(date=datetime.now().strftime("%Y-%m-%d %H:%M")))
		return (
			'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
			f"<title>{page_title}</title></head>\n<body>\n"
			f"<h1>{page_title}</h1>\n<p>{exported}</p>\n"
			f"<h2>{escape(title)}</h2>\n"
			f'<table border="1">\n<thead><tr>{head}</tr></thead>\n<tbody>\n{body}</tbody>\n</table>\n'
			"</body></html>\n"
		)
	# Plain text: one line of "Header: value" pairs for each row.
	return "\n".join([title, *(_format_row_text(headers, row) for row in cells)]) + "\n"
