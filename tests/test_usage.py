"""The record of the use of each device: charging case, elapsed time, recharge level, manual order."""

import json
import time

import pytest

DAY = 86400.0
HOUR = 3600.0


def _scan(tracker, device, t, level, rank=None):
	tracker.update([device(level, rank)], now=t)


def test_the_charging_case_counts_the_charges_the_earbuds_got(bt, device):
	tracker = bt.usage.UsageTracker()
	t = 1_000_000.0
	tracker.update([device(100)], now=t)
	tracker.set_case("AA", True, 10.0, 52.0, 1.0)
	capacity, rounds = bt.usage._case_capacity(tracker.case_snapshot("AA"))
	# 52 hours with the case, 10 hours per charge: 4.2 charges (the first one is in the earbuds)
	assert (capacity, rounds) == (pytest.approx(4.2), 0)
	left = []
	for _ in range(5):
		for level in (60, 30, 10):
			t += 600
			_scan(tracker, device, t, level)
		t += 600
		_scan(tracker, device, t, 10, bt.bluetooth.CONNECTION_DISCONNECTED)
		t += 600
		_scan(tracker, device, t, 100)
		left.append(bt.usage._case_left(tracker.case_snapshot("AA")))
	# the earbuds go down to 10 percent: each recharge gives back 90 points
	assert left == pytest.approx([3.3, 2.4, 1.5, 0.6, 0.0])


def test_the_size_of_the_case_is_learned_from_the_rounds(bt, device):
	tracker = bt.usage.UsageTracker()
	tracker.update([device(100)], now=1e6, count=False)
	tracker.set_case("AA", True, 10.0, 52.0, 1.0)
	tracker._data["AA"]["case_rounds"] = [0.3, 0.2, 3.4]
	# rounds with less than one charge do not count, and two rounds are not enough
	assert bt.usage._case_capacity(tracker.case_snapshot("AA")) == (pytest.approx(4.2), 0)
	tracker._data["AA"]["case_rounds"] = [3.4, 3.6, 3.5, 3.5]
	assert bt.usage._case_capacity(tracker.case_snapshot("AA")) == (pytest.approx(3.5), 4)


def test_marking_the_case_as_charged_keeps_the_round_and_counts_again(bt, device):
	tracker = bt.usage.UsageTracker()
	tracker.update([device(100)], now=1e6, count=False)
	tracker.set_case("AA", True, 10.0, 52.0, 1.0)
	tracker._data["AA"]["case_used"] = 4.5
	tracker.mark_case_charged("AA")
	snapshot = tracker.case_snapshot("AA")
	assert snapshot["case_used"] == 0.0
	assert snapshot["case_rounds"] == [4.5]


def test_a_device_that_counts_elapsed_time_lasts_until_the_level_was_seen_dropping(bt, device):
	tracker = bt.usage.UsageTracker()
	t0 = time.time() - 80 * DAY

	def keyboard(level):
		return device(level, bt.bluetooth.CONNECTION_UNKNOWN, key="KB", name="KB", conn_type="LE")

	tracker.update([keyboard(100)], now=t0)
	tracker.set_elapsed("KB", True)
	entry = tracker._data["KB"]
	entry["cycle_start"] = entry["last_obs"] = t0
	# Windows keeps showing the old level while the keyboard is on its dongle (days 1 to 9, 11 to 19, 21 to 25)
	readings = {n: 100 for n in range(1, 10)}
	readings.update({10: 90, **{n: 90 for n in range(11, 20)}, 20: 78, **{n: 78 for n in range(21, 26)}, 26: 100})
	for day, level in sorted(readings.items()):
		tracker.update([keyboard(level)], now=t0 + day * DAY)
	record = entry["history"][-1]
	# the cycle lasted until the level was last seen dropping (day 20), not until the next reading
	assert record["secs"] == pytest.approx(20 * DAY)
	assert (record["from"], record["to"], record["elapsed"]) == (100, 78, True)
	# the recharge happened between the readings of days 25 and 26: it is placed halfway
	assert record["end"] == pytest.approx(t0 + 25.5 * DAY)
	assert entry["cycle_start"] == pytest.approx(t0 + 25.5 * DAY)
	tracker.update([keyboard(95)], now=t0 + 36 * DAY)
	assert entry["active"] == pytest.approx(10.5 * DAY)
	assert bt.stats._full_charge_seconds(record["secs"], 100, 78) == pytest.approx(20 * DAY * 100 / 22)


