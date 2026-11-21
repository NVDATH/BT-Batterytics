"""The sound files of the alerts."""

from __future__ import annotations


import os
import addonHandler


# The sound file of each alert, in the "sounds" folder of the add-on. Replace a file to change the sound.
_SOUND_FILES = {
	"low_battery": "lowBattery.wav",
	"level_drop": "levelDrop.wav",
	"connected": "deviceConnected.wav",
	"disconnected": "deviceDisconnected.wav",
	"case": "chargingCase.wav",
}
# Beep (frequency in Hz, length in ms) played when the sound file of an alert is missing.
_FALLBACK_BEEPS = {
	"low_battery": (500, 400),
	"level_drop": (700, 150),
	"connected": (900, 120),
	"disconnected": (400, 120),
	"case": (600, 250),
}


def _sounds_dir() -> str:
	"""The "sounds" folder: in the folder of the add-on, or next to this file if it is not in an add-on."""
	try:
		return os.path.join(addonHandler.getCodeAddon().path, "sounds")
	except Exception:
		return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
