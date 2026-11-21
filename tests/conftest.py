"""Stubs of the NVDA modules, so that the logic of the add-on can be tested without NVDA.

The tests only run the code that does not need a screen or a Bluetooth radio. Anything that touches
wx, gui or ui is replaced by a small fake in the test that needs it.
"""

import ctypes
import re
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _Meta(type):
	def __getattr__(cls, name):
		if name.startswith("__"):
			raise AttributeError(name)
		return Dummy


class Dummy(metaclass=_Meta):
	"""Stands for any class or object of NVDA: it accepts any attribute and any call."""

	def __init__(self, *args, **kwargs):
		pass

	def __getattr__(self, name):
		if name.startswith("__"):
			raise AttributeError(name)
		return Dummy()

	def __call__(self, *args, **kwargs):
		return Dummy()


class _Config(dict):
	spec: dict = {}
	profiles = [{}]


def _install_stubs():
	if not hasattr(ctypes, "WinDLL"):
		ctypes.WinDLL = lambda *args, **kwargs: MagicMock()
		ctypes.windll = MagicMock()
	for name in ("addonHandler", "api", "globalPluginHandler", "logHandler", "ui", "wx", "gui", "tones", "nvwave"):
		module = types.ModuleType(name)
		module.__getattr__ = lambda attribute, _m=module: Dummy
		sys.modules[name] = module

	def initTranslation():
		# Like NVDA: the translation functions are put in the module that calls this.
		caller = sys._getframe(1).f_globals
		caller["_"] = lambda text: text
		caller["ngettext"] = lambda one, other, count: one if count == 1 else other

	sys.modules["addonHandler"].initTranslation = initTranslation
	sys.modules["globalPluginHandler"].GlobalPlugin = Dummy
	sys.modules["logHandler"].log = MagicMock()
	sys.modules["ui"].message = lambda *args, **kwargs: None
	config = types.ModuleType("config")
	config.conf = _Config()
	config.conf["btBatterytics"] = {}
	sys.modules["config"] = config
	sys.modules["globalVars"] = types.ModuleType("globalVars")
	sys.modules["globalVars"].appArgs = SimpleNamespace(configPath="")
	script_handler = types.ModuleType("scriptHandler")
	script_handler.script = lambda **kwargs: (lambda function: function)
	script_handler.getLastScriptRepeatCount = lambda: 0
	sys.modules["scriptHandler"] = script_handler


_install_stubs()


def _defaults(confspec):
	"""The default value of every setting, from its configuration specification."""
	values = {}
	for name, spec in confspec.items():
		default = re.search(r"default=([^,)]*)", spec).group(1)
		kind = spec.split("(")[0]
		values[name] = (default == "True") if kind == "boolean" else int(default) if kind == "integer" else default.strip("'")
	return values


@pytest.fixture()
def bt(tmp_path):
	"""The modules of the add-on, with default settings and an empty folder for the data."""
	from btBatterytics import bluetooth, dialogs, settings, shared, sounds, stats, statswindow, usage
	import btBatterytics as package

	sys.modules["globalVars"].appArgs.configPath = str(tmp_path)
	config = sys.modules["config"]
	config.conf.clear()
	config.conf["btBatterytics"] = _defaults(settings.confspec)
	usage.UsageTracker.current = None
	shared.plugin = None
	return SimpleNamespace(
		package=package,
		bluetooth=bluetooth,
		dialogs=dialogs,
		settings=settings,
		shared=shared,
		sounds=sounds,
		stats=stats,
		statswindow=statswindow,
		usage=usage,
		conf=config.conf["btBatterytics"],
		folder=tmp_path,
	)


@pytest.fixture()
def device(bt):
	"""A function that makes a device as the scan of the Bluetooth devices gives it."""

	def make(level, rank=None, key="AA", name="Buds", conn_type="Classic"):
		if rank is None:
			rank = bt.bluetooth.CONNECTION_CONNECTED
		return bt.bluetooth.BluetoothDevice(name, level, rank, conn_type, None, key)

	return make
