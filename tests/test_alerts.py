"""The alerts and the questions of the plugin: what is said, played and shown, and in which order."""

from types import SimpleNamespace

import pytest


class _Now:
	"""A thread that runs at once, so that the order of the sounds can be tested."""

	def __init__(self, target, args=(), daemon=None):
		self.target = target
		self.args = args

	def start(self):
		self.target(*self.args)


@pytest.fixture()
def plugin(bt, device, monkeypatch):
	"""The plugin with fakes for what NVDA shows and plays. The fakes are in .spoken, .boxes, .sounds, .beeps."""
	package = bt.package
	instance = package.GlobalPlugin()
	fakes = SimpleNamespace(spoken=[], sounds=[], beeps=[], answers=[], boxes=[])
	monkeypatch.setattr(package, "ui", SimpleNamespace(message=fakes.spoken.append))
	monkeypatch.setattr(package, "tones", SimpleNamespace(beep=lambda *args: fakes.beeps.append(args)))
	monkeypatch.setattr(package, "nvwave", SimpleNamespace(playWaveFile=lambda path, **kw: fakes.sounds.append((path, kw))))
	monkeypatch.setattr(package, "threading", SimpleNamespace(Thread=_Now))
	wx = SimpleNamespace(
		CallAfter=lambda function, *args: function(*args),
		CallLater=lambda *args: None,
		OK=0,
		ICON_WARNING=0,
		YES=1,
		NO=2,
		YES_NO=0,
		NO_DEFAULT=0,
		ICON_QUESTION=0,
	)
	monkeypatch.setattr(package, "wx", wx)

	def message_box(text, title, style, *args):
		fakes.boxes.append(text)
		return fakes.answers.pop(0) if fakes.answers else wx.NO

	monkeypatch.setattr(package, "gui", SimpleNamespace(messageBox=message_box))
	instance._usage_tracker = bt.usage.UsageTracker()
	instance.fakes = fakes
	return instance


def _scan(plugin, bt, device, level, rank=None):
	"""One scan of the background monitor, with the device at this level."""
	results = [device(level, rank)]
	bt.package.collect_bluetooth_battery = lambda: results
	plugin._last_slow_check = float("-inf")
	plugin._monitor_scan()


def test_a_level_drop_is_not_given_with_the_low_battery_alert_of_the_same_device(bt, device, plugin):
	tracker = plugin._usage_tracker
	tracker.update([device(50)], now=1e6, count=False)
	tracker.set_alert_flag("AA", "drop_alert", True)
	for level in (50, 40, 30, 20, 15, 10):
		_scan(plugin, bt, device, level)
	assert plugin.fakes.spoken == [
		"Buds battery 40%",
		"Buds battery 30%",
		"Buds battery low: 20%",
		"Buds battery 10%",
	]
	# only the low battery alert has a dialog
	assert plugin.fakes.boxes == ["Buds battery low: 20%"]


def test_a_device_with_an_unknown_status_gets_level_drops_but_no_low_battery_alert(bt, device, plugin):
	tracker = plugin._usage_tracker
	tracker.update([device(50)], now=1e6, count=False)
	tracker.set_alert_flag("AA", "drop_alert", True)
	unknown = bt.bluetooth.CONNECTION_UNKNOWN
	for level in (30, 20, 10):
		_scan(plugin, bt, device, level, unknown)
	assert plugin.fakes.spoken == ["Buds battery 20%", "Buds battery 10%"]


def test_the_sounds_of_several_alerts_play_one_after_another_until_their_end(bt, plugin, monkeypatch):
	for name in bt.sounds._SOUND_FILES.values():
		(bt.folder / name).write_bytes(b"")
	monkeypatch.setattr(bt.package, "_sounds_dir", lambda: str(bt.folder))
	bt.conf["alertSpeech"] = False
	bt.conf["alertCustomSound"] = True
	plugin._notify(
		{"low_battery": ["a"], "level_drop": [], "connected": ["b"], "disconnected": [], "case": ["c"]},
	)
	played = [(path.split("/")[-1].split("\\")[-1], options) for path, options in plugin.fakes.sounds]
	assert [name for name, options in played] == ["lowBattery.wav", "deviceConnected.wav", "chargingCase.wav"]
	# NVDA stops a sound when another one starts, unless the call waits for the end of the sound
	assert all(options == {"asynchronous": False} for name, options in played)


def test_a_beep_replaces_a_missing_sound_file(bt, plugin, monkeypatch):
	monkeypatch.setattr(bt.package, "_sounds_dir", lambda: str(bt.folder))
	bt.conf["alertSpeech"] = False
	bt.conf["alertCustomSound"] = True
	plugin._notify({"low_battery": [], "level_drop": [], "connected": [], "disconnected": [], "case": ["c"]})
	assert plugin.fakes.beeps == [(600, 250)]


def test_the_charging_case_alert_and_the_question(bt, device, plugin):
	tracker = plugin._usage_tracker
	tracker.update([device(100)], now=1e6, count=False)
	tracker.set_case("AA", True, 10.0, 52.0, 1.0)
	clock = [1e6]
	alerts = []

	def scan(level, rank=None):
		clock[0] += 600
		results = [device(level, rank)]
		tracker.update(results, now=clock[0])
		found = plugin._find_case_alerts(results, 20)
		plugin._queue_case_questions()
		alerts.extend(found)

	def round_():
		for level in (60, 30, 10):
			scan(level)
		scan(10, bt.bluetooth.CONNECTION_DISCONNECTED)
		scan(100)

	for _ in range(4):
		round_()
	assert alerts == [] and plugin.fakes.boxes == []
	plugin.fakes.answers = [2]
	round_()
	# the fifth time the earbuds run low, the case has about 0.6 charges left
	assert len(alerts) == 1 and "charges left: about 0.6" in alerts[0]
	assert len(plugin.fakes.boxes) == 1
	# the answer was No: the case keeps counting, and the alert comes again at the next low battery
	assert tracker.case_snapshot("AA")["case_used"] == pytest.approx(4.5)
	plugin.fakes.answers = [1]
	round_()
	assert len(alerts) == 2 and len(plugin.fakes.boxes) == 2
	snapshot = tracker.case_snapshot("AA")
	assert snapshot["case_used"] == 0.0 and snapshot["case_rounds"] == pytest.approx([5.4])
	assert not snapshot["case_pending"] and not snapshot["case_ask"]


def test_the_report_tells_the_time_since_the_last_recharge_of_a_device_that_counts_elapsed_time(bt, device, plugin):
	import time

	tracker = plugin._usage_tracker
	tracker.update([device(95)], now=time.time() - 5 * 86400, count=False)
	tracker.set_elapsed("AA", True)
	tracker._data["AA"]["cycle_start"] = time.time() - 12 * 86400
	bt.conf["showConnectionDuration"] = True
	bt.conf["reportUnknown"] = True
	line = plugin._format_report([device(95, bt.bluetooth.CONNECTION_UNKNOWN)], {bt.bluetooth.CONNECTION_UNKNOWN})
	assert line == "Buds battery 95% (since the last recharge 12 days)"
