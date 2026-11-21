"""The statistics window: the two lists, their keys and menus, exports and deletions."""

from __future__ import annotations


import tempfile
import threading
import os
import addonHandler
import api
import logHandler
import ui
import wx
import gui
import config
import tones

from . import shared
from .bluetooth import collect_bluetooth_battery
from .dialogs import _AlertLevelDialog, _CaseDialog, _ColumnsDialog, _RechargeLevelDialog
from .stats import (
	_average_full_charge_seconds,
	_build_usage_cycle_blocks,
	_build_usage_summary_rows,
	_cycle_columns,
	_cycle_detail_headers,
	_cycle_sort_choices,
	_device_sort_choices,
	_display_name,
	_export_formats,
	_flatten_cycle_blocks,
	_format_export,
	_format_row_text,
	_sort_devices,
	_summary_columns,
	_summary_detail_headers,
	_visible_columns,
)
from .usage import UsageTracker, _CASE_COLUMNS

addonHandler.initTranslation()

log = logHandler.log


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
		self._cycleTextColumns = [
			(column[0], column[1]) for column in _cycle_columns() if column[0] != "state"
		]
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
				wx.ID_ANY,
				_("Count &elapsed time (for devices that are not always connected)"),
			)
			elapsedItem.Check(info["elapsed"])
			self.Bind(wx.EVT_MENU, lambda e, deviceKey=key[0]: self._toggleElapsed(deviceKey), elapsedItem)
			# Translators: item of the Measuring menu of a device: the level at which the user usually recharges it
			chargeItem = measureMenu.Append(wx.ID_ANY, _("Usual recharge &level..."))
			self.Bind(wx.EVT_MENU, lambda e: self._setChargeAt(statsList), chargeItem)
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
						attribute,
						configKey,
						key,
						label,
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
		if flag != "drop_alert" and shared.plugin is not None:
			# The connection alerts need frequent checks: start them soon.
			shared.plugin.restart_monitor()
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
			if shared.plugin is not None:
				# The alert needs the background checks: start them soon.
				shared.plugin.restart_monitor()
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

	def _setChargeAt(self, statsList):
		"""Ask for the level at which the user usually recharges the device of the current row."""
		tracker = UsageTracker.current
		key = statsList.focusedKey()
		if tracker is None or key is None or key[0] not in self._deviceInfo:
			return
		info = self._deviceInfo[key[0]]
		dialog = _RechargeLevelDialog(self, _display_name(info), info["charge_at"])
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			level = dialog.chosen()
		finally:
			dialog.Destroy()
		tracker.set_charge_at(key[0], level)
		self._reload()
		# Translators: spoken after the usual recharge level of a device was set (or turned off) in the statistics
		ui.message(_("Recharge level saved") if level else _("Recharge level off"))

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
						statsList,
						fmt,
						extension,
						toFile,
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
