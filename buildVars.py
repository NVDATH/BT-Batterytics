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
		"battery statistics in the Input Gestures dialog.\n"
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
		"First release of BT-Batterytics, based on BlueToothBatteryReport. "
		"New: filters by connection status, connection type and connection time in the report, "
		"measurement of the connection time between two recharges, a battery statistics window "
		"with estimates and exports, names of your own for devices, per-device alerts "
		"(low battery, level drops, connects, disconnects) with speech, beep or sound files, "
		"an estimate of the charges left in the charging case of earbuds, "
		"and a gesture that depends on whether the computer has a battery.",
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
