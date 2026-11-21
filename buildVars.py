# Build customizations
# Change this file instead of sconstruct or manifest files, whenever possible.

from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries, SpeechDictionaries

# Since some strings in `addon_info` are translatable,
# we need to include them in the .po files.
# Gettext recognizes only strings given as parameters to the `_` function.
# To avoid initializing translations in this module we simply import a "fake" `_` function
# which returns whatever is given to it as an argument.
from site_scons.site_tools.NVDATool.utils import _


# Add-on information variables
addon_info = AddonInfo(
	# add-on Name/identifier, internal for NVDA
	addon_name="btBatterytics",
	# Add-on summary/title, usually the user visible name of the add-on
	# Translators: Summary/title for this add-on
	# to be shown on installation and add-on information found in add-on store
	addon_summary=_("BT-Batterytics"),
	# Add-on description
	# Translators: Long description to be shown for this add-on on add-on information from add-on store
	addon_description=_(
		"BT-Batterytics reports the battery level of your Bluetooth devices, remembers how long "
		"each device lasts between two recharges, and shows statistics about it. It is a modified "
		"version of BlueToothBatteryReport by haitun001 and cary-rowen.\n"
		"\n"
		"Battery report\n"
		"Press NVDA+Alt+B (NVDA+Shift+B on a computer that has no battery, such as a desktop PC) "
		"to hear the battery level of every Bluetooth device that Windows can read it from. "
		"Press twice to copy the report to the clipboard, three times to open the settings. "
		"Devices are announced in this order: connected, unknown, disconnected. You choose which "
		"of these groups are announced, and whether the connection type (Classic or LE) and the "
		"connection time are included. Only devices that report their battery level to Windows "
		"can be listed.\n"
		"\n"
		"Connection time and statistics\n"
		"The add-on measures how long each device is connected between two recharges, so you can "
		"see how long it really lasts on one charge. For a device that is often not connected, such "
		"as a keyboard that also uses a dongle, it can count the elapsed time instead. The statistics "
		"window shows, for every device "
		"and every recharge cycle, the connected time, the battery used, the drain rate, the "
		"estimated runtime on a full charge, the trend over the latest cycles and the estimated "
		"time left now. You can give devices names of your own, sort the lists and choose their "
		"columns, and export the statistics to the clipboard or to a file as plain text, Markdown, "
		"CSV, tab-separated values, JSON or HTML, or open them as a report in your web browser. "
		"Open the window from the settings, or assign a key to the command Open the Bluetooth "
		"battery statistics in the Input Gestures dialog. For a device whose battery level does not "
		"go down evenly, you can set the level at which you usually recharge it, so that the "
		"estimates stay realistic.\n"
		"\n"
		"Alerts\n"
		"Each device can have its own alerts: low battery, battery level drops, device connects "
		"and device disconnects. For true wireless earbuds, the add-on can also estimate how many "
		"charges are left in the charging case and warn you when to charge it. An alert can be "
		"spoken, played as a double beep, or played as a "
		"sound file, and the sound files can be replaced with your own. A low battery alert also "
		"shows a warning dialog. A background check runs every five minutes, and more often while "
		"a device has a connect or disconnect alert.\n"
		"\n"
		"Everything is set in NVDA settings, in the BT-Batterytics category. The records stay on "
		"your computer, in the NVDA configuration folder.\n"
		"\n"
		"Credits: the ideas and the testing with NVDA are by NVDATH. All the modifications to the "
		"code of the original add-on were written by Claude, an AI assistant made by Anthropic, "
		"following the instructions of NVDATH.",
	),
	# version
	addon_version="1.0.0",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_(
		# CHANGELOG-START
        """First release as BT-Batterytics, a modified version of BlueToothBatteryReport 0.4 by haitun001 and cary-rowen. It keeps its own single-file code: it does not include the refactoring of version 0.4.

The ideas and the testing with NVDA are by NVDATH. All the modifications to the code were written by Claude, an AI assistant made by Anthropic, following the instructions of NVDATH.

### Reporting

- The report runs in a background thread, so NVDA does not freeze while the devices are scanned.
- Press the hotkey once to read the report, twice to copy it to the clipboard, three times to open the settings.
- The default hotkey is NVDA+Shift+B on a computer without a battery (a desktop PC) and NVDA+Alt+B on a computer with a battery (a laptop or tablet), so that NVDA's own battery command is left alone. The choice is made when NVDA starts. If Windows cannot tell, a battery is assumed.
- A settings panel in NVDA settings. Devices to report can be chosen by status: connected, unknown, disconnected.
- Optional connection type (Classic or LE) after the device name.
- Optional connection duration, as reported by Windows (Bluetooth Classic devices only).
- Optional total connection time since the last recharge, remembered across disconnections and NVDA restarts, which also works for LE devices.
- Optional estimate of the charges left in the charging case of true wireless earbuds.
- Names that you give to devices are used in the report and in the alerts.
- Fixed: the Bluetooth radio handle could be closed twice while reading the connection states.

### Connection time tracking

- The connected time of each device is counted between two recharges. A recharge is detected when the battery rises at least 15 points above the lowest level of the cycle, so devices that never reach 100% work too.
- Time is not counted while the device is disconnected, while the battery level rises, or over gaps longer than 15 minutes (for example while the computer sleeps).
- For Bluetooth Classic devices the total is never smaller than the connection time reported by Windows.
- Finished cycles are saved in `btBatterytics_usage.json` in the NVDA configuration folder. Limits can be set for the number of cycles kept per device and for their age.
- Devices are identified by their Bluetooth address: devices with the same name do not share data, and a renamed device keeps its data.
- The measurement of a device can be stopped without losing its data.
- Devices that are not always connected, such as a tri-mode keyboard that also uses a dongle, can count the elapsed time since the last recharge instead of the connected time. It is chosen for each device in the Measuring menu. The time of a cycle runs until the battery level was last seen dropping, a recharge is placed halfway between two readings, and each cycle remembers how its time was counted.
- Durations of two days or more are shown in days.
- A usual recharge level for each device, for devices whose reported battery level does not go down evenly (for example a keyboard that stops working at 55 to 60% and is recharged at about 70%). The estimates of the full charge and of the time left are then calculated down to that level instead of down to 0%.

### Statistics window

- Opened from the settings or by a command of the Input Gestures dialog (no gesture by default).
- A summary list with one row per device and a cycle list. Both are virtual lists, so they stay fast with many cycles.
- Summary columns: status, measuring, alerts, cycles, average, shortest, longest, full charge estimate, drain rate, recharge interval, last recharge, trend, time left estimate. Cycle columns: cycle, state, duration, battery, drain rate, full charge estimate, end.
- In the cycle list only the cycle in progress of each device is shown. Space, double-click or the context menu expands or collapses its finished cycles.
- Devices are listed in the order of the spoken report. F5 scans again and updates the window.
- The columns of both lists can be shown, hidden and moved (Control+Shift+Up and Control+Shift+Down in the Choose columns dialog). The order is used to show, copy and export them.
- Manual sort of the devices and of the finished cycles: Control+Shift+Up and Control+Shift+Down move a device, or a finished cycle of an expanded device. A new device is put first.
- Control+Shift+Left and Control+Shift+Right move the two lists, and the window opens on the first one.
- Context menu and keys (in the menu, the commands without a key come first): select (several rows, Control+Space, Control+A), copy a row or a device (Control+C, Control+Shift+C), delete a row or a device after a question (Control+Delete, Control+Shift+Delete), rename a device (F2), measure or not, choose the columns, sort the devices and the cycles (the choices are remembered), alerts of the device.
- Export (Control+E) of the selected rows, the current device or all rows, copied to the clipboard or saved to a file, as plain text, Markdown, CSV, tab-separated values, JSON or HTML, or opened as an HTML report in the browser. Detailed values (exact seconds, percentages, ISO dates, device identity) are included by default. Only the standard library of Python is used.

### Alerts

- Low battery alert. The setting is the default for all devices, with a default level. Each device can follow it, have a level of its own (it alerts even if the default is off), or never alert. The choice is made in a dialog of the Alerts menu of the device.
- Level drop alert for each device: alerts each time the battery has dropped by a number of points (10 by default).
- Connect and disconnect alerts for each device. The devices are checked every few seconds while one of these alerts is on.
- The alert methods are chosen once for all alerts and can be combined: speech (on by default), a double beep, and the sound of the alert, a .wav file of the `sounds` folder of the add-on (`lowBattery.wav`, `levelDrop.wav`, `deviceConnected.wav`, `deviceDisconnected.wav`, `chargingCase.wav`). A beep replaces a missing file.
- The low battery alert also shows a warning dialog.
- A level drop alert is not given together with a low battery alert of the same device, and the sounds of several alerts play one after another.
- A Browse sound folder button in the settings opens the folder of the sound files, to replace them. The sounds that come with the add-on are from Pixabay, see the readme for the credits.
- Charging case estimate for true wireless earbuds, off by default and set for each device. The add-on counts how many times the case charged the earbuds from the recharges it sees, and alerts when the earbuds are low and the case is nearly empty, so that you charge both together. After the alert, the next time the earbuds are seen recharged, a question asks whether you charged the case, and Yes counts from zero again (Mark case charged, Control+Shift+R, does the same at any time). The typical size of the case is learned from your rounds. It is an estimate, and works best if the earbuds are used mainly with this computer.

### Changed

- Renamed to BT-Batterytics (add-on ID `btBatterytics`). The data and the settings saved under the former name are taken over the first time the add-on runs.
- The alert sound mode (beep or sound file) of earlier versions is replaced by the alert methods.
- The "Only report connected devices" option of version 0.4 is replaced by one option for each status.""",
        # CHANGELOG-END
	),
	# Author(s)
	addon_author="NVDATH, based on BlueToothBatteryReport by haitun001 and cary-rowen",
	# URL for the add-on documentation support
	addon_url="https://github.com/NVDATH/BT-Batterytics",
	# URL for the add-on repository where the source code can be found
	addon_sourceURL="https://github.com/NVDATH/BT-Batterytics",
	# Documentation file name
	addon_docFileName="readme.html",
	# Minimum NVDA version supported (e.g. "2019.3.0", minor version is optional)
	addon_minimumNVDAVersion="2025.1.0",
	# Last NVDA version supported/tested (e.g. "2024.4.0", ideally more recent than minimum version)
	addon_lastTestedNVDAVersion="2026.3.1",
	# Add-on update channel (default is None, denoting stable releases,
	# and for development releases, use "dev".)
	# Do not change unless you know what you are doing!
	addon_updateChannel=None,
	# Add-on license such as GPL 2
	addon_license="GPL 2",
	# URL for the license document the ad-on is licensed under
	addon_licenseURL="https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
)

