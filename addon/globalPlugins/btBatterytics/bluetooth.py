"""Reading the Bluetooth devices and their battery levels from Windows."""

from __future__ import annotations


import ctypes
import re
from ctypes import wintypes
from datetime import datetime
from typing import NamedTuple
import addonHandler


addonHandler.initTranslation()


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
			st.wYear,
			st.wMonth,
			st.wDay,
			st.wHour,
			st.wMinute,
			st.wSecond,
		)
	except ValueError:
		return None


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
			device_find_handle = BluetoothFindFirstDevice(
				ctypes.byref(search_params),
				ctypes.byref(device_info),
			)
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