def test_the_connected_time_is_not_counted_while_the_device_is_away(bt, device):
	tracker = bt.usage.UsageTracker()
	t = 1e6
	tracker.update([device(100)], now=t)
	for step in range(1, 4):
		tracker.update([device(100)], now=t + step * 600)
	assert tracker._data["AA"]["active"] == pytest.approx(1800)
	# a gap of more than 15 minutes (the computer slept) is not counted
	tracker.update([device(99)], now=t + 3 * 600 + 5 * HOUR)
	assert tracker._data["AA"]["active"] == pytest.approx(1800)
	# a disconnected device is not counted either
	tracker.update([device(99, bt.bluetooth.CONNECTION_DISCONNECTED)], now=t + 3 * 600 + 5 * HOUR + 600)
	assert tracker._data["AA"]["active"] == pytest.approx(1800)


def test_the_estimates_go_down_to_the_usual_recharge_level(bt, device):
	tracker = bt.usage.UsageTracker()
	tracker.update([device(100, key="KB", name="KB")], now=1e6, count=False)
	entry = tracker._data["KB"]
	# the cycle of a keyboard: 115 hours and 32 minutes, from 100 to 71 percent
	entry["history"] = [{"end": 1e6, "secs": 115 * HOUR + 32 * 60, "from": 100, "to": 71, "pos": 0.0, "elapsed": False}]
	entry["level"] = entry["min_level"] = entry["start_level"] = 100

	def summary(level):
		entry["level"] = level
		row = tracker.get_rows()[0]
		labels = [column[1] for column in bt.stats._summary_columns()]
		return dict(zip(labels, bt.stats._build_usage_summary_rows([row])[0].text))

	whole = summary(100)
	assert whole["Full charge (est.)"] == "16.6 days"
	tracker.set_charge_at("KB", 70)
	assert summary(100)["Full charge (est.)"] == "5 days"
	assert summary(85)["Left now (est.)"] == "2.5 days"
	assert summary(70)["Left now (est.)"] == "0 min"
	assert summary(100)["Measuring"] == "on, recharge at 70%"
	tracker.set_charge_at("KB", 200)
	assert tracker._data["KB"]["charge_at"] == 95


def test_new_devices_come_first_in_the_manual_order(bt, device):
	tracker = bt.usage.UsageTracker()
	first = {"A1": "Alpha", "B2": "Beta", "C3": "Gamma"}
	seen = []
	for key, name in first.items():
		seen.append(device(80, key=key, name=name))
		tracker.update(list(seen), now=1e6, count=False)

	def names():
		return [row[2]["name"] for row in bt.stats._sort_devices(tracker.get_rows(), "manual")]

	assert names() == ["Gamma", "Beta", "Alpha"]
	for entry in tracker._data.values():
		entry["order"] = None
	tracker.init_manual_order(["B2", "C3", "A1"])
	assert names() == ["Beta", "Gamma", "Alpha"]
	tracker.update([device(80, key="D4", name="Delta")], now=1e6, count=False)
	assert names() == ["Delta", "Beta", "Gamma", "Alpha"]
	tracker.set_device_order(["A1", "D4", "C3", "B2"])
	assert names() == ["Alpha", "Delta", "Gamma", "Beta"]


def test_the_finished_cycles_can_be_put_in_the_order_of_the_user(bt, device):
	tracker = bt.usage.UsageTracker()
	tracker.update([device(100)], now=1e6, count=False)
	tracker._data["AA"]["history"] = [
		{"end": float(n), "secs": 4000.0 * n, "from": 100, "to": 40, "pos": -float(n - 1), "elapsed": False}
		for n in (1, 2, 3, 4)
	]
	history = tracker.get_rows()[0][1]
	assert [number for number, record in bt.stats._order_history(history, "manual")] == [4, 3, 2, 1]
	tracker.set_cycle_order("AA", [3, 4, 2, 1])
	history = tracker.get_rows()[0][1]
	assert [number for number, record in bt.stats._order_history(history, "manual")] == [3, 4, 2, 1]


def test_a_file_of_an_earlier_version_is_loaded(bt, device):
	tracker = bt.usage.UsageTracker()
	tracker.update([device(100)], now=1e6, count=False)
	tracker.set_case("AA", True, 10.0, 52.0, 1.0)
	tracker.set_elapsed("AA", True)
	tracker.set_charge_at("AA", 70)
	path = tracker._path
	data = json.load(open(path, encoding="utf-8"))
	for entry in data.values():
		for name in [name for name in entry if name.startswith("case_")] + ["elapsed", "last_obs", "charge_at", "order"]:
			entry.pop(name, None)
		entry["history"] = [{"end": 1.0, "secs": 4000.0, "from": 100, "to": 40}]
	json.dump(data, open(path, "w", encoding="utf-8"))
	row = bt.usage.UsageTracker().get_rows()[0]
	current = row[2]
	assert (current["elapsed"], current["charge_at"], current["case_enabled"], current["order"]) == (False, 0, False, None)
	assert row[1][0]["pos"] == 0.0 and row[1][0]["elapsed"] is False
	# the lists can be built from it
	bt.stats._build_usage_summary_rows([row])
	bt.stats._build_usage_cycle_blocks([row])