# Define the python files that are the sources of your add-on.
# You can either list every file (using ""/") as a path separator,
# or use glob expressions.
# For example to include all files with a ".py" extension from the "globalPlugins" dir of your add-on
# the list can be written as follows:
# pythonSources = ["addon/globalPlugins/*.py"]
# For more information on SCons Glob expressions please take a look at:
# https://scons.org/doc/production/HTML/scons-user/apd.html
# "**" matches any number of folders, so these patterns cover every shape of global plugin:
# a single file (globalPlugins/name.py), a package (globalPlugins/name/__init__.py) and the
# sub-packages inside it. Patterns that match nothing, such as installTasks.py when there is none, are harmless.
pythonSources: list[str] = [
	"addon/globalPlugins/**/*.py",
	"addon/installTasks.py",
]

# Files that contain strings for translation. Usually your python sources
i18nSources: list[str] = pythonSources + ["buildVars.py"]

# Files that will be ignored when building the nvda-addon file
# Paths are relative to the addon directory, not to the root directory of your addon sources.
# You can either list every file (using ""/") as a path separator,
# or use glob expressions.
excludedFiles: list[str] = [
	# A pattern is matched from the right end of the path, so these work at any depth of folders.
	"__pycache__/*",
	"*.py[co]",
	"Thumbs.db",
	"desktop.ini",
	".DS_Store",
]

