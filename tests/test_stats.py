"""The statistics: text of durations and rates, the columns of the lists, sorting, exports and the moves."""

import csv
import io
import json
from types import SimpleNamespace

import pytest


@pytest.fixture()
def rows(bt, device):
	"""The rows of a device that has a finished cycle and a charging case."""
	tracker = bt.usage.UsageTracker()
	tracker.update([device(80)], now=1e6, count=False)
	tracker._data["AA"]["history"] = [
		{"end": 1.7e9, "secs": 20 * 3600.0, "from": 100, "to": 60, "pos": 0.0, "elapsed": False},
		{"end": 1.8e9, "secs": 30 * 3600.0, "from": 100, "to": 55, "pos": -1.0, "elapsed": False},
	]
	tracker.set_case("AA", True, 10.0, 52.0, 1.0)
	return tracker.get_rows()


def test_durations_are_in_minutes_hours_or_days(bt):
	format_duration = bt.stats._format_duration
	assert [format_duration(seconds) for seconds in (45 * 60, 5 * 3600, 47 * 3600)] == ["45 min", "5 hr", "47 hr"]
	assert [format_duration(seconds) for seconds in (48 * 3600, 16.6 * 86400, 3 * 86400)] == [
		"2 days",
		"16.6 days",
		"3 days",
	]
	assert format_duration(3600 + 25 * 60) == "1 hr 25 min"


def test_slow_drain_rates_are_in_days(bt):
	assert bt.stats._format_drain_rate(4.5) == "4.5%/hr"
	assert bt.stats._format_drain_rate(0.3) == "7.2%/day"
	assert bt.stats._format_drain_rate(None) == ""


def test_the_trend_compares_the_latest_cycles_with_the_earlier_ones(bt):
	assert bt.stats._describe_trend([10.0, 10.0, 10.0]) == ""
	assert bt.stats._describe_trend([10.0, 10.0, 10.0, 10.0]) == "stable"
	assert bt.stats._describe_trend([10.0, 10.0, 8.0, 8.0, 8.0]) == "20% shorter"


def test_every_row_has_one_value_for_each_column_and_each_detail_header(bt, rows):
	summary = bt.stats._build_usage_summary_rows(rows)[0]
	assert len(summary.text) == len(bt.stats._summary_columns())
	assert len(summary.detail) == len(bt.stats._summary_detail_headers())
	blocks = bt.stats._build_usage_cycle_blocks(rows)
	cycle_rows = [blocks[0][1], *blocks[0][2]]
	text_columns = [column for column in bt.stats._cycle_columns() if column[0] != "state"]
	for row in cycle_rows:
		assert len(row.text) == len(text_columns)
		assert len(row.detail) == len(bt.stats._cycle_detail_headers())


def test_the_estimates_of_the_summary(bt, rows):
	labels = [column[1] for column in bt.stats._summary_columns()]
	summary = dict(zip(labels, bt.stats._build_usage_summary_rows(rows)[0].text))
	assert summary["Cycles"] == "2"
	assert summary["Shortest"] == "20 hr"
	assert summary["Longest"] == "30 hr"
	assert summary["Alerts"] == "low battery 20%, charging case"
	assert summary["Case left (charges, est.)"] == "4.2"


def test_the_columns_come_in_the_order_of_the_user(bt):
	columns = bt.stats._summary_columns()
	default = bt.stats._visible_columns("statsSummaryColumns", columns)
	assert default[0] == "device"
	# the columns about the charging case and the time counted are hidden until they are needed
	assert "case_left" not in default
	bt.conf["statsSummaryColumns"] = "status,device,drain,average,unknown_column,case_left"
	assert bt.stats._visible_columns("statsSummaryColumns", columns) == [
		"device",
		"status",
		"drain",
		"average",
		"case_left",
	]
	# the choice saved by an earlier version, with the required columns in it
	bt.conf["statsCycleColumns"] = "device,cycle,duration,battery"
	assert bt.stats._visible_columns("statsCycleColumns", bt.stats._cycle_columns()) == [
		"device",
		"cycle",
		"duration",
		"battery",
	]


def test_the_devices_can_be_sorted_by_name_or_by_a_measure(bt, rows):
	other = [(key, history, dict(current, name="Another", alias=None, order=5.0)) for key, history, current in rows]
	devices = [rows[0], other[0][:2] + (dict(other[0][2]),)]
	devices[1][2]["name"] = "Another"
	by_name = [device[2]["name"] for device in bt.stats._sort_devices(devices, "name")]
	assert by_name == ["Another", "Buds"]
	for mode, _label in bt.stats._device_sort_choices():
		bt.stats._sort_devices(devices, mode)


