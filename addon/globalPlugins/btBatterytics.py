# BT-Batterytics: Bluetooth battery levels, connection times and statistics for NVDA
# Modified version of BlueToothBatteryReport, https://github.com/haitun001/BlueToothBatteryReport
# Original work Copyright (C) haitun001 and cary-rowen
# Modified in 2026 by NVDATH: connection status filters, connection type label, connection duration,
# low battery alert, measurement of the total connection time between recharges, battery statistics,
# device names chosen by the user and other changes
# (see https://github.com/haitun001/BlueToothBatteryReport/issues/3).
# Ideas, design decisions and testing with NVDA: NVDATH. All the modifications to the code were written by
# Claude, an AI assistant made by Anthropic, following the instructions of NVDATH.
# This file is covered by the GNU General Public License version 2.
# See the file COPYING.txt of the original project for more details.

"""BT-Batterytics: global plugin for Bluetooth battery levels, connection times and statistics."""

from __future__ import annotations

import csv
import ctypes
import html
import io
import json
import re
import shutil
import statistics
import tempfile
import threading
import time
from ctypes import wintypes
from datetime import datetime
from typing import NamedTuple
import os
import addonHandler
import api
import globalPluginHandler
import logHandler
import ui
import wx
import gui
import config
import globalVars
from scriptHandler import script, getLastScriptRepeatCount
import tones
import nvwave

addonHandler.initTranslation()


SCRIPT_CATEGORY = _("BT-Batterytics")
log = logHandler.log

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
cfgmgr32 = ctypes.WinDLL("CfgMgr32", use_last_error=True)
bthprops = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
kernel32 = ctypes.windll.kernel32

DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004

SPDRP_DEVICEDESC = 0x00000000
SPDRP_FRIENDLYNAME = 0x0000000C

ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259
CR_SUCCESS = 0
CM_LOCATE_DEVNODE_NORMAL = 0
DEVPROP_TYPE_BYTE = 0x00000003
DEVPROP_TYPE_UINT32 = 0x00000007
DEVPROP_TYPE_STRING = 0x00000012
DN_DEVICE_DISCONNECTED = 0x02000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

CONNECTION_CONNECTED = 0
CONNECTION_UNKNOWN = 1
CONNECTION_DISCONNECTED = 2

# Connection type constants (derived from instance_id prefix)
CONNTYPE_CLASSIC = "Classic"
CONNTYPE_LE = "LE"
CONNTYPE_UNKNOWN_TYPE = ""

# Low battery monitor interval: 5 minutes
_MONITOR_INTERVAL_MS = 5 * 60 * 1000
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
# The plugin that is running, so that the statistics window and the settings can restart its monitor.
_plugin_instance = None


def _sounds_dir() -> str:
	"""The "sounds" folder: in the folder of the add-on, or next to this file if it is not in an add-on."""
	try:
		return os.path.join(addonHandler.getCodeAddon().path, "sounds")
	except Exception:
		return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

# Usage tracking (connected time between two recharges)
_USAGE_FILE_NAME = "btBatterytics_usage.json"
# The names used before the add-on was renamed: the data and the settings under them are taken over.
_LEGACY_USAGE_FILE_NAME = "blueToothBatteryReport_usage.json"
_LEGACY_CONFIG_SECTION = "blueToothBatteryReport"
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


class GUID(ctypes.Structure):
	_fields_ = [
		("Data1", wintypes.DWORD),
		("Data2", wintypes.WORD),
		("Data3", wintypes.WORD),
		("Data4", ctypes.c_ubyte * 8),
	]


class DEVPROPKEY(ctypes.Structure):
	_fields_ = [
		("fmtid", GUID),
		("pid", wintypes.DWORD),
	]


class SP_DEVINFO_DATA(ctypes.Structure):
	_fields_ = [
		("cbSize", wintypes.DWORD),
		("ClassGuid", GUID),
		("DevInst", wintypes.DWORD),
		("Reserved", ctypes.c_void_p),
	]


class SYSTEMTIME(ctypes.Structure):
	_fields_ = [
		("wYear", wintypes.WORD),
		("wMonth", wintypes.WORD),
		("wDayOfWeek", wintypes.WORD),
		("wDay", wintypes.WORD),
		("wHour", wintypes.WORD),
		("wMinute", wintypes.WORD),
		("wSecond", wintypes.WORD),
		("wMilliseconds", wintypes.WORD),
	]


class BLUETOOTH_ADDRESS_UNION(ctypes.Union):
	_fields_ = [
		("ullLong", ctypes.c_ulonglong),
		("rgBytes", ctypes.c_ubyte * 6),
	]


class BLUETOOTH_ADDRESS(ctypes.Structure):
	_anonymous_ = ("address",)
	_fields_ = [("address", BLUETOOTH_ADDRESS_UNION)]


class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
	_fields_ = [("dwSize", wintypes.DWORD)]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
	_fields_ = [
		("dwSize", wintypes.DWORD),
		("fReturnAuthenticated", wintypes.BOOL),
		("fReturnRemembered", wintypes.BOOL),
		("fReturnUnknown", wintypes.BOOL),
		("fReturnConnected", wintypes.BOOL),
		("fIssueInquiry", wintypes.BOOL),
		("cTimeoutMultiplier", ctypes.c_ubyte),
		("hRadio", wintypes.HANDLE),
	]


class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
	_fields_ = [
		("dwSize", wintypes.DWORD),
		("Address", BLUETOOTH_ADDRESS),
		("ulClassofDevice", wintypes.ULONG),
		("fConnected", wintypes.BOOL),
		("fRemembered", wintypes.BOOL),
		("fAuthenticated", wintypes.BOOL),
		("stLastSeen", SYSTEMTIME),
		("stLastUsed", SYSTEMTIME),
		("szName", wintypes.WCHAR * 248),
	]


DEVPKEY_BLUETOOTH_BATTERY = DEVPROPKEY(
	GUID(
		0x104EA319,
		0x6EE2,
		0x4701,
		(ctypes.c_ubyte * 8)(0xBD, 0x47, 0x8D, 0xDB, 0xF4, 0x25, 0xBB, 0xE5),
	),
	2,
)

DEVPKEY_NAME = DEVPROPKEY(
	GUID(
		0xB725F130,
		0x47EF,
		0x101A,
		(ctypes.c_ubyte * 8)(0xA5, 0xF1, 0x02, 0x60, 0x8C, 0x9E, 0xEB, 0xAC),
	),
	10,
)

DEVPKEY_DEVICE_FRIENDLYNAME = DEVPROPKEY(
	GUID(
		0xA45C254E,
		0xDF1C,
		0x4EFD,
		(ctypes.c_ubyte * 8)(0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0),
	),
	14,
)

DEVPKEY_DEVICE_DEVNODE_STATUS = DEVPROPKEY(
	GUID(
		0x4340A6C5,
		0x93FA,
		0x4706,
		(ctypes.c_ubyte * 8)(0x97, 0x2C, 0x7B, 0x64, 0x80, 0x08, 0xA5, 0xA7),
	),
	2,
)


SetupDiGetClassDevsW = setupapi.SetupDiGetClassDevsW
SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
SetupDiGetClassDevsW.restype = ctypes.c_void_p

SetupDiDestroyDeviceInfoList = setupapi.SetupDiDestroyDeviceInfoList
SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

SetupDiEnumDeviceInfo = setupapi.SetupDiEnumDeviceInfo
SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
SetupDiEnumDeviceInfo.restype = wintypes.BOOL

SetupDiGetDeviceInstanceIdW = setupapi.SetupDiGetDeviceInstanceIdW
SetupDiGetDeviceInstanceIdW.argtypes = [
	ctypes.c_void_p,
	ctypes.POINTER(SP_DEVINFO_DATA),
	wintypes.LPWSTR,
	wintypes.DWORD,
	ctypes.POINTER(wintypes.DWORD),
]
SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL

SetupDiGetDeviceRegistryPropertyW = setupapi.SetupDiGetDeviceRegistryPropertyW
SetupDiGetDeviceRegistryPropertyW.argtypes = [
	ctypes.c_void_p,
	ctypes.POINTER(SP_DEVINFO_DATA),
	wintypes.DWORD,
	ctypes.POINTER(wintypes.DWORD),
	ctypes.POINTER(ctypes.c_byte),
	wintypes.DWORD,
	ctypes.POINTER(wintypes.DWORD),
]
SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL

SetupDiGetDevicePropertyW = setupapi.SetupDiGetDevicePropertyW
SetupDiGetDevicePropertyW.argtypes = [
	ctypes.c_void_p,
	ctypes.POINTER(SP_DEVINFO_DATA),
	ctypes.POINTER(DEVPROPKEY),
	ctypes.POINTER(wintypes.ULONG),
	ctypes.POINTER(ctypes.c_byte),
	wintypes.DWORD,
	ctypes.POINTER(wintypes.DWORD),
	wintypes.DWORD,
]
SetupDiGetDevicePropertyW.restype = wintypes.BOOL

CM_Locate_DevNodeW = cfgmgr32.CM_Locate_DevNodeW
CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wintypes.ULONG), wintypes.LPWSTR, wintypes.ULONG]
CM_Locate_DevNodeW.restype = wintypes.ULONG

CM_Get_DevNode_PropertyW = cfgmgr32.CM_Get_DevNode_PropertyW
CM_Get_DevNode_PropertyW.argtypes = [
	wintypes.ULONG,
	ctypes.POINTER(DEVPROPKEY),
	ctypes.POINTER(wintypes.ULONG),
	ctypes.c_void_p,
	ctypes.POINTER(wintypes.ULONG),
	wintypes.ULONG,
]
CM_Get_DevNode_PropertyW.restype = wintypes.ULONG

BluetoothFindFirstRadio = bthprops.BluetoothFindFirstRadio
BluetoothFindFirstRadio.argtypes = [
	ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS),
	ctypes.POINTER(wintypes.HANDLE),
]
BluetoothFindFirstRadio.restype = ctypes.c_void_p

BluetoothFindNextRadio = bthprops.BluetoothFindNextRadio
BluetoothFindNextRadio.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
BluetoothFindNextRadio.restype = wintypes.BOOL

BluetoothFindRadioClose = bthprops.BluetoothFindRadioClose
BluetoothFindRadioClose.argtypes = [ctypes.c_void_p]
BluetoothFindRadioClose.restype = wintypes.BOOL

BluetoothFindFirstDevice = bthprops.BluetoothFindFirstDevice
BluetoothFindFirstDevice.argtypes = [
	ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS),
	ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
]
BluetoothFindFirstDevice.restype = ctypes.c_void_p