# Base language for the NVDA add-on
# If your add-on is written in a language other than english, modify this variable.
# For example, set baseLanguage to "es" if your add-on is primarily written in spanish.
# You must also edit .gitignore file to specify base language files to be ignored.
baseLanguage: str = "en"

# Markdown extensions for add-on documentation
# Most add-ons do not require additional Markdown extensions.
# If you need to add support for markup such as tables, fill out the below list.
# Extensions string must be of the form "markdown.extensions.extensionName"
# e.g. "markdown.extensions.tables" to add tables.
markdownExtensions: list[str] = []

# Custom braille translation tables
# If your add-on includes custom braille tables (most will not), fill out this dictionary.
# Each key is a dictionary named according to braille table file name,
# with keys inside recording the following attributes:
# displayName (name of the table shown to users and translatable),
# contracted (contracted (True) or uncontracted (False) braille code),
# output (shown in output table list),
# input (shown in input table list).
brailleTables: BrailleTables = {}

# Custom speech symbol dictionaries
# Symbol dictionary files reside in the locale folder, e.g. `locale\en`, and are named `symbols-<name>.dic`.
# If your add-on includes custom speech symbol dictionaries (most will not), fill out this dictionary.
# Each key is the name of the dictionary,
# with keys inside recording the following attributes:
# displayName (name of the speech dictionary shown to users and translatable),
# mandatory (True when always enabled, False when not).
symbolDictionaries: SymbolDictionaries = {}

# Custom speech dictionaries (distinct from symbol dictionaries above)
# Speech dictionary files reside in the speechDicts folder and are named `name.dic`.
# If your add-on includes custom speech (pronunciation) dictionaries (most will not), fill out this dictionary.
# Each key is the name of the dictionary,
# with keys inside recording the following attributes:
# displayName (name of the speech dictionary shown to users and translatable),
# mandatory (True when always enabled, False when not).
speechDictionaries: SpeechDictionaries = {}