@pytest.mark.parametrize("fmt", ["text", "markdown", "csv", "tsv", "json", "html"])
def test_every_export_format_holds_all_the_rows(bt, rows, fmt):
	summary = bt.stats._build_usage_summary_rows(rows)
	headers = [column[1] for column in bt.stats._summary_columns()] + list(bt.stats._summary_detail_headers())
	values = [row.text + row.detail for row in summary]
	text = bt.stats._format_export(fmt, "Summary", headers, values)
	assert "Buds" in text
	if fmt == "csv":
		parsed = list(csv.reader(io.StringIO(text)))
		assert parsed[0] == headers and len(parsed) == 2 and len(parsed[1]) == len(headers)
	if fmt == "json":
		data = json.loads(text)
		assert len(data["rows"]) == 1
		# numbers stay numbers
		assert data["rows"][0]["Recharge level (%)"] is None
	if fmt == "html":
		assert "<table" in text and text.count("<tr>") == 2


class _List:
	def __init__(self, key):
		self.key = key

	def focusedKey(self):
		return self.key


@pytest.fixture()
def window(bt, device, monkeypatch):
	"""A statistics window without a screen: only what moving a row or a list needs."""
	tracker = bt.usage.UsageTracker()
	seen = []
	for key, name in (("A1", "Alpha"), ("B2", "Beta"), ("C3", "Gamma")):
		seen.append(device(80, key=key, name=name))
		tracker.update(list(seen), now=1e6, count=False)
	messages = []
	monkeypatch.setattr(bt.statswindow, "ui", SimpleNamespace(message=messages.append))
	beeps = []
	monkeypatch.setattr(bt.statswindow, "tones", SimpleNamespace(beep=lambda *args: beeps.append(args)))
	dialog = object.__new__(bt.statswindow.UsageStatsDialog)
	dialog._deviceSort = dialog._cycleSort = "manual"

	def reload():
		devices = bt.stats._sort_devices(tracker.get_rows(), dialog._deviceSort)
		dialog._summaryOrder = [(key, None) for key, history, current in devices]
		blocks = bt.stats._build_usage_cycle_blocks(devices, dialog._cycleSort)
		dialog._blocksByKey = {block[0]: block for block in blocks}

	dialog._reload = reload
	dialog.summaryList = _List(None)
	dialog.cyclesList = _List(None)
	reload()
	return SimpleNamespace(dialog=dialog, tracker=tracker, messages=messages, beeps=beeps)


def test_a_device_moves_with_the_manual_sort(bt, window):
	order = lambda: [key for key, number in window.dialog._summaryOrder]  # noqa: E731
	assert order() == ["C3", "B2", "A1"]
	window.dialog.summaryList.key = ("B2", None)
	window.dialog._moveRow(window.dialog.summaryList, 1)
	assert order() == ["C3", "A1", "B2"]
	assert window.messages[-1] == "3 of 3"
	# at the end of the list: a beep, and nothing moves
	window.dialog._moveRow(window.dialog.summaryList, 1)
	assert order() == ["C3", "A1", "B2"] and window.beeps
	# from the cycle list, the row of the cycle in progress moves the device
	window.dialog.cyclesList.key = ("A1", None)
	window.dialog._moveRow(window.dialog.cyclesList, -1)
	assert order() == ["A1", "C3", "B2"]


def test_nothing_moves_without_the_manual_sort(bt, window):
	window.dialog._deviceSort = "name"
	window.dialog._reload()
	before = list(window.dialog._summaryOrder)
	window.dialog.summaryList.key = ("B2", None)
	window.dialog._moveRow(window.dialog.summaryList, 1)
	assert window.dialog._summaryOrder == before
	assert "Manual" in window.messages[-1]


def test_a_finished_cycle_moves_among_the_cycles_of_its_device(bt, window):
	window.tracker._data["A1"]["history"] = [
		{"end": float(n), "secs": 4000.0 * n, "from": 100, "to": 40, "pos": -float(n - 1), "elapsed": False}
		for n in (1, 2, 3, 4)
	]
	window.dialog._reload()
	numbers = lambda: [row.key[1] for row in window.dialog._blocksByKey["A1"][2]]  # noqa: E731
	assert numbers() == [4, 3, 2, 1]
	window.dialog.cyclesList.key = ("A1", 3)
	window.dialog._moveRow(window.dialog.cyclesList, -1)
	assert numbers() == [3, 4, 2, 1]


def test_the_lists_swap_places_and_the_choice_is_kept(bt, window, monkeypatch):
	arranged = []
	dialog = window.dialog
	dialog._listsOrder = ["summary", "cycles"]
	dialog._arrangeLists = lambda: arranged.append(list(dialog._listsOrder))
	dialog.summaryList = SimpleNamespace(SetFocus=lambda: None)
	dialog.cyclesList = SimpleNamespace(SetFocus=lambda: None)
	dialog._moveList(dialog.cyclesList, -1)
	assert dialog._listsOrder == ["cycles", "summary"]
	assert bt.conf["statsListsOrder"] == "cycles,summary"
	assert arranged == [["cycles", "summary"]]
	# already first: a beep
	dialog._moveList(dialog.cyclesList, -1)
	assert dialog._listsOrder == ["cycles", "summary"] and window.beeps
