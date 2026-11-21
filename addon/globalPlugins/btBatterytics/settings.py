"""The settings of the add-on: configuration, take-over of the former name, settings panel."""

from __future__ import annotations


import os
import addonHandler
import logHandler
import ui
import wx
import gui
import config

from . import shared
from .sounds import _sounds_dir
from .statswindow import _show_usage_statistics
from .usage import UsageTracker

addonHandler.initTranslation()

log = logHandler.log


_LEGACY_CONFIG_SECTION = "blueToothBatteryReport"


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
			wx.CheckBox(self, label=_("Report &connected devices")),
		)
		self.reportConnectedCheckbox.SetValue(
			config.conf["btBatterytics"]["reportConnected"],
		)

		self.reportDisconnectedCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Report &disconnected devices")),
		)
		self.reportDisconnectedCheckbox.SetValue(
			config.conf["btBatterytics"]["reportDisconnected"],
		)

		self.reportUnknownCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Report &unknown status devices")),
		)
		self.reportUnknownCheckbox.SetValue(
			config.conf["btBatterytics"]["reportUnknown"],
		)

		# --- Display group ---
		self.showConnectionTypeCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Show connection &type (Classic / LE)")),
		)
		self.showConnectionTypeCheckbox.SetValue(
			config.conf["btBatterytics"]["showConnectionType"],
		)

		self.showConnectionDurationCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Show connection &duration")),
		)
		self.showConnectionDurationCheckbox.SetValue(
			config.conf["btBatterytics"]["showConnectionDuration"],
		)

		self.enableUsageTrackingCheckbox = sHelper.addItem(
			wx.CheckBox(
				self,
				label=_(
					"Speak &total connection time since the last recharge (unchecked: current connection only)",
				),
			),
		)
		self.enableUsageTrackingCheckbox.SetValue(
			config.conf["btBatterytics"]["enableUsageTracking"],
		)

		# Translators: label of a check box in the settings: adds the charges left in the charging case to the report
		self.reportCaseLeftCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Show the charging case estimate in the &report")),
		)
		self.reportCaseLeftCheckbox.SetValue(config.conf["btBatterytics"]["reportCaseLeft"])

		self.viewStatsButton = sHelper.addItem(wx.Button(self, label=_("&View battery statistics...")))
		self.viewStatsButton.Bind(wx.EVT_BUTTON, self.onViewStats)

		maxCyclesLabel = wx.StaticText(self, label=_("Keep at most this many finished cycles per &device:"))
		self.historyMaxCyclesSpinner = wx.SpinCtrl(self, min=5, max=5000)
		self.historyMaxCyclesSpinner.SetValue(config.conf["btBatterytics"]["historyMaxCycles"])
		sHelper.addItem(maxCyclesLabel)
		sHelper.addItem(self.historyMaxCyclesSpinner)

		maxDaysLabel = wx.StaticText(
			self,
			label=_("Delete finished cycles older than this many &days (0 keeps them all):"),
		)
		self.historyMaxDaysSpinner = wx.SpinCtrl(self, min=0, max=3650)
		self.historyMaxDaysSpinner.SetValue(config.conf["btBatterytics"]["historyMaxDays"])
		sHelper.addItem(maxDaysLabel)
		sHelper.addItem(self.historyMaxDaysSpinner)

		# --- Low battery alert group ---
		self.enableLowBatteryAlertCheckbox = sHelper.addItem(
			wx.CheckBox(self, label=_("Enable &low battery alert (default for all devices)")),
		)
		self.enableLowBatteryAlertCheckbox.SetValue(
			config.conf["btBatterytics"]["enableLowBatteryAlert"],
		)
		self.enableLowBatteryAlertCheckbox.Bind(wx.EVT_CHECKBOX, self._onAlertToggle)

		thresholdLabel = wx.StaticText(self, label=_("Default low battery &threshold for devices (percent):"))
		self.lowBatteryThresholdSpinner = wx.SpinCtrl(self, min=5, max=50)
		self.lowBatteryThresholdSpinner.SetValue(
			config.conf["btBatterytics"]["lowBatteryThreshold"],
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
			self,
			label=_("Level drop alerts: alert each time the battery drops by this many &points:"),
		)
		self.dropAlertStepSpinner = wx.SpinCtrl(self, min=1, max=50)
		self.dropAlertStepSpinner.SetValue(config.conf["btBatterytics"]["dropAlertStep"])
		sHelper.addItem(dropStepLabel)
		sHelper.addItem(self.dropAlertStepSpinner)

		checkSecondsLabel = wx.StaticText(
			self,
			label=_(
				"Check for device connection changes every this many &seconds (for the connect and disconnect alerts):",
			),
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
		config.conf["btBatterytics"]["reportConnected"] = self.reportConnectedCheckbox.GetValue()
		config.conf["btBatterytics"]["reportDisconnected"] = self.reportDisconnectedCheckbox.GetValue()
		config.conf["btBatterytics"]["reportUnknown"] = self.reportUnknownCheckbox.GetValue()
		config.conf["btBatterytics"]["showConnectionType"] = self.showConnectionTypeCheckbox.GetValue()
		config.conf["btBatterytics"]["showConnectionDuration"] = (
			self.showConnectionDurationCheckbox.GetValue()
		)
		config.conf["btBatterytics"]["enableUsageTracking"] = self.enableUsageTrackingCheckbox.GetValue()
		config.conf["btBatterytics"]["reportCaseLeft"] = self.reportCaseLeftCheckbox.GetValue()
		config.conf["btBatterytics"]["historyMaxCycles"] = self.historyMaxCyclesSpinner.GetValue()
		config.conf["btBatterytics"]["historyMaxDays"] = self.historyMaxDaysSpinner.GetValue()
		if UsageTracker.current is not None:
			UsageTracker.current.prune_history()
		config.conf["btBatterytics"]["enableLowBatteryAlert"] = self.enableLowBatteryAlertCheckbox.GetValue()
		config.conf["btBatterytics"]["lowBatteryThreshold"] = self.lowBatteryThresholdSpinner.GetValue()
		checkedMethods = set(self.alertMethodsList.CheckedItems)
		config.conf["btBatterytics"]["alertSpeech"] = 0 in checkedMethods
		config.conf["btBatterytics"]["alertBeep"] = 1 in checkedMethods
		config.conf["btBatterytics"]["alertCustomSound"] = 2 in checkedMethods
		config.conf["btBatterytics"]["dropAlertStep"] = self.dropAlertStepSpinner.GetValue()
		config.conf["btBatterytics"]["connectionCheckSeconds"] = self.connectionCheckSpinner.GetValue()
		if shared.plugin is not None:
			shared.plugin.restart_monitor()