BluetoothFindNextDevice = bthprops.BluetoothFindNextDevice
BluetoothFindNextDevice.argtypes = [ctypes.c_void_p, ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
BluetoothFindNextDevice.restype = wintypes.BOOL

BluetoothFindDeviceClose = bthprops.BluetoothFindDeviceClose
BluetoothFindDeviceClose.argtypes = [ctypes.c_void_p]
BluetoothFindDeviceClose.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

BATTERY_FLAG_NO_SYSTEM_BATTERY = 0x80
BATTERY_FLAG_UNKNOWN = 0xFF


class SYSTEM_POWER_STATUS(ctypes.Structure):
	_fields_ = [
		("ACLineStatus", ctypes.c_ubyte),
		("BatteryFlag", ctypes.c_ubyte),
		("BatteryLifePercent", ctypes.c_ubyte),
		("SystemStatusFlag", ctypes.c_ubyte),
		("BatteryLifeTime", wintypes.DWORD),
		("BatteryFullLifeTime", wintypes.DWORD),
	]


def _has_system_battery() -> bool:
	"""Whether Windows reports a battery in this computer (a laptop or a tablet), False for a desktop PC.

	This is the same check NVDA uses to say "No system battery". If it fails or the status is
	unknown, a battery is assumed, so that the gesture of NVDA itself is left alone.
	"""
	status = SYSTEM_POWER_STATUS()
	if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
		return True
	if status.BatteryFlag == BATTERY_FLAG_UNKNOWN:
		return True
	return not status.BatteryFlag & BATTERY_FLAG_NO_SYSTEM_BATTERY


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get_instance_id(device_info_set: ctypes.c_void_p, devinfo: SP_DEVINFO_DATA) -> str | None:
	required_size = wintypes.DWORD(0)
	SetupDiGetDeviceInstanceIdW(device_info_set, ctypes.byref(devinfo), None, 0, ctypes.byref(required_size))
	last_error = ctypes.get_last_error()
	if last_error not in (0, ERROR_INSUFFICIENT_BUFFER) or required_size.value == 0:
		return None

	buffer = ctypes.create_unicode_buffer(required_size.value)
	if not SetupDiGetDeviceInstanceIdW(
		device_info_set,
		ctypes.byref(devinfo),
		buffer,
		required_size,
		ctypes.byref(required_size),
	):
		return None
	return buffer.value


def _read_registry_string(
	device_info_set: ctypes.c_void_p,
	devinfo: SP_DEVINFO_DATA,
	property_id: int,
) -> str | None:
	prop_type = wintypes.DWORD(0)
	required_size = wintypes.DWORD(0)
	SetupDiGetDeviceRegistryPropertyW(
		device_info_set,
		ctypes.byref(devinfo),
		property_id,
		ctypes.byref(prop_type),
		None,
		0,
		ctypes.byref(required_size),
	)
	last_error = ctypes.get_last_error()
	if last_error != ERROR_INSUFFICIENT_BUFFER or required_size.value == 0:
		return None

	buffer = (ctypes.c_byte * required_size.value)()
	if not SetupDiGetDeviceRegistryPropertyW(
		device_info_set,
		ctypes.byref(devinfo),
		property_id,
		ctypes.byref(prop_type),
		buffer,
		required_size,
		ctypes.byref(required_size),
	):
		return None

	raw = bytes(buffer)
	return raw.decode("utf-16-le", errors="ignore").rstrip("\x00") or None


def _read_device_property_string(
	device_info_set: ctypes.c_void_p,
	devinfo: SP_DEVINFO_DATA,
	property_key: DEVPROPKEY,
) -> str | None:
	prop_type = wintypes.ULONG(0)
	required_size = wintypes.DWORD(0)
	SetupDiGetDevicePropertyW(
		device_info_set,
		ctypes.byref(devinfo),
		ctypes.byref(property_key),
		ctypes.byref(prop_type),
		None,
		0,
		ctypes.byref(required_size),
		0,
	)
	last_error = ctypes.get_last_error()
	if last_error != ERROR_INSUFFICIENT_BUFFER or required_size.value == 0:
		return None

	buffer = (ctypes.c_byte * required_size.value)()
	if not SetupDiGetDevicePropertyW(
		device_info_set,
		ctypes.byref(devinfo),
		ctypes.byref(property_key),
		ctypes.byref(prop_type),
		buffer,
		required_size,
		ctypes.byref(required_size),
		0,
	):
		return None
	if prop_type.value != DEVPROP_TYPE_STRING:
		return None

	raw = bytes(buffer)
	return raw.decode("utf-16-le", errors="ignore").rstrip("\x00") or None


def _read_device_name(device_info_set: ctypes.c_void_p, devinfo: SP_DEVINFO_DATA) -> str | None:
	return (
		_read_device_property_string(device_info_set, devinfo, DEVPKEY_DEVICE_FRIENDLYNAME)
		or _read_device_property_string(device_info_set, devinfo, DEVPKEY_NAME)
		or _read_registry_string(device_info_set, devinfo, SPDRP_FRIENDLYNAME)
		or _read_registry_string(device_info_set, devinfo, SPDRP_DEVICEDESC)
	)


def _read_battery_percent(instance_id: str) -> int | None:
	devinst = wintypes.ULONG(0)
	cr = CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, CM_LOCATE_DEVNODE_NORMAL)
	if cr != CR_SUCCESS:
		return None

	prop_type = wintypes.ULONG(DEVPROP_TYPE_BYTE)
	value = ctypes.c_ubyte(0)
	size = wintypes.ULONG(ctypes.sizeof(value))
	cr = CM_Get_DevNode_PropertyW(
		devinst,
		ctypes.byref(DEVPKEY_BLUETOOTH_BATTERY),
		ctypes.byref(prop_type),
		ctypes.byref(value),
		ctypes.byref(size),
		0,
	)
	if cr != CR_SUCCESS or prop_type.value != DEVPROP_TYPE_BYTE:
		return None
	battery = int(value.value)
	if not 0 <= battery <= 100:
		return None
	return battery


def _read_devnode_status(instance_id: str) -> int | None:
	devinst = wintypes.ULONG(0)
	cr = CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, CM_LOCATE_DEVNODE_NORMAL)
	if cr != CR_SUCCESS:
		return None

	prop_type = wintypes.ULONG(DEVPROP_TYPE_UINT32)
	value = wintypes.ULONG(0)
	size = wintypes.ULONG(ctypes.sizeof(value))
	cr = CM_Get_DevNode_PropertyW(
		devinst,
		ctypes.byref(DEVPKEY_DEVICE_DEVNODE_STATUS),
		ctypes.byref(prop_type),
		ctypes.byref(value),
		ctypes.byref(size),
		0,
	)
	if cr != CR_SUCCESS or prop_type.value != DEVPROP_TYPE_UINT32:
		return None
	return int(value.value)


def _extract_bt_address(instance_id: str) -> str | None:
	upper_id = instance_id.upper()
	match = re.search(r"DEV_([0-9A-F]{12})", upper_id)
	if match:
		return match.group(1)

	match = re.search(r"&0&([0-9A-F]{12})_C", upper_id)
	if match:
		return match.group(1)

	match = re.search(r"_([0-9A-F]{12})\\[^\\]+$", upper_id)
	if match:
		return match.group(1)

	return None


def _format_bluetooth_address(raw_bytes: ctypes.Array[ctypes.c_ubyte]) -> str:
	return "".join(f"{raw_bytes[index]:02X}" for index in range(5, -1, -1))


def _detect_conn_type(instance_id: str) -> str:
	"""Return CONNTYPE_CLASSIC, CONNTYPE_LE, or CONNTYPE_UNKNOWN_TYPE from instance_id prefix."""
	upper_id = instance_id.upper()
	if upper_id.startswith("BTHENUM\\"):
		return CONNTYPE_CLASSIC
	if upper_id.startswith("BTHLE\\") or upper_id.startswith("BTHLEDEVICE\\"):
		return CONNTYPE_LE
	return CONNTYPE_UNKNOWN_TYPE


def _systemtime_to_datetime(st: SYSTEMTIME) -> datetime | None:
	"""Convert a SYSTEMTIME struct to a naive local datetime.

	Despite MSDN documentation, stLastUsed from bthprops.cpl stores local time,
	not UTC. We therefore return a naive datetime (no tzinfo) so it can be
	compared directly with datetime.now() without timezone offset errors.
	Returns None if the struct is zeroed out (device never used).
	"""
	try:
		if st.wYear == 0:
			return None
		return datetime(
			st.wYear, st.wMonth, st.wDay,
			st.wHour, st.wMinute, st.wSecond,
		)
	except ValueError:
		return None


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


def _collect_classic_connection_states() -> dict[str, tuple[bool, datetime | None]]:
	"""Enumerate all Bluetooth Classic radios.

	Returns dict mapping address → (is_connected, last_used_local).
	last_used_local is a naive datetime in local time, sourced from
	BLUETOOTH_DEVICE_INFO.stLastUsed which Windows persists in the Registry
	across reboots and NVDA restarts.

	FIX: radio_handle is set to None immediately after CloseHandle() inside the
	loop so the finally block cannot double-close the same handle.
	"""
	results: dict[str, tuple[bool, datetime | None]] = {}
	radio_params = BLUETOOTH_FIND_RADIO_PARAMS(dwSize=ctypes.sizeof(BLUETOOTH_FIND_RADIO_PARAMS))
	radio_handle = wintypes.HANDLE()
	radio_find_handle = BluetoothFindFirstRadio(ctypes.byref(radio_params), ctypes.byref(radio_handle))
	if not radio_find_handle:
		return results

	try:
		while True:
			search_params = BLUETOOTH_DEVICE_SEARCH_PARAMS(
				dwSize=ctypes.sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS),
				fReturnAuthenticated=True,
				fReturnRemembered=True,
				fReturnUnknown=True,
				fReturnConnected=True,
				fIssueInquiry=False,
				cTimeoutMultiplier=0,
				hRadio=radio_handle,
			)
			device_info = BLUETOOTH_DEVICE_INFO(dwSize=ctypes.sizeof(BLUETOOTH_DEVICE_INFO))
			device_find_handle = BluetoothFindFirstDevice(ctypes.byref(search_params), ctypes.byref(device_info))
			if device_find_handle:
				try:
					while True:
						address = _format_bluetooth_address(device_info.Address.rgBytes)
						is_connected = bool(device_info.fConnected)
						last_used = _systemtime_to_datetime(device_info.stLastUsed)
						results[address] = (is_connected, last_used)
						if not BluetoothFindNextDevice(device_find_handle, ctypes.byref(device_info)):
							break
				finally:
					BluetoothFindDeviceClose(device_find_handle)

			# Close and clear the handle before fetching the next radio so
			# the finally block below cannot double-close it.
			CloseHandle(radio_handle)
			radio_handle = None  # type: ignore[assignment]

			next_handle = wintypes.HANDLE()
			if not BluetoothFindNextRadio(radio_find_handle, ctypes.byref(next_handle)):
				break
			radio_handle = next_handle
	finally:
		if radio_handle:
			CloseHandle(radio_handle)
		BluetoothFindRadioClose(radio_find_handle)

	return results


def _connection_sort_rank(
	address: str | None,
	node_instance_id: str,
	root_instance_id: str | None,
	classic_states: dict[str, tuple[bool, datetime | None]],
) -> int:
	if address in classic_states:
		return CONNECTION_CONNECTED if classic_states[address][0] else CONNECTION_DISCONNECTED

	instance_ids = [node_instance_id]
	if root_instance_id and root_instance_id != node_instance_id:
		instance_ids.append(root_instance_id)
	for instance_id in instance_ids:
		status = _read_devnode_status(instance_id)
		if status is not None and status & DN_DEVICE_DISCONNECTED:
			return CONNECTION_DISCONNECTED

	return CONNECTION_UNKNOWN


# ---------------------------------------------------------------------------
# Main collection function
# Returns (name, battery, sort_rank, conn_type, last_used_local)
# ---------------------------------------------------------------------------

class BluetoothDevice(NamedTuple):
	"""One device of a scan."""

	name: str
	battery: int
	sort_rank: int
	conn_type: str
	last_used: datetime | None
	# Stable identity of the device: its Bluetooth address (or its instance ID). The name can change.
	key: str


