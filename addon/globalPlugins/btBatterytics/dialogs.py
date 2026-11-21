"""The small dialogs of the statistics window: columns, alert level, recharge level, charging case."""

from __future__ import annotations


import addonHandler
import ui
import wx
import gui
import tones

from .stats import _REQUIRED_COLUMNS, _format_count
from .usage import _case_capacity

addonHandler.initTranslation()


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
			(
				_("&Summary columns (Control+Shift+Up or Down moves a column):"),
				summaryColumns,
				summaryVisible,
			),
			(_("&Cycle columns (Control+Shift+Up or Down moves a column):"), cycleColumns, cycleVisible),
		)
		for label, columns, visible in groups:
			names = {column[0]: column[1] for column in columns}
			# The shown columns come first, in their order, then the hidden ones. The required ones are not listed.
			shown = [
				column_id
				for column_id in visible
				if column_id in names and column_id not in _REQUIRED_COLUMNS
			]
			hidden = [
				column[0]
				for column in columns
				if column[0] not in _REQUIRED_COLUMNS and column[0] not in shown
			]
			ids = shown + hidden
			mainSizer.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
			checkList = gui.nvdaControls.CustomCheckListBox(
				self,
				choices=[names[column_id] for column_id in ids],
			)
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


class _RechargeLevelDialog(wx.Dialog):
	"""The battery level at which the user usually recharges a device. 0 means none (the whole battery)."""

	def __init__(self, parent, name, current):
		# Translators: title of the dialog for the usual recharge level of a device. {name} is the name of the device.
		super().__init__(parent, title=_("Usual recharge level: {name}").format(name=name))
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		note = wx.StaticText(
			self,
			# Translators: explanation in the dialog of the usual recharge level
			label=_(
				"Some devices report a battery level that does not go down evenly. For example, the level stays "
				"at 100 percent for a long time, then falls quickly, and the device stops working at 55 or 60 "
				"percent. If you recharge such a device at a level that is safe for you, enter it here. The "
				"estimates of the statistics (full charge, time left) are then calculated down to that level, "
				"instead of down to 0 percent, so they are much closer to the time between your recharges. "
				"Leave 0 for a device whose level goes down evenly.",
			),
		)
		note.Wrap(420)
		mainSizer.Add(note, 0, wx.ALL, 8)
		# Translators: label of the field of the usual recharge level
		mainSizer.Add(
			wx.StaticText(self, label=_("&Level at which you recharge (percent, 0 for none):")),
			0,
			wx.LEFT | wx.RIGHT,
			8,
		)
		self._spin = wx.SpinCtrl(self, min=0, max=95)
		self._spin.SetValue(current)
		mainSizer.Add(self._spin, 0, wx.EXPAND | wx.ALL, 8)
		mainSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()
		self._spin.SetFocus()

	def chosen(self) -> int:
		return self._spin.GetValue()


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
			mainSizer,
			_("Alert &when fewer than this many charges are left:"),
			case["case_alert"],
			0.5,
			10,
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
				"as charged in the context menu of the statistics.",
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
					count=_format_count(total / hours - 1),
				),
			)
		capacity, rounds = _case_capacity(self._case)
		if rounds:
			# Translators: line of the charging case dialog. It replaces the figure from the runtimes in the alert.
			lines.append(
				_("Learned from your last {rounds} case rounds, charges per round: about {count}.").format(
					rounds=rounds,
					count=_format_count(capacity),
				),
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