def collect_bluetooth_battery() -> list[BluetoothDevice]:
	"""Collect battery info for all Bluetooth devices.

	Returns a list of BluetoothDevice (display name, battery percent, sort rank, connection type, last used
	time in local time, key) sorted by (sort_rank, name_lower).

	last_used_local is a naive datetime in local time sourced from
	BLUETOOTH_DEVICE_INFO.stLastUsed — a value Windows stores in the Registry
	and keeps across reboots and NVDA restarts. No separate monitoring timer
	is needed; the value is read fresh on every scan.
	"""
	device_info_set = SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
	if not device_info_set or device_info_set == INVALID_HANDLE_VALUE:
		raise OSError(f"SetupDiGetClassDevsW failed: {ctypes.get_last_error()}")

	root_names: dict[str, str] = {}
	root_instance_ids: dict[str, str] = {}
	root_conn_types: dict[str, str] = {}
	battery_candidates: list[tuple[str | None, str, int, str, str]] = []

	try:
		index = 0
		while True:
			devinfo = SP_DEVINFO_DATA()
			devinfo.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
			if not SetupDiEnumDeviceInfo(device_info_set, index, ctypes.byref(devinfo)):
				if ctypes.get_last_error() == ERROR_NO_MORE_ITEMS:
					break
				raise OSError(f"SetupDiEnumDeviceInfo failed: {ctypes.get_last_error()}")

			index += 1
			instance_id = _get_instance_id(device_info_set, devinfo)
			if not instance_id:
				continue

			upper_id = instance_id.upper()
			if not (
				upper_id.startswith("BTHENUM\\")
				or upper_id.startswith("BTHLE\\")
				or upper_id.startswith("BTHLEDEVICE\\")
			):
				continue

			conn_type = _detect_conn_type(instance_id)
			name = _read_device_name(device_info_set, devinfo) or instance_id
			address = _extract_bt_address(instance_id)
			if (upper_id.startswith("BTHENUM\\DEV_") or upper_id.startswith("BTHLE\\DEV_")) and address:
				root_names[address] = name
				root_instance_ids[address] = instance_id
				root_conn_types[address] = conn_type

			battery = _read_battery_percent(instance_id)
			if battery is not None:
				battery_candidates.append((address, name, battery, instance_id, conn_type))
	finally:
		SetupDiDestroyDeviceInfoList(device_info_set)

	classic_states = _collect_classic_connection_states()
	results: dict[str, BluetoothDevice] = {}
	for address, node_name, battery, instance_id, node_conn_type in battery_candidates:
		display_name = root_names.get(address or "", node_name)
		final_conn_type = root_conn_types.get(address or "", node_conn_type)
		key = address or instance_id
		sort_rank = _connection_sort_rank(
			address,
			instance_id,
			root_instance_ids.get(address or ""),
			classic_states,
		)
		last_used: datetime | None = None
		if address and address in classic_states:
			last_used = classic_states[address][1]
		results[key] = BluetoothDevice(display_name, battery, sort_rank, final_conn_type, last_used, key)

	return sorted(results.values(), key=lambda device: (device.sort_rank, device.name.lower()))


# ---------------------------------------------------------------------------
# Usage tracker (full charge -> next full charge, per device)
# ---------------------------------------------------------------------------

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
								history.append({
									"end": self._optional_number(record.get("end"), float),
									"secs": float(record["secs"]),
									"from": self._optional_number(record.get("from"), int),
									"to": self._optional_number(record.get("to"), int),
									"pos": self._optional_number(record.get("pos"), float),
									"elapsed": bool(record.get("elapsed", False)),
								})
						if not history and entry.get("last") is not None:
							# Written before the history existed: keep its last finished cycle.
							history.append({
								"end": None,
								"secs": float(entry["last"]),
								"from": self._optional_number(entry.get("last_from"), int),
								"to": None,
							})
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
						entry["history"].append({
							"end": recharged_at,
							"elapsed": entry["elapsed"],
							"pos": min((record["pos"] for record in entry["history"]), default=1.0) - 1,
							"secs": entry["active"],
							"from": entry["start_level"],
							"to": entry["min_level"],
						})
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
						**{name: (list(value) if isinstance(value, list) else value)
							for name, value in entry.items() if name.startswith("case_")},
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


# ---------------------------------------------------------------------------
# Battery statistics dialog
# ---------------------------------------------------------------------------

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


def _full_charge_seconds(secs: float, start: int | None, end: int | None) -> float | None:
	"""Estimated runtime on a full charge, from the battery points used during `secs` seconds."""
	if start is None or end is None or secs <= 0:
		return None
	drop = start - end
	if drop < _STATS_MIN_DROP:
		return None
	return secs * 100 / drop


def _format_full_charge(secs: float, start: int | None, end: int | None) -> str:
	life = _full_charge_seconds(secs, start, end)
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
	return level * sum(secs for secs, used in records) / sum(used for secs, used in records)


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
				_format_full_charge(current["secs"], current["from"], current["to"]),
				"",
				_describe_basis(current["elapsed"]),
			),
			who
			+ (
				_whole(current["secs"]),
				current["from"],
				current["to"],
				used,
				_whole(_full_charge_seconds(current["secs"], current["from"], current["to"])),
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
						_format_full_charge(record["secs"], record["from"], record["to"]),
						_format_timestamp(record["end"]),
						_describe_basis(bool(record.get("elapsed", False))),
					),
					who
					+ (
						_whole(record["secs"]),
						record["from"],
						record["to"],
						used,
						_whole(_full_charge_seconds(record["secs"], record["from"], record["to"])),
						_iso(record["end"]),
						_rounded(_cycle_drain_rate(record["secs"], record["from"], record["to"])),
					),
				)
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
		durations = [record["secs"] for record in history]
		runtimes = [
			runtime
			for runtime in (_full_charge_seconds(r["secs"], r["from"], r["to"]) for r in history)
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
			_("off") if current["ignored"] else _("on, elapsed time") if current["elapsed"] else _("on"),
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
		if mode == "cycles":
			return len(history)
		if mode == "current":
			return current["secs"]
		if mode == "average":
			return sum(record["secs"] for record in history) / len(history) if history else None
		if mode == "full_charge":
			runtimes = [
				runtime
				for runtime in (_full_charge_seconds(r["secs"], r["from"], r["to"]) for r in history)
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


class _StatsListCtrl(wx.ListCtrl):
	"""A virtual list: the text of a cell is only asked for when the cell is drawn.

	Several rows can be selected, as in any list: Control+Space toggles the current row.
	"""

	def __init__(self, parent, columns, height):
		super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL, size=(1000, height))
		# (id, label, width) of every column, and the positions of the columns that are shown.
		self.columns = columns
		self.visibleIndexes = []
		# The text rows that are shown, and a key for each one: (device key, cycle number or None).
		self.shownRows = []
		self.shownKeys = []

	def setVisible(self, ids):
		"""Show only the columns with these ids."""
		self.DeleteAllColumns()
		# The columns come in the order of ids, which the user can change.
		positions = {column[0]: index for index, column in enumerate(self.columns)}
		self.visibleIndexes = [positions[column_id] for column_id in ids if column_id in positions]
		for position, index in enumerate(self.visibleIndexes):
			column_id, label, width = self.columns[index]
			self.InsertColumn(position, label, width=width)
		self.Refresh()

	def visibleIds(self):
		return [self.columns[index][0] for index in self.visibleIndexes]

	def focusedKey(self):
		index = self.GetFocusedItem()
		return self.shownKeys[index] if 0 <= index < len(self.shownKeys) else None

	def selectedIndexes(self):
		indexes = []
		index = self.GetFirstSelected()
		while index != -1:
			indexes.append(index)
			index = self.GetNextSelected(index)
		return indexes

	def selectedKeys(self):
		return [self.shownKeys[index] for index in self.selectedIndexes()]

	def setRows(self, rows, keys, focusKey=None, selectedKeys=()):
		"""Show these rows. The focus goes to the row of focusKey if there is one, and the rows of
		selectedKeys are selected.
		"""
		previousFocus = max(self.GetFocusedItem(), 0)
		self.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
		self.shownRows = rows
		self.shownKeys = keys
		self.SetItemCount(len(rows))
		self.Refresh()
		if not rows:
			return
		selected = set(selectedKeys)
		for index, key in enumerate(keys):
			if key in selected:
				self.SetItemState(index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
		index = keys.index(focusKey) if focusKey in keys else min(previousFocus, len(rows) - 1)
		self.Focus(index)
		self.EnsureVisible(index)

	def OnGetItemText(self, item, column):
		return self.shownRows[item][self.visibleIndexes[column]]


class _ColumnsDialog(wx.Dialog):
	"""Choose and order the columns of the two statistics lists: each list of columns is a list of check boxes.

	Control+Shift+Up and Control+Shift+Down move the current column in its list.
	"""

	def __init__(self, parent, summaryColumns, summaryVisible, cycleColumns, cycleVisible):
		# Translators: title of the dialog to choose the columns of the statistics
		super().__init__(parent, title=_("Choose columns"))
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		self._lists = []
		groups = (
			# Translators: labels above the lists of columns that can be shown, hidden or moved
			(_("&Summary columns (Control+Shift+Up or Down moves a column):"), summaryColumns, summaryVisible),
			(_("&Cycle columns (Control+Shift+Up or Down moves a column):"), cycleColumns, cycleVisible),
		)
		for label, columns, visible in groups:
			names = {column[0]: column[1] for column in columns}
			# The shown columns come first, in their order, then the hidden ones. The required ones are not listed.
			shown = [column_id for column_id in visible if column_id in names and column_id not in _REQUIRED_COLUMNS]
			hidden = [
				column[0]
				for column in columns
				if column[0] not in _REQUIRED_COLUMNS and column[0] not in shown
			]
			ids = shown + hidden
			mainSizer.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
			checkList = gui.nvdaControls.CustomCheckListBox(self, choices=[names[column_id] for column_id in ids])
			checkList.CheckedItems = list(range(len(shown)))
			checkList.SetSelection(0)
			mainSizer.Add(checkList, 1, wx.EXPAND | wx.ALL, 8)
			self._lists.append((columns, ids, checkList))
		mainSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()
		# The hook sees Control+Shift+Up and Down before the list does.
		self.Bind(wx.EVT_CHAR_HOOK, self._onCharHook)
		self._lists[0][2].SetFocus()

	def _onCharHook(self, evt):
		"""Control+Shift+Up or Down moves the current column of the list that has the focus."""
		keyCode = evt.GetKeyCode()
		focus = self.FindFocus()
		if (
			keyCode in (wx.WXK_UP, wx.WXK_DOWN)
			and evt.ControlDown()
			and evt.ShiftDown()
			and not evt.AltDown()
			and any(focus == box for columns, ids, box in self._lists)
		):
			self._moveColumn(focus, -1 if keyCode == wx.WXK_UP else 1)
			return
		evt.Skip()

	def _moveColumn(self, checkList, step):
		"""Move the current column of a list up (step -1) or down (step 1). Its check box moves with it."""
		ids = next(ids for columns, ids, box in self._lists if box == checkList)
		index = checkList.GetSelection()
		if index == wx.NOT_FOUND:
			return
		target = index + step
		if not 0 <= target < len(ids):
			# The column is already at the end of the list.
			tones.beep(220, 60)
			return
		labels = (checkList.GetString(index), checkList.GetString(target))
		checked = (checkList.IsChecked(index), checkList.IsChecked(target))
		checkList.SetString(index, labels[1])
		checkList.SetString(target, labels[0])
		checkList.Check(index, checked[1])
		checkList.Check(target, checked[0])
		ids[index], ids[target] = ids[target], ids[index]
		checkList.SetSelection(target)
		# Translators: spoken after a column was moved in the list of columns. {number} is its new position and
		# {total} how many columns there are.
		ui.message(_("{number} of {total}").format(number=target + 1, total=len(ids)))

	def chosenIds(self):
		"""For each list, the ids of the columns to show, in order: the required ones, then the checked ones."""
		chosen = []
		for columns, ids, checkList in self._lists:
			checked = {ids[index] for index in checkList.CheckedItems}
			required = [column[0] for column in columns if column[0] in _REQUIRED_COLUMNS]
			chosen.append(required + [column_id for column_id in ids if column_id in checked])
		return chosen


class _AlertLevelDialog(wx.Dialog):
	"""Choose the low battery alert level of a device: the default, a level of its own, or no alert."""

	def __init__(self, parent, name, current, default, defaultOn=True):
		# Translators: title of the dialog to choose the low battery alert level of a device
		super().__init__(parent, title=_("Low battery alert level"))
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		mainSizer.Add(
			# Translators: label of the list of choices for the low battery alert of a device
			wx.StaticText(self, label=_("&Alert for {name}:").format(name=name)),
			0,
			wx.LEFT | wx.RIGHT | wx.TOP,
			8,
		)
		self._modeChoice = wx.Choice(
			self,
			choices=[
				# Translators: choices of the low battery alert of a device
				_("Use the default level ({level}%)").format(level=default)
				if defaultOn
				# Translators: choice of the low battery alert of a device when the default alert is turned off
				else _("Use the default (no alert, the low battery alert is off)"),
				_("Use a level of my own"),
				_("Never alert for this device"),
			],
		)
		self._modeChoice.SetSelection(0 if current is None else 2 if current == 0 else 1)
		self._modeChoice.Bind(wx.EVT_CHOICE, lambda evt: self._updateLevel())
		mainSizer.Add(self._modeChoice, 0, wx.EXPAND | wx.ALL, 8)
		# Translators: label of the field with the level of the low battery alert of a device
		mainSizer.Add(wx.StaticText(self, label=_("&Level (percent):")), 0, wx.LEFT | wx.RIGHT, 8)
		self._levelSpin = wx.SpinCtrl(self, min=5, max=50)
		self._levelSpin.SetValue(current if current else default)
		mainSizer.Add(self._levelSpin, 0, wx.EXPAND | wx.ALL, 8)
		mainSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self._updateLevel()
		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()
		self._modeChoice.SetFocus()

	def _updateLevel(self):
		self._levelSpin.Enable(self._modeChoice.GetSelection() == 1)

	def chosenLevel(self):
		"""The level chosen: None for the default, 0 for no alert, or a percentage."""
		mode = self._modeChoice.GetSelection()
		if mode == 0:
			return None
		return 0 if mode == 2 else self._levelSpin.GetValue()


class _CaseDialog(wx.Dialog):
	"""The charging case of true wireless earbuds: whether to alert, and how long the earbuds and the case last."""

	def __init__(self, parent, name, case, runtimeSeconds):
		# Translators: title of the dialog for the charging case of a device. {name} is the name of the device.
		super().__init__(parent, title=_("Charging case: {name}").format(name=name))
		self._case = case
		self._runtimeSeconds = runtimeSeconds
		hours = case["case_hours"] or (round(runtimeSeconds / 3600 * 2) / 2 if runtimeSeconds else 5.0)
		total = case["case_total"] or hours * 5
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		# Translators: check box of the charging case dialog: turns the estimate and the alert on for the device
		self._enabledBox = wx.CheckBox(self, label=_("&Alert about the charging case"))
		self._enabledBox.SetValue(case["case_enabled"])
		self._enabledBox.Bind(wx.EVT_CHECKBOX, lambda evt: self._update())
		mainSizer.Add(self._enabledBox, 0, wx.ALL, 8)
		# Translators: labels of the fields of the charging case dialog
		self._hoursSpin = self._addSpin(mainSizer, _("Earbuds &runtime per charge (hours):"), hours, 0.5, 100)
		self._totalSpin = self._addSpin(mainSizer, _("&Total runtime with the case (hours):"), total, 1, 500)
		self._leftSpin = self._addSpin(
			mainSizer, _("Alert &when fewer than this many charges are left:"), case["case_alert"], 0.5, 10
		)
		# Translators: button of the charging case dialog: fills the runtime of the earbuds from the statistics
		self._statsButton = wx.Button(self, label=_("&Use statistics"))
		self._statsButton.Bind(wx.EVT_BUTTON, self._onUseStatistics)
		mainSizer.Add(self._statsButton, 0, wx.ALL, 8)
		self._infoText = wx.StaticText(self, label="")
		mainSizer.Add(self._infoText, 0, wx.LEFT | wx.RIGHT, 8)
		note = wx.StaticText(
			self,
			# Translators: note at the end of the charging case dialog
			label=_(
				"The charges of the case are estimated from how many times the earbuds were recharged while "
				"connected to this computer, so the estimate is less accurate if you also use them with another "
				"device. The connection time of the device must be measured. After you charge the case, mark it "
				"as charged in the context menu of the statistics."
			),
		)
		note.Wrap(420)
		mainSizer.Add(note, 0, wx.ALL, 8)
		okButton = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)
		mainSizer.Add(okButton, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self._update()
		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()
		self._enabledBox.SetFocus()

	def _addSpin(self, mainSizer, label, value, minimum, maximum):
		mainSizer.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		spin = wx.SpinCtrlDouble(self, min=minimum, max=maximum, inc=0.5)
		spin.SetDigits(1)
		spin.SetValue(min(max(value, minimum), maximum))
		spin.Bind(wx.EVT_SPINCTRLDOUBLE, lambda evt: self._update())
		spin.Bind(wx.EVT_TEXT, lambda evt: self._update())
		mainSizer.Add(spin, 0, wx.EXPAND | wx.ALL, 8)
		return spin

	def _update(self):
		enabled = self._enabledBox.GetValue()
		for control in (self._hoursSpin, self._totalSpin, self._leftSpin):
			control.Enable(enabled)
		self._statsButton.Enable(enabled and self._runtimeSeconds is not None)
		hours = self._hoursSpin.GetValue()
		total = self._totalSpin.GetValue()
		lines = []
		if total > hours:
			# Translators: line of the charging case dialog. {count} is a number of charges, for example 4.2
			lines.append(
				_("Charges of the earbuds from a full case, from these runtimes: about {count}.").format(
					count=_format_count(total / hours - 1)
				)
			)
		capacity, rounds = _case_capacity(self._case)
		if rounds:
			# Translators: line of the charging case dialog. It replaces the figure from the runtimes in the alert.
			lines.append(
				_("Learned from your last {rounds} case rounds, charges per round: about {count}.").format(
					rounds=rounds, count=_format_count(capacity)
				)
			)
		self._infoText.SetLabel("\n".join(lines))
		self.Layout()

	def _onUseStatistics(self, evt):
		"""Fill the runtime of the earbuds with the full charge estimate of the statistics, to half an hour."""
		if self._runtimeSeconds is not None:
			self._hoursSpin.SetValue(min(max(round(self._runtimeSeconds / 3600 * 2) / 2, 0.5), 100))
			self._update()

	def _onOk(self, evt):
		if self._enabledBox.GetValue() and self._totalSpin.GetValue() <= self._hoursSpin.GetValue():
			gui.messageBox(
				# Translators: error in the charging case dialog
				_("The total runtime with the case must be longer than the runtime of the earbuds."),
				_("Charging case"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			self._totalSpin.SetFocus()
			return
		evt.Skip()

	def chosen(self):
		"""(alert on, runtime of the earbuds, total runtime, alert when fewer charges than this are left)."""
		return (
			self._enabledBox.GetValue(),
			self._hoursSpin.GetValue(),
			self._totalSpin.GetValue(),
			self._leftSpin.GetValue(),
		)


class UsageStatsDialog(wx.Dialog):
	"""Per-device summary and the list of recorded battery cycles."""

	def __init__(self, parent, devices):
		# Translators: title of the dialog that shows the recorded battery cycles
		super().__init__(parent, title=_("Bluetooth battery statistics"))
		section = config.conf["btBatterytics"]
		self._devices = list(devices)
		self._deviceSort = section["statsSortDevices"]
		self._cycleSort = section["statsSortCycles"]
		# What Export acts on: the "selected" rows, the "device" of the current row, or "all" rows.
		self._exportScope = "all"
		self._exportDetailed = section["statsExportDetailed"]
		# The devices whose finished cycles are shown. At first only the cycle in progress is shown.
		self._expanded = set()
		self._refreshing = False
		# The ids and labels of the columns of the row texts (the State column is not one of them).
		self._summaryTextColumns = [(column[0], column[1]) for column in _summary_columns()]
		self._cycleTextColumns = [(column[0], column[1]) for column in _cycle_columns() if column[0] != "state"]
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		# The two lists, each below its label, are put in this sizer in the order chosen by the user.
		self._listsSizer = wx.BoxSizer(wx.VERTICAL)
		mainSizer.Add(self._listsSizer, 1, wx.EXPAND)
		order = section["statsListsOrder"].split(",")
		self._listsOrder = order if sorted(order) == ["cycles", "summary"] else ["summary", "cycles"]
		self._summaryLabel, self.summaryList = self._addList(
			# Translators: label of the list with one summary line per device
			_("&Summary per device:"),
			_summary_columns(),
			"statsSummaryColumns",
			150,
		)
		self._cyclesLabel, self.cyclesList = self._addList(
			# Translators: label of the list with every recorded battery cycle
			_("&Cycles:"),
			_cycle_columns(),
			"statsCycleColumns",
			260,
		)
		self._refresh()
		self.cyclesList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda evt: self._toggleDevice())

		closeButton = wx.Button(self, wx.ID_CLOSE, label=_("&Close"))
		closeButton.SetDefault()
		closeButton.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CLOSE))
		self.SetEscapeId(wx.ID_CLOSE)
		mainSizer.Add(closeButton, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self._closeButton = closeButton
		self._arrangeLists()

		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()
		# The window opens on the list that comes first.
		(self.summaryList if self._listsOrder[0] == "summary" else self.cyclesList).SetFocus()

	def _addList(self, labelText, columns, configKey, height):
		"""Make a list and its label. They are placed by _arrangeLists."""
		# The label is created right before the list so screen readers use it as the list's name.
		label = wx.StaticText(self, label=labelText)
		statsList = _StatsListCtrl(self, columns, height)
		statsList.setVisible(_visible_columns(configKey, columns))
		statsList.Bind(wx.EVT_KEY_DOWN, self._onKeyDown)
		statsList.Bind(wx.EVT_CONTEXT_MENU, self._onContextMenu)
		return label, statsList

	def _arrangeLists(self):
		"""Put the two lists, each below its label, in the order of the user, also in the tab order."""
		parts = {
			"summary": (self._summaryLabel, self.summaryList),
			"cycles": (self._cyclesLabel, self.cyclesList),
		}
		windows = []
		self._listsSizer.Clear(False)
		for name in self._listsOrder:
			label, statsList = parts[name]
			self._listsSizer.Add(label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
			self._listsSizer.Add(statsList, 1, wx.EXPAND | wx.ALL, 8)
			windows += [label, statsList]
		# The tab order follows the order of creation, so it is set again.
		for previous, window in zip(windows, windows[1:]):
			window.MoveAfterInTabOrder(previous)
		self._closeButton.MoveAfterInTabOrder(windows[-1])
		self.Layout()

	def _refresh(self):
		"""Fill both lists from the devices, in the chosen order.

		The focus and the selection stay on the same rows when they are still there.
		"""
		summaryFocus = self.summaryList.focusedKey()
		summarySelected = self.summaryList.selectedKeys()
		cyclesFocus = self.cyclesList.focusedKey()
		cyclesSelected = self.cyclesList.selectedKeys()
		devices = _sort_devices(self._devices, self._deviceSort)
		self._deviceInfo = {key: current for key, history, current in devices}
		self._deviceNames = {key: _display_name(current) for key, history, current in devices}
		summaryRows = _build_usage_summary_rows(devices)
		self._cycleBlocks = _build_usage_cycle_blocks(devices, self._cycleSort)
		self._blocksByKey = {block[0]: block for block in self._cycleBlocks}
		# Every row of the lists, by key, with the rows of the cycles in the order of the devices.
		self._summaryOrder = [row.key for row in summaryRows]
		self._summaryRowsByKey = {row.key: row for row in summaryRows}
		cycleRows = [row for block in self._cycleBlocks for row in (block[1], *block[2])]
		self._cycleOrder = [row.key for row in cycleRows]
		self._cycleRowsByKey = {row.key: row for row in cycleRows}
		shownSummary = [row.text for row in summaryRows]
		shownCycles, cycleKeys = _flatten_cycle_blocks(self._cycleBlocks, self._expanded)
		# When nothing was selected (the first time), the current row is selected.
		if not summarySelected and self._summaryOrder:
			summarySelected = [summaryFocus if summaryFocus in self._summaryOrder else self._summaryOrder[0]]
		if not cyclesSelected and cycleKeys:
			cyclesSelected = [cyclesFocus if cyclesFocus in cycleKeys else cycleKeys[0]]
		self.summaryList.setRows(shownSummary, list(self._summaryOrder), summaryFocus, summarySelected)
		self.cyclesList.setRows(shownCycles, cycleKeys, cyclesFocus, cyclesSelected)

	def _reload(self):
		"""Read the devices again from the tracker, then fill the lists."""
		tracker = UsageTracker.current
		if tracker is not None:
			self._devices = tracker.get_rows()
		self._refresh()

	def _rowsByKey(self, statsList):
		return self._cycleRowsByKey if statsList is self.cyclesList else self._summaryRowsByKey

	def _textColumns(self, statsList):
		return self._cycleTextColumns if statsList is self.cyclesList else self._summaryTextColumns

	def _rowPairs(self, statsList, statsRow):
		"""The headers and the values of the columns of a row that are shown in its list."""
		columns = self._textColumns(statsList)
		positions = {column[0]: index for index, column in enumerate(columns)}
		indexes = [positions[column_id] for column_id in statsList.visibleIds() if column_id in positions]
		return [columns[index][1] for index in indexes], [statsRow.text[index] for index in indexes]

	def _moveList(self, statsList, step):
		"""Control+Shift+Left or Right: move the list that has the focus before or after the other one."""
		name = "cycles" if statsList is self.cyclesList else "summary"
		order = list(self._listsOrder)
		position = order.index(name)
		target = position + step
		if not 0 <= target < len(order):
			tones.beep(220, 60)
			return
		order[position], order[target] = order[target], order[position]
		self._listsOrder = order
		config.conf["btBatterytics"]["statsListsOrder"] = ",".join(order)
		self._arrangeLists()
		statsList.SetFocus()
		# Translators: spoken after a list or a row was moved. {number} is its new position and {total} how many
		# there are.
		ui.message(_("{number} of {total}").format(number=target + 1, total=len(order)))

	def _moveRow(self, statsList, step):
		"""Control+Shift+Up or Down: move the device of the current row, or a finished cycle of a device.

		A device is moved by its row of the summary list, or by its cycle in progress in the cycle list. A finished
		cycle is moved among the finished cycles of its device. Each needs the manual sort.
		"""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None:
			return
		deviceKey, number = key
		if statsList is self.cyclesList and number is not None:
			if self._cycleSort != "manual":
				# Translators: spoken when trying to move a cycle without the manual sort
				ui.message(_("To move cycles, choose Manual in the Sort menu, under Cycles by"))
				return
			order = [row.key[1] for row in self._blocksByKey[deviceKey][2]]
			position = order.index(number)
		else:
			if self._deviceSort != "manual":
				# Translators: spoken when trying to move a device without the manual sort
				ui.message(_("To move devices, choose Manual in the Sort menu, under Devices by"))
				return
			order = [rowKey[0] for rowKey in self._summaryOrder]
			position = order.index(deviceKey)
		target = position + step
		if not 0 <= target < len(order):
			# The row is already at the end of its list.
			tones.beep(220, 60)
			return
		order[position], order[target] = order[target], order[position]
		if statsList is self.cyclesList and number is not None:
			tracker.set_cycle_order(deviceKey, order)
		else:
			tracker.set_device_order(order)
		self._reload()
		ui.message(_("{number} of {total}").format(number=target + 1, total=len(order)))

	def _toggleDevice(self):
		"""Expand or collapse the finished cycles of the device of the current row of the cycle list."""
		key = self.cyclesList.focusedKey()
		if key is None:
			return
		deviceKey = key[0]
		if not self._blocksByKey[deviceKey][2]:
			# Translators: spoken when trying to expand a device that has no finished cycles
			ui.message(_("No earlier cycles"))
			return
		if deviceKey in self._expanded:
			self._expanded.discard(deviceKey)
			# Translators: spoken after the finished cycles of a device were hidden
			message = _("Collapsed")
		else:
			self._expanded.add(deviceKey)
			# Translators: spoken after the finished cycles of a device were shown
			message = _("Expanded")
		rows, keys = _flatten_cycle_blocks(self._cycleBlocks, self._expanded)
		# The focus goes to the row of the cycle in progress of the device, which is its first row.
		focus = (deviceKey, None)
		self.cyclesList.setRows(rows, keys, focus, self.cyclesList.selectedKeys() or [focus])
		ui.message(message)

	def _onKeyDown(self, evt):
		statsList = evt.GetEventObject()
		keyCode = evt.GetKeyCode()
		control = evt.ControlDown() and not evt.AltDown()
		if control and keyCode == ord("C"):
			# Control+C copies the current row, Control+Shift+C everything about the current device.
			self._copyCurrent(statsList, evt.ShiftDown())
		elif control and keyCode == wx.WXK_DELETE:
			# Control+Delete deletes the current row (or the selected rows), Control+Shift+Delete the device.
			self._deleteRows(statsList, evt.ShiftDown())
		elif control and not evt.ShiftDown() and keyCode == ord("E"):
			menu = self._exportMenu(statsList)
			statsList.PopupMenu(menu)
			menu.Destroy()
		elif control and evt.ShiftDown() and keyCode in (wx.WXK_UP, wx.WXK_DOWN):
			self._moveRow(statsList, -1 if keyCode == wx.WXK_UP else 1)
		elif control and evt.ShiftDown() and keyCode in (wx.WXK_LEFT, wx.WXK_RIGHT):
			self._moveList(statsList, -1 if keyCode == wx.WXK_LEFT else 1)
		elif control and evt.ShiftDown() and keyCode == ord("R"):
			self._markCaseCharged(statsList)
		elif keyCode == wx.WXK_F5 and not evt.HasAnyModifiers():
			self._startRefresh()
		elif keyCode == wx.WXK_F2 and not evt.HasAnyModifiers():
			self._renameDevice(statsList)
		elif keyCode == wx.WXK_SPACE and statsList is self.cyclesList and not evt.HasAnyModifiers():
			self._toggleDevice()
		else:
			evt.Skip()

	def _onContextMenu(self, evt):
		statsList = evt.GetEventObject()
		menu = wx.Menu()
		key = statsList.focusedKey()
		hasDevice = key is not None and key[0] in self._deviceInfo
		# First the items that have no key of their own (submenus, dialogs), then those that have one.
		if hasDevice:
			info = self._deviceInfo[key[0]]
			measureMenu = wx.Menu()
			# Translators: items of the Measuring menu of a device in the statistics. The second one counts the time
			# since the last recharge, for devices that are not always connected (for example a keyboard that also
			# uses a dongle), instead of the time the device is connected.
			measureItem = measureMenu.AppendCheckItem(wx.ID_ANY, _("&Measure this device"))
			measureItem.Check(not info["ignored"])
			self.Bind(wx.EVT_MENU, lambda e, deviceKey=key[0]: self._toggleMeasured(deviceKey), measureItem)
			elapsedItem = measureMenu.AppendCheckItem(
				wx.ID_ANY, _("Count &elapsed time (for devices that are not always connected)")
			)
			elapsedItem.Check(info["elapsed"])
			self.Bind(wx.EVT_MENU, lambda e, deviceKey=key[0]: self._toggleElapsed(deviceKey), elapsedItem)
			menu.AppendSubMenu(measureMenu, _("Meas&uring"))
			# Translators: the Alerts submenu of the context menu of the statistics lists
			menu.AppendSubMenu(self._alertsMenu(statsList, key[0]), _("&Alerts"))
		# Translators: items of the context menu of the statistics lists, some followed by their keys
		menu.AppendSubMenu(self._selectMenu(statsList), _("&Select"))
		menu.AppendSubMenu(self._sortMenu(), _("S&ort"))
		columnsItem = menu.Append(wx.ID_ANY, _("Choose &columns..."))
		self.Bind(wx.EVT_MENU, lambda e: self._chooseColumns(), columnsItem)
		menu.AppendSeparator()
		if statsList is self.cyclesList and key is not None and self._blocksByKey[key[0]][2]:
			# Translators: items of the context menu of the cycle list, followed by their key
			label = _("Co&llapse\tSpace") if key[0] in self._expanded else _("&Expand\tSpace")
			toggleItem = menu.Append(wx.ID_ANY, label)
			self.Bind(wx.EVT_MENU, lambda e: self._toggleDevice(), toggleItem)
		if hasDevice:
			renameItem = menu.Append(wx.ID_ANY, _("Rena&me device...\tF2"))
			self.Bind(wx.EVT_MENU, lambda e: self._renameDevice(statsList), renameItem)
		# The row moves only with the manual sort of its kind (devices, or the finished cycles of a device).
		cycleRow = statsList is self.cyclesList and key is not None and key[1] is not None
		if key is not None and (self._cycleSort if cycleRow else self._deviceSort) == "manual":
			# Translators: items of the context menu of the statistics lists, followed by their keys
			upItem = menu.Append(wx.ID_ANY, _("Move row u&p\tCtrl+Shift+Up"))
			downItem = menu.Append(wx.ID_ANY, _("Move row do&wn\tCtrl+Shift+Down"))
			self.Bind(wx.EVT_MENU, lambda e: self._moveRow(statsList, -1), upItem)
			self.Bind(wx.EVT_MENU, lambda e: self._moveRow(statsList, 1), downItem)
		beforeItem = menu.Append(wx.ID_ANY, _("Move list &before\tCtrl+Shift+Left"))
		afterItem = menu.Append(wx.ID_ANY, _("Move l&ist after\tCtrl+Shift+Right"))
		self.Bind(wx.EVT_MENU, lambda e: self._moveList(statsList, -1), beforeItem)
		self.Bind(wx.EVT_MENU, lambda e: self._moveList(statsList, 1), afterItem)
		copyRowItem = menu.Append(wx.ID_ANY, _("Copy &row\tCtrl+C"))
		copyDeviceItem = menu.Append(wx.ID_ANY, _("Copy &device\tCtrl+Shift+C"))
		self.Bind(wx.EVT_MENU, lambda e: self._copyCurrent(statsList, False), copyRowItem)
		self.Bind(wx.EVT_MENU, lambda e: self._copyCurrent(statsList, True), copyDeviceItem)
		if hasDevice and self._deviceInfo[key[0]]["case_enabled"]:
			# Translators: item of the context menu of the statistics lists, followed by its key
			markCaseItem = menu.Append(wx.ID_ANY, _("Mar&k case charged\tCtrl+Shift+R"))
			self.Bind(wx.EVT_MENU, lambda e: self._markCaseCharged(statsList), markCaseItem)
		menu.AppendSubMenu(self._exportMenu(statsList), _("E&xport\tCtrl+E"))
		refreshItem = menu.Append(wx.ID_ANY, _("Re&fresh\tF5"))
		self.Bind(wx.EVT_MENU, lambda e: self._startRefresh(), refreshItem)
		deleteRowItem = menu.Append(wx.ID_ANY, _("Dele&te row\tCtrl+Delete"))
		deleteDeviceItem = menu.Append(wx.ID_ANY, _("Delete de&vice\tCtrl+Shift+Delete"))
		self.Bind(wx.EVT_MENU, lambda e: self._deleteRows(statsList, False), deleteRowItem)
		self.Bind(wx.EVT_MENU, lambda e: self._deleteRows(statsList, True), deleteDeviceItem)
		statsList.PopupMenu(menu)
		menu.Destroy()

	def _selectMenu(self, statsList):
		menu = wx.Menu()
		# Translators: items of the Select menu of the statistics lists, some followed by their keys
		choices = (
			("toggle", _("&Toggle current row\tCtrl+Space")),
			("all", _("Select &all\tCtrl+A")),
			("none", _("Select &none")),
			("invert", _("&Invert selection")),
			("device", _("Select rows of this &device")),
		)
		for how, label in choices:
			item = menu.Append(wx.ID_ANY, label)
			self.Bind(wx.EVT_MENU, lambda e, how=how: self._selectRows(statsList, how), item)
		return menu

	def _selectRows(self, statsList, how):
		selected = wx.LIST_STATE_SELECTED
		if how == "all":
			statsList.SetItemState(-1, selected, selected)
		elif how == "none":
			statsList.SetItemState(-1, 0, selected)
		elif how == "invert":
			for index in range(statsList.GetItemCount()):
				statsList.SetItemState(index, 0 if statsList.IsSelected(index) else selected, selected)
		else:
			key = statsList.focusedKey()
			if key is None:
				return
			if how == "toggle":
				index = statsList.GetFocusedItem()
				statsList.SetItemState(index, 0 if statsList.IsSelected(index) else selected, selected)
			else:
				for index, rowKey in enumerate(statsList.shownKeys):
					if rowKey[0] == key[0]:
						statsList.SetItemState(index, selected, selected)
		# Translators: spoken after changing the selection in a statistics list
		ui.message(_("{count} selected").format(count=len(statsList.selectedIndexes())))

	def _sortMenu(self):
		menu = wx.Menu()
		groups = (
			# Translators: the two groups of the Sort menu of the statistics
			(_("&Devices by"), _device_sort_choices(), "_deviceSort", "statsSortDevices"),
			(_("&Cycles by"), _cycle_sort_choices(), "_cycleSort", "statsSortCycles"),
		)
		for groupLabel, choices, attribute, configKey in groups:
			subMenu = wx.Menu()
			for key, label in choices:
				item = subMenu.AppendRadioItem(wx.ID_ANY, label)
				item.Check(getattr(self, attribute) == key)
				self.Bind(
					wx.EVT_MENU,
					lambda e, key=key, label=label, attribute=attribute, configKey=configKey: self._setSort(
						attribute, configKey, key, label
					),
					item,
				)
			menu.AppendSubMenu(subMenu, groupLabel)
		return menu

	def _setSort(self, attribute, configKey, key, label):
		setattr(self, attribute, key)
		config.conf["btBatterytics"][configKey] = key
		tracker = UsageTracker.current
		if attribute == "_deviceSort" and key == "manual" and tracker is not None:
			# The manual order starts from the order that was in use.
			tracker.init_manual_order([deviceKey for deviceKey, number in self._summaryOrder])
			self._reload()
		else:
			self._refresh()
		# Translators: spoken after choosing how the statistics are sorted
		ui.message(_("Sorted by {order}").format(order=label))

	def _chooseColumns(self):
		summaryColumns = _summary_columns()
		cycleColumns = _cycle_columns()
		dialog = _ColumnsDialog(
			self,
			summaryColumns,
			self.summaryList.visibleIds(),
			cycleColumns,
			self.cyclesList.visibleIds(),
		)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			summaryIds, cycleIds = dialog.chosenIds()
		finally:
			dialog.Destroy()
		section = config.conf["btBatterytics"]
		section["statsSummaryColumns"] = ",".join(summaryIds)
		section["statsCycleColumns"] = ",".join(cycleIds)
		self.summaryList.setVisible(summaryIds)
		self.cyclesList.setVisible(cycleIds)

	def _startRefresh(self):
		"""Scan the devices again (in a background thread), then update the lists."""
		if self._refreshing:
			return
		self._refreshing = True
		# Translators: spoken when the statistics start refreshing
		ui.message(_("Refreshing"))
		threading.Thread(target=self._scanForRefresh, daemon=True).start()

	def _scanForRefresh(self):
		succeeded = True
		try:
			results = collect_bluetooth_battery()
			tracker = UsageTracker.current
			if tracker is not None:
				tracker.note_status(results)
				tracker.update(results, count=config.conf["btBatterytics"]["enableUsageTracking"])
		except Exception:
			log.exception("BT-Batterytics: refreshing the statistics failed")
			succeeded = False
		wx.CallAfter(self._finishRefresh, succeeded)

	def _finishRefresh(self, succeeded):
		self._refreshing = False
		try:
			if not succeeded:
				ui.message(_("Bluetooth battery detection failed."))
				return
			self._reload()
			# Translators: spoken after the statistics were refreshed
			ui.message(_("Refreshed"))
		except RuntimeError:
			# The window was closed in the meantime.
			pass

	def _renameDevice(self, statsList):
		"""Ask for a name for the device of the current row. An empty name goes back to the original one."""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None or key[0] not in self._deviceInfo:
			return
		info = self._deviceInfo[key[0]]
		with wx.TextEntryDialog(
			self,
			# Translators: question when renaming a device in the statistics. {name} is the name Windows gave.
			_("Name for {name} (leave empty to use the name Windows gave):").format(name=info["name"]),
			# Translators: title of the dialog to rename a device in the statistics
			_("Rename device"),
			value=info["alias"] or info["name"],
		) as dialog:
			if dialog.ShowModal() != wx.ID_OK:
				return
			alias = dialog.GetValue()
		# Choosing the original name again clears the alias.
		tracker.set_alias(key[0], "" if alias.strip() == info["name"] else alias)
		self._reload()
		# Translators: spoken after a device was renamed in the statistics
		ui.message(_("Renamed"))

	def _setAlertLevel(self, statsList):
		"""Ask for the low battery alert level of the device of the current row."""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None or key[0] not in self._deviceInfo:
			return
		info = self._deviceInfo[key[0]]
		section = config.conf["btBatterytics"]
		dialog = _AlertLevelDialog(
			self,
			_display_name(info),
			info["alert"],
			section["lowBatteryThreshold"],
			section["enableLowBatteryAlert"],
		)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			level = dialog.chosenLevel()
		finally:
			dialog.Destroy()
		tracker.set_alert(key[0], level)
		self._reload()
		# Translators: spoken after the low battery alert level of a device was chosen
		ui.message(_("Alert level set"))

	def _alertsMenu(self, statsList, deviceKey):
		"""The alerts of a device: the alerts to turn on or off, then the low battery level."""
		menu = wx.Menu()
		# Translators: items of the Alerts menu of a device in the statistics
		for flag, label in (
			("drop_alert", _("Battery level &drops")),
			("connect_alert", _("Device &connects")),
			("disconnect_alert", _("Device d&isconnects")),
		):
			item = menu.AppendCheckItem(wx.ID_ANY, label)
			item.Check(self._deviceInfo[deviceKey][flag])
			self.Bind(wx.EVT_MENU, lambda e, flag=flag: self._toggleAlertFlag(deviceKey, flag), item)
		# The low battery alert is not a check item: it opens a dialog (default, level of its own, or never).
		menu.AppendSeparator()
		levelItem = menu.Append(wx.ID_ANY, _("Low battery &level..."))
		self.Bind(wx.EVT_MENU, lambda e: self._setAlertLevel(statsList), levelItem)
		# Translators: item of the Alerts menu of a device in the statistics: opens the charging case dialog
		caseItem = menu.Append(wx.ID_ANY, _("C&harging case..."))
		self.Bind(wx.EVT_MENU, lambda e: self._setCase(statsList), caseItem)
		return menu

	def _toggleAlertFlag(self, deviceKey, flag):
		tracker = UsageTracker.current
		if tracker is None or deviceKey not in self._deviceInfo:
			return
		enabled = not self._deviceInfo[deviceKey][flag]
		tracker.set_alert_flag(deviceKey, flag, enabled)
		self._reload()
		if flag != "drop_alert" and _plugin_instance is not None:
			# The connection alerts need frequent checks: start them soon.
			_plugin_instance.restart_monitor()
		messages = {
			# Translators: spoken after turning an alert of a device on or off
			"drop_alert": (_("Level drop alert on"), _("Level drop alert off")),
			"connect_alert": (_("Connect alert on"), _("Connect alert off")),
			"disconnect_alert": (_("Disconnect alert on"), _("Disconnect alert off")),
		}
		ui.message(messages[flag][0] if enabled else messages[flag][1])

	def _setCase(self, statsList):
		"""Ask about the charging case of the device of the current row."""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None or key[0] not in self._deviceInfo:
			return
		info = self._deviceInfo[key[0]]
		history = next((rows for deviceKey, rows, current in self._devices if deviceKey == key[0]), [])
		dialog = _CaseDialog(self, _display_name(info), info, _average_full_charge_seconds(history))
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			enabled, hours, total, alertLeft = dialog.chosen()
		finally:
			dialog.Destroy()
		tracker.set_case(key[0], enabled, hours, total, alertLeft)
		if enabled:
			self._showCaseColumns()
			if _plugin_instance is not None:
				# The alert needs the background checks: start them soon.
				_plugin_instance.restart_monitor()
		self._reload()
		# Translators: spoken after the charging case of a device was set in the statistics
		ui.message(_("Charging case saved"))

	def _showCaseColumns(self):
		"""The first time a charging case is turned on, add its columns to the summary list. The user can hide them."""
		section = config.conf["btBatterytics"]
		if section["statsCaseColumnsShown"]:
			return
		section["statsCaseColumnsShown"] = True
		ids = _visible_columns("statsSummaryColumns", _summary_columns())
		ids += [column_id for column_id in _CASE_COLUMNS if column_id not in ids]
		section["statsSummaryColumns"] = ",".join(ids)
		self.summaryList.setVisible(ids)

	def _markCaseCharged(self, statsList):
		"""The charging case of the device of the current row was charged: count its charges from zero."""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None or key[0] not in self._deviceInfo:
			return
		if not self._deviceInfo[key[0]]["case_enabled"]:
			# Translators: spoken when marking the case as charged for a device that has no charging case alert
			ui.message(_("The charging case alert is off for this device"))
			return
		tracker.mark_case_charged(key[0])
		self._reload()
		# Translators: spoken after the charging case of a device was marked as charged
		ui.message(_("Case marked as charged"))

	def _toggleElapsed(self, deviceKey):
		"""Count the elapsed time since the last recharge, or the connected time, of a device."""
		tracker = UsageTracker.current
		if tracker is None or deviceKey not in self._deviceInfo:
			return
		elapsed = not self._deviceInfo[deviceKey]["elapsed"]
		tracker.set_elapsed(deviceKey, elapsed)
		if elapsed:
			self._showBasisColumn()
		self._reload()
		# Translators: spoken after choosing how the time of a device is counted
		ui.message(_("Counting elapsed time") if elapsed else _("Counting connected time"))

	def _showBasisColumn(self):
		"""The first time elapsed time is used, add the column of the time counted to the cycle list."""
		section = config.conf["btBatterytics"]
		if section["statsBasisColumnShown"]:
			return
		section["statsBasisColumnShown"] = True
		ids = _visible_columns("statsCycleColumns", _cycle_columns())
		if "basis" not in ids:
			ids.append("basis")
		section["statsCycleColumns"] = ",".join(ids)
		self.cyclesList.setVisible(ids)

	def _toggleMeasured(self, deviceKey):
		tracker = UsageTracker.current
		if tracker is None or deviceKey not in self._deviceInfo:
			return
		ignored = self._deviceInfo[deviceKey]["ignored"]
		tracker.set_ignored(deviceKey, not ignored)
		self._reload()
		# Translators: spoken after choosing whether the connection time of a device is measured
		ui.message(_("Measuring on") if ignored else _("Measuring off"))

	def _exportMenu(self, statsList):
		menu = wx.Menu()
		scopes = (
			# Translators: what the Export menu exports, one choice is checked
			("selected", _("Selected rows ({count})").format(count=len(statsList.selectedIndexes()))),
			("device", _("Current device")),
			("all", _("All rows")),
		)
		for scope, label in scopes:
			item = menu.AppendRadioItem(wx.ID_ANY, label)
			item.Check(self._exportScope == scope)
			self.Bind(wx.EVT_MENU, lambda e, scope=scope: setattr(self, "_exportScope", scope), item)
		menu.AppendSeparator()
		# Translators: a check box item of the Export menu. When checked, exports have extra columns with
		# exact values (seconds, percent, ISO dates) and the identity of the device.
		detailedItem = menu.AppendCheckItem(wx.ID_ANY, _("Include &detailed values"))
		detailedItem.Check(self._exportDetailed)
		self.Bind(wx.EVT_MENU, lambda e: self._setExportDetailed(not self._exportDetailed), detailedItem)
		menu.AppendSeparator()
		for toFile, groupLabel in ((False, _("&Copy to clipboard as")), (True, _("&Save to a file as"))):
			subMenu = wx.Menu()
			for fmt, label, extension in _export_formats():
				item = subMenu.Append(wx.ID_ANY, label)
				self.Bind(
					wx.EVT_MENU,
					lambda e, fmt=fmt, extension=extension, toFile=toFile: self._export(
						statsList, fmt, extension, toFile
					),
					item,
				)
			menu.AppendSubMenu(subMenu, groupLabel)
		# Translators: an item of the Export menu: make an HTML report and open it in the web browser
		browserItem = menu.Append(wx.ID_ANY, _("&Open as an HTML report in the browser"))
		self.Bind(wx.EVT_MENU, lambda e: self._openReport(statsList), browserItem)
		return menu

	def _setExportDetailed(self, detailed):
		self._exportDetailed = detailed
		config.conf["btBatterytics"]["statsExportDetailed"] = detailed

	def _exportTable(self, statsList):
		"""The title, headers and rows (values) to export from a list, according to the export scope.

		With detailed values, every column of the list and the extra columns of exact values are exported.
		Without, the columns that are shown in the list.
		"""
		cycles = statsList is self.cyclesList
		# Translators: names of the two statistics lists, used as the title of an export
		title = _("Cycles") if cycles else _("Summary per device")
		rowsByKey = self._rowsByKey(statsList)
		order = self._cycleOrder if cycles else self._summaryOrder
		key = statsList.focusedKey()
		if self._exportScope == "selected":
			keys = statsList.selectedKeys()
		elif self._exportScope == "device" and key is not None:
			keys = [rowKey for rowKey in order if rowKey[0] == key[0]]
		else:
			keys = list(order)
		statsRows = [rowsByKey[rowKey] for rowKey in keys if rowKey in rowsByKey]
		columns = self._textColumns(statsList)
		if self._exportDetailed:
			detailHeaders = _cycle_detail_headers() if cycles else _summary_detail_headers()
			headers = [column[1] for column in columns] + list(detailHeaders)
			rows = [row.text + row.detail for row in statsRows]
		else:
			positions = {column[0]: index for index, column in enumerate(columns)}
			indexes = [positions[column_id] for column_id in statsList.visibleIds() if column_id in positions]
			headers = [columns[index][1] for index in indexes]
			rows = [tuple(row.text[index] for index in indexes) for row in statsRows]
		return title, headers, rows, "cycles" if cycles else "summary"

	def _export(self, statsList, fmt, extension, toFile):
		"""Copy or save the rows chosen by the export scope, in a format."""
		title, headers, rows, name = self._exportTable(statsList)
		if not rows:
			# Translators: spoken when there is nothing to export
			ui.message(_("Nothing to export"))
			return
		text = _format_export(fmt, title, headers, rows)
		if not toFile:
			if api.copyToClip(text):
				# Translators: spoken after the statistics were copied to the clipboard
				ui.message(_("Copied {count} rows").format(count=len(rows)))
			else:
				ui.message(_("Failed to copy to clipboard."))
			return
		with wx.FileDialog(
			self,
			# Translators: title of the dialog to choose the file of an export
			_("Save statistics"),
			defaultFile=f"bluetooth-battery-{name}.{extension}",
			wildcard=f"*.{extension}|*.{extension}",
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		) as dialog:
			if dialog.ShowModal() != wx.ID_OK:
				return
			path = dialog.GetPath()
		if self._writeFile(path, fmt, text):
			# Translators: spoken after the statistics were saved to a file
			ui.message(_("Saved {count} rows").format(count=len(rows)))

	def _writeFile(self, path, fmt, text):
		try:
			# A byte order mark lets Excel read the accents and other letters of a CSV file correctly.
			with open(path, "w", encoding="utf-8-sig" if fmt == "csv" else "utf-8", newline="") as f:
				f.write(text)
		except OSError:
			log.exception("BT-Batterytics: failed to save the statistics")
			# Translators: spoken when saving the statistics to a file failed
			ui.message(_("Failed to save the file."))
			return False
		return True

	def _openReport(self, statsList):
		"""Make an HTML report of the rows chosen by the export scope and open it in the web browser."""
		title, headers, rows, name = self._exportTable(statsList)
		if not rows:
			ui.message(_("Nothing to export"))
			return
		path = os.path.join(tempfile.gettempdir(), f"bluetooth-battery-{name}.html")
		if not self._writeFile(path, "html", _format_export("html", title, headers, rows)):
			return
		try:
			os.startfile(path)
		except OSError:
			log.exception("BT-Batterytics: could not open the report")
			# Translators: spoken when the HTML report could not be opened in the browser
			ui.message(_("Failed to open the report."))

	def _copyCurrent(self, statsList, wholeDevice):
		key = statsList.focusedKey()
		statsRow = self._rowsByKey(statsList).get(key)
		if statsRow is None:
			return
		if wholeDevice:
			lines = [self._deviceNames.get(key[0], "")]
			summaryRow = self._summaryRowsByKey.get((key[0], None))
			if summaryRow is not None:
				headers, values = self._rowPairs(self.summaryList, summaryRow)
				lines.append(_format_row_text(headers[1:], values[1:]))
			for rowKey in self._cycleOrder:
				if rowKey[0] == key[0]:
					headers, values = self._rowPairs(self.cyclesList, self._cycleRowsByKey[rowKey])
					lines.append(_format_row_text(headers[1:], values[1:]))
			text = "\n".join(lines)
		else:
			headers, values = self._rowPairs(statsList, statsRow)
			text = _format_row_text(headers, values)
		if not api.copyToClip(text):
			ui.message(_("Failed to copy to clipboard."))
		elif wholeDevice:
			# Translators: spoken after copying everything about a device from the statistics
			ui.message(_("Device copied"))
		else:
			# Translators: spoken after copying a row of the statistics
			ui.message(_("Row copied"))

	def _deleteRows(self, statsList, wholeDevice):
		"""Delete the current row, the selected rows or, with wholeDevice, the device of the current row.

		On the cycle in progress this restarts the cycle from zero. A question comes first.
		"""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None:
			return
		selected = statsList.selectedKeys()
		targets = selected if not wholeDevice and len(selected) > 1 else [key]
		deleteDevices = set()
		restartCurrent = set()
		deleteCycles = {}
		if wholeDevice:
			deleteDevices.add(key[0])
		else:
			for deviceKey, number in targets:
				if statsList is self.summaryList:
					deleteDevices.add(deviceKey)
				elif number is None:
					restartCurrent.add(deviceKey)
				else:
					deleteCycles.setdefault(deviceKey, set()).add(number)
		restartCurrent -= deleteDevices
		for deviceKey in deleteDevices:
			deleteCycles.pop(deviceKey, None)
		cycleCount = sum(len(numbers) for numbers in deleteCycles.values())
		involved = deleteDevices | restartCurrent | set(deleteCycles)
		lines = []
		singleRow = len(targets) == 1 and not wholeDevice
		if len(involved) == 1 and not singleRow:
			# Translators: first line of the question before deleting statistics
			lines.append(_("Device: {name}").format(name=self._deviceNames.get(next(iter(involved)), "")))
		if singleRow:
			headers, values = self._rowPairs(statsList, self._rowsByKey(statsList)[key])
			lines.append(_format_row_text(headers, values))
		if deleteDevices:
			# Translators: line of the question before deleting statistics
			lines.append(_("Devices to delete with all their data: {count}").format(count=len(deleteDevices)))
		if restartCurrent:
			# Translators: line of the question before deleting statistics
			lines.append(_("Current cycles to restart from zero: {count}").format(count=len(restartCurrent)))
		if cycleCount:
			# Translators: line of the question before deleting statistics
			lines.append(_("Finished cycles to delete: {count}").format(count=cycleCount))
		# Translators: end of the question before deleting statistics
		message = "\n".join(lines) + "\n\n" + _("This cannot be undone. Continue?")
		answer = gui.messageBox(
			message,
			# Translators: title of the question before deleting statistics
			_("Confirm deletion"),
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
			self,
		)
		if answer != wx.YES:
			return
		for deviceKey in deleteDevices:
			tracker.delete_device(deviceKey)
		for deviceKey in restartCurrent:
			tracker.reset_current(deviceKey)
		for deviceKey, numbers in deleteCycles.items():
			tracker.delete_cycles(deviceKey, numbers)
		self._reload()
		# Translators: spoken after statistics were deleted
		ui.message(_("Deleted"))

_stats_dialog = None


def _show_usage_statistics(parent=None) -> None:
	"""Show the statistics window, or a message if nothing has been recorded yet."""
	global _stats_dialog
	if _stats_dialog is not None:
		# Already open: bring it forward instead of opening another one.
		_stats_dialog.Raise()
		return
	tracker = UsageTracker.current
	devices = tracker.get_rows() if tracker else []
	if not devices:
		gui.messageBox(
			_("No battery statistics have been recorded yet."),
			_("Bluetooth battery statistics"),
			wx.OK | wx.ICON_INFORMATION,
			parent,
		)
		return
	dialog = _stats_dialog = UsageStatsDialog(parent, devices)
	try:
		if parent is None:
			gui.mainFrame.prePopup()
		dialog.ShowModal()
	finally:
		if parent is None:
			gui.mainFrame.postPopup()
		dialog.Destroy()
		_stats_dialog = None


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------

confspec = {
	"reportConnected": "boolean(default=True)",
	"reportDisconnected": "boolean(default=False)",
	"reportUnknown": "boolean(default=False)",
	"showConnectionType": "boolean(default=False)",
	"showConnectionDuration": "boolean(default=False)",
	"enableUsageTracking": "boolean(default=True)",
	"statsSortDevices": "string(default='report')",
	"statsSortCycles": "string(default='newest')",
	"statsSummaryColumns": "string(default='')",
	"statsCycleColumns": "string(default='')",
	"statsExportDetailed": "boolean(default=True)",
	"historyMaxCycles": "integer(default=500, min=5, max=5000)",
	"historyMaxDays": "integer(default=0, min=0, max=3650)",
	"enableLowBatteryAlert": "boolean(default=True)",
	"lowBatteryThreshold": "integer(default=20, min=5, max=50)",
	"alertSpeech": "boolean(default=True)",
	"alertBeep": "boolean(default=False)",
	"alertCustomSound": "boolean(default=False)",
	"dropAlertStep": "integer(default=10, min=1, max=50)",
	"connectionCheckSeconds": "integer(default=15, min=5, max=300)",
	"reportCaseLeft": "boolean(default=False)",
	"statsCaseColumnsShown": "boolean(default=False)",
	"statsListsOrder": "string(default='summary,cycles')",
	"statsBasisColumnShown": "boolean(default=False)",
}
config.conf.spec["btBatterytics"] = confspec


def _take_over_legacy_settings() -> None:
	"""Take over, once, the settings saved under the former name of the add-on."""
	try:
		base = config.conf.profiles[0]
		legacy = base.get(_LEGACY_CONFIG_SECTION)
		if legacy is None or "btBatterytics" in base:
			return
		section = config.conf["btBatterytics"]
		for name, spec in confspec.items():
			if name not in legacy:
				continue
			kind = spec.split("(", 1)[0]
			raw = legacy[name]
			try:
				if kind == "boolean":
					value = raw if isinstance(raw, bool) else str(raw).strip().lower() == "true"
				elif kind == "integer":
					value = int(raw)
				else:
					value = str(raw)
			except ValueError:
				continue
			section[name] = value
	except Exception:
		log.exception("BT-Batterytics: could not take over the settings saved under the former name")


_take_over_legacy_settings()


def _upgrade_alert_settings() -> None:
	"""The alert sound mode (beep or sound file) of earlier versions becomes the check boxes of the alert methods."""
	try:
		saved = config.conf.profiles[0].get("btBatterytics")
		if saved is None or "alertSoundMode" not in saved:
			return
		custom = str(saved["alertSoundMode"]).strip().lower() == "custom"
		section = config.conf["btBatterytics"]
		section["alertBeep"] = not custom
		section["alertCustomSound"] = custom
		del saved["alertSoundMode"]
	except Exception:
		log.exception("BT-Batterytics: could not upgrade the alert settings")


_upgrade_alert_settings()


class BtBatteryticsSettingsPanel(gui.settingsDialogs.SettingsPanel):
	title = _("BT-Batterytics")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# --- Filter group ---
		self.reportConnectedCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Report &connected devices"))
		)
		self.reportConnectedCheckbox.SetValue(
			config.conf["btBatterytics"]["reportConnected"]
		)

		self.reportDisconnectedCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Report &disconnected devices"))
		)
		self.reportDisconnectedCheckbox.SetValue(
			config.conf["btBatterytics"]["reportDisconnected"]
		)

		self.reportUnknownCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Report &unknown status devices"))
		)
		self.reportUnknownCheckbox.SetValue(
			config.conf["btBatterytics"]["reportUnknown"]
		)

		# --- Display group ---
		self.showConnectionTypeCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Show connection &type (Classic / LE)"))
		)
		self.showConnectionTypeCheckbox.SetValue(
			config.conf["btBatterytics"]["showConnectionType"]
		)

		self.showConnectionDurationCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Show connection &duration"))
		)
		self.showConnectionDurationCheckbox.SetValue(
			config.conf["btBatterytics"]["showConnectionDuration"]
		)

		self.enableUsageTrackingCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Speak &total connection time since the last recharge (unchecked: current connection only)"))
		)
		self.enableUsageTrackingCheckbox.SetValue(
			config.conf["btBatterytics"]["enableUsageTracking"]
		)

		# Translators: label of a check box in the settings: adds the charges left in the charging case to the report
		self.reportCaseLeftCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Show the charging case estimate in the &report"))
		)
		self.reportCaseLeftCheckbox.SetValue(config.conf["btBatterytics"]["reportCaseLeft"])

		self.viewStatsButton = sHelper.addItem(wx.Button(self, label=_("&View battery statistics...")))
		self.viewStatsButton.Bind(wx.EVT_BUTTON, self.onViewStats)

		maxCyclesLabel = wx.StaticText(self, label=_("Keep at most this many finished cycles per &device:"))
		self.historyMaxCyclesSpinner = wx.SpinCtrl(self, min=5, max=5000)
		self.historyMaxCyclesSpinner.SetValue(config.conf["btBatterytics"]["historyMaxCycles"])
		sHelper.addItem(maxCyclesLabel)
		sHelper.addItem(self.historyMaxCyclesSpinner)

		maxDaysLabel = wx.StaticText(self, label=_("Delete finished cycles older than this many &days (0 keeps them all):"))
		self.historyMaxDaysSpinner = wx.SpinCtrl(self, min=0, max=3650)
		self.historyMaxDaysSpinner.SetValue(config.conf["btBatterytics"]["historyMaxDays"])
		sHelper.addItem(maxDaysLabel)
		sHelper.addItem(self.historyMaxDaysSpinner)

		# --- Low battery alert group ---
		self.enableLowBatteryAlertCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Enable &low battery alert (default for all devices)"))
		)
		self.enableLowBatteryAlertCheckbox.SetValue(
			config.conf["btBatterytics"]["enableLowBatteryAlert"]
		)
		self.enableLowBatteryAlertCheckbox.Bind(wx.EVT_CHECKBOX, self._onAlertToggle)

		thresholdLabel = wx.StaticText(self, label=_("Default low battery &threshold for devices (percent):"))
		self.lowBatteryThresholdSpinner = wx.SpinCtrl(self, min=5, max=50)
		self.lowBatteryThresholdSpinner.SetValue(
			config.conf["btBatterytics"]["lowBatteryThreshold"]
		)
		sHelper.addItem(thresholdLabel)
		sHelper.addItem(self.lowBatteryThresholdSpinner)

		# --- How alerts are given: the low battery alert, the level drop alerts and the connection alerts ---
		methodsLabel = wx.StaticText(self, label=_("Alert &methods (for all alerts):"))
		sHelper.addItem(methodsLabel)
		self.alertMethodsList = gui.nvdaControls.CustomCheckListBox(
			self,
			choices=[
				_("Speak the alert"),
				_("Play a double beep"),
				_("Play the sound of the alert (a .wav file in the sounds folder)"),
			],
		)
		section = config.conf["btBatterytics"]
		self.alertMethodsList.CheckedItems = [
			index
			for index, key in enumerate(("alertSpeech", "alertBeep", "alertCustomSound"))
			if section[key]
		]
		self.alertMethodsList.SetSelection(0)
		sHelper.addItem(self.alertMethodsList)

		# Translators: label of a button in the settings that opens the folder with the sound files of the alerts
		self.browseSoundsButton = sHelper.addItem(wx.Button(self, label=_("&Browse sound folder...")))
		self.browseSoundsButton.Bind(wx.EVT_BUTTON, self.onBrowseSounds)

		dropStepLabel = wx.StaticText(
			self, label=_("Level drop alerts: alert each time the battery drops by this many &points:")
		)
		self.dropAlertStepSpinner = wx.SpinCtrl(self, min=1, max=50)
		self.dropAlertStepSpinner.SetValue(config.conf["btBatterytics"]["dropAlertStep"])
		sHelper.addItem(dropStepLabel)
		sHelper.addItem(self.dropAlertStepSpinner)

		checkSecondsLabel = wx.StaticText(
			self,
			label=_("Check for device connection changes every this many &seconds (for the connect and disconnect alerts):"),
		)
		self.connectionCheckSpinner = wx.SpinCtrl(self, min=5, max=300)
		self.connectionCheckSpinner.SetValue(config.conf["btBatterytics"]["connectionCheckSeconds"])
		sHelper.addItem(checkSecondsLabel)
		sHelper.addItem(self.connectionCheckSpinner)

		# Initialize control states
		self._onAlertToggle(None)

	def _onAlertToggle(self, event):
		self.lowBatteryThresholdSpinner.Enable(self.enableLowBatteryAlertCheckbox.GetValue())

	def onViewStats(self, evt):
		_show_usage_statistics(self)

	def onBrowseSounds(self, evt):
		"""Open the folder with the sound files of the alerts in the file explorer."""
		folder = _sounds_dir()
		try:
			os.makedirs(folder, exist_ok=True)
			os.startfile(folder)
		except OSError:
			log.exception("BT-Batterytics: could not open the sounds folder")
			# Translators: spoken when the folder with the sound files of the alerts could not be opened
			ui.message(_("Failed to open the sounds folder."))

	def onSave(self):
		config.conf["btBatterytics"]["reportConnected"] = (
			self.reportConnectedCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["reportDisconnected"] = (
			self.reportDisconnectedCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["reportUnknown"] = (
			self.reportUnknownCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["showConnectionType"] = (
			self.showConnectionTypeCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["showConnectionDuration"] = (
			self.showConnectionDurationCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["enableUsageTracking"] = (
			self.enableUsageTrackingCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["reportCaseLeft"] = self.reportCaseLeftCheckbox.GetValue()
		config.conf["btBatterytics"]["historyMaxCycles"] = self.historyMaxCyclesSpinner.GetValue()
		config.conf["btBatterytics"]["historyMaxDays"] = self.historyMaxDaysSpinner.GetValue()
		if UsageTracker.current is not None:
			UsageTracker.current.prune_history()
		config.conf["btBatterytics"]["enableLowBatteryAlert"] = (
			self.enableLowBatteryAlertCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["lowBatteryThreshold"] = (
			self.lowBatteryThresholdSpinner.GetValue()
		)
		checkedMethods = set(self.alertMethodsList.CheckedItems)
		config.conf["btBatterytics"]["alertSpeech"] = 0 in checkedMethods
		config.conf["btBatterytics"]["alertBeep"] = 1 in checkedMethods
		config.conf["btBatterytics"]["alertCustomSound"] = 2 in checkedMethods
		config.conf["btBatterytics"]["dropAlertStep"] = self.dropAlertStepSpinner.GetValue()
		config.conf["btBatterytics"]["connectionCheckSeconds"] = self.connectionCheckSpinner.GetValue()
		if _plugin_instance is not None:
			_plugin_instance.restart_monitor()


# ---------------------------------------------------------------------------
# Global Plugin
# ---------------------------------------------------------------------------

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
		global _plugin_instance
		_plugin_instance = self

	def terminate(self):
		global _plugin_instance
		_plugin_instance = None
		self._stop_monitor()
		if self._gesture_timer is not None:
			self._gesture_timer.Stop()
			self._gesture_timer = None
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(BtBatteryticsSettingsPanel)
		except ValueError:
			pass
		super().terminate()

	# ------------------------------------------------------------------
	# Low-battery background monitor (every 5 minutes)
	# ------------------------------------------------------------------

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
		watch_connections = tracker.has_alert_flag("connect_alert") or tracker.has_alert_flag("disconnect_alert")
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
						_("{name} battery low: {battery}%").format(name=name, battery=device.battery)
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
						"Choose Yes to count the charges of the case from zero again, or No to keep counting."
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
						"Charge it together with the earbuds."
					).format(name=name, count=_format_count(left))
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

	# ------------------------------------------------------------------
	# Report helpers
	# ------------------------------------------------------------------

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
					name=name, conn_type=device.conn_type, battery=device.battery
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
					duration=duration_str
				)

			if conf["reportCaseLeft"]:
				case = self._usage_tracker.case_snapshot(device.key)
				case_left = _case_left(case) if case else None
				if case_left is not None:
					# Translators: appended to a device line. {count} is a number of charges, for example 2.2
					base = _("{device_info} (case charges left: about {count})").format(
						device_info=base, count=_format_count(case_left)
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

	# ------------------------------------------------------------------
	# Script
	# ------------------------------------------------------------------

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
		description=_("Press once to report battery, twice to copy to clipboard, three times to open settings."),
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
				BtBatteryticsSettingsPanel
			)
			return
		threading.Thread(
			target=self._handle_scan_action,
			args=(repeat_count,),
			daemon=True,
		).start()
