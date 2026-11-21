# BT-Batterytics

BT-Batterytics reports the battery levels of Bluetooth devices, remembers how long each device is connected between two recharges, and shows statistics about it.

It is a modified version of [BlueToothBatteryReport](https://github.com/haitun001/BlueToothBatteryReport) by haitun001 and cary-rowen (see Credits and license below).

It supports multi-device battery reporting and sequentially announces all Bluetooth devices whose battery levels can be detected. Devices are announced in this order: connected, unknown, disconnected.

## Hotkey

- `NVDA+Shift+B` on a computer without a battery (a desktop PC), `NVDA+Alt+B` on a computer with a battery (a laptop or tablet) — Press once to read battery status, twice to copy the report to the clipboard, three times to open the settings panel.

NVDA+Shift+B is NVDA's own battery status command. A desktop PC has no battery, so the add-on uses that gesture there. On a computer that has a battery it uses NVDA+Alt+B instead, to leave NVDA's command alone. The choice is made when NVDA starts, from what Windows reports, and if Windows cannot tell, the add-on assumes a battery. The gesture can be changed in NVDA → Preferences → Input Gestures, in the BT-Batterytics category. That category also has the command "Open the Bluetooth battery statistics", which has no gesture by default.

## Spoken Format

When battery information is available, each device is announced as:

- `device name battery xx%`

Optionally, the connection type label and the connection time can be shown:

- `device name (Classic) battery xx%`
- `device name (LE) battery xx%`
- `device name battery xx% (connected 2 hr 5 min)`

If you gave a device a name of your own (see Battery Statistics), that name is announced instead of the name Windows gave.

## Settings

A dedicated settings page is available under NVDA → Preferences → Settings → BT-Batterytics.

### Which devices are reported

- **Report connected devices** — Announce devices that are currently connected (enabled by default).
- **Report disconnected devices** — Announce devices that are paired but not connected.
- **Report unknown status devices** — Announce devices whose connection status cannot be determined. Bluetooth LE devices are usually reported with this status.

### What is announced for each device

- **Show connection type (Classic / LE)** — Append a label indicating whether the device uses Bluetooth Classic or Bluetooth Low Energy.
- **Show connection duration** — Announce how long the device has been connected.
- **Speak total connection time since the last recharge** — Chooses which connection time is announced, and turns the measurement on (enabled by default).
  - Checked: the total connected time counted since the device was last recharged. It is remembered across disconnections and NVDA restarts, and it works for Classic and LE devices.
  - Unchecked: only the time of the current connection session, as reported by Windows. Windows provides this value for Classic devices only, so LE devices have no connection time in this mode.
- **Show the charging case estimate in the report** — Add the estimated charges left in the charging case of earbuds to their line of the report (off by default, see Charging Case).

### Statistics

- **View battery statistics...** — Opens the battery statistics window (see below).
- **Keep at most this many finished cycles per device** — From 5 to 5000, 500 by default. The oldest cycles are deleted beyond this number.
- **Delete finished cycles older than this many days** — 0 keeps them all (the default).

### Alerts

- **Enable low battery alert (default for all devices)** — Alert when the battery of a connected device drops below its alert level. Each device follows this setting unless you choose otherwise for it (see Alerts). The dialog of a low battery alert is always shown.
- **Default low battery threshold** — The percentage at which a low battery alert is triggered for the devices that have no level of their own (5–50%, default 20%).
- **Alert methods (for all alerts)** — A list of check boxes that work together:
  - **Speak the alert** (checked by default)
  - **Play a double beep**
  - **Play the sound of the alert** (see Alert Sounds)
- **Browse sound folder...** — Opens the folder with the sound files of the alerts, so you can replace them.
- **Level drop alerts: alert each time the battery drops by this many points** — From 1 to 50, 10 by default.
- **Check for device connection changes every this many seconds** — From 5 to 300, 15 by default. Used only while a device has a connect or disconnect alert.

## Connection Time Tracking

The add-on keeps a record of how long each device is connected between two recharges, so you can see how long a device really lasts on one charge. This works in the background and is controlled by **Speak total connection time since the last recharge**.

- A device starts being tracked the first time the add-on sees it, at any battery level. The first cycle of a device may therefore be shorter than the real one if the device was not full at that moment.
- Only the time the device is seen as connected is counted. Time while it is disconnected is not counted, but the total counted so far is kept.
- A recharge is detected when the battery is at least 15 percentage points above the lowest level seen in the current cycle. This also works for devices that never reach 100%. The finished cycle is saved and counting restarts from zero. Time is not counted while the battery level is rising (charging).
- If Windows reports that a Classic device has been connected longer than the add-on has counted, the longer value is used. LE devices have no such value, so their total covers only the time the add-on has observed them.
- Gaps of more than 15 minutes between two observations (for example while the computer sleeps) are not counted.
- Cycles shorter than 30 minutes are not saved as finished cycles.
- Devices are identified by their Bluetooth address, not by their name. Two devices with the same name keep separate records, and a device that is renamed in Windows keeps its data.
- The measurement of a device can be stopped (see Battery Statistics). Its data is kept, and its connection time is then the one reported by Windows, if any.

### Devices That Are Not Always Connected

Some devices stay powered on but are rarely connected to the computer. An example is a tri-mode keyboard that you use with a 2.4 GHz dongle, and that you connect by Bluetooth only from time to time to check its battery. The connected time of such a device is very short, and a cycle with less than 30 minutes of connected time is not saved, so nothing useful is recorded. For these devices, choose **Count elapsed time** in the Measuring menu of the device in the statistics window. It is off by default, and set for each device.

With it:

- The time of a cycle runs from the recharge to the last moment when the battery level was seen dropping. It does not run until the next time you check, because the level is only known when it is read, and Windows can show an old level for a device that is not connected.
- A recharge is detected the first time you read the battery after it. Its moment is taken as halfway between the last reading before it and that one.
- The estimates (full charge, drain rate, time left, trend) and the Recharged every column use these times, which are shown in days from two days on. The first cycle begins when the add-on first sees the device, whatever its level.
- In the report, the line of the device shows the time since its last recharge instead of the connected time.
- Each cycle remembers how its time was counted. The statistics of a device use only the cycles counted as the device is counted now. The other cycles stay in the cycle list, with their way of counting in the Time counted column.
- Changing the way of counting starts the current cycle again.

Read the battery of such a device from time to time: connect it by Bluetooth and press the hotkey. The less often you do, the less accurate the estimates are, and if the device is recharged twice between two readings, the two cycles count as one.

### Devices That Do Not Go Down to 0%

Some devices report a battery level that does not go down evenly. An example is a keyboard whose level stays at 100% for a long time, then falls quickly, and which stops working at 55% or 60%. You learn to recharge it earlier, for example at 70%, to be safe. The estimates of the statistics (Full charge, Left now) assume that the level goes down evenly to 0%, so for such a device they are far too long: the time that the device really lasts between your recharges is much shorter than the estimate.

For these devices, choose **Usual recharge level...** in the Measuring menu of the device and enter the level at which you recharge it, for example 70. It is off (0) by default, and set for each device.

With it:

- Full charge (est.) becomes the time the device lasts from a full battery down to your level, which is the time between your recharges.
- Left now (est.) becomes the time left before the battery reaches your level. It is zero when the battery is already at that level or below.
- The drain rate, the times of the cycles and the detection of the recharges do not change.
- The Measuring column of the summary list shows the level, for example "on, recharge at 70%".

Leave it off for devices whose level goes down evenly. The estimates stay rough, because the level of such a device does not go down evenly, so the most reliable figures are the real times between recharges: Average, Shortest, Longest and Recharged every.

## Battery Statistics

**View battery statistics...** in the settings panel opens a window with two lists. The command "Open the Bluetooth battery statistics" in the Input Gestures dialog opens it directly. The window shows the stored records even when the measurement is turned off.

Devices are listed in the same order as in the spoken report: connected, unknown, disconnected, then by name. Devices that were not in the latest scan come last.

### Summary per device

One row per device:

- **Status** — The connection status in the latest scan.
- **Measuring** — Whether the time of the device is measured: off, on, or on with elapsed time. The usual recharge level is added when it is set, for example "recharge at 70%".
- **Alerts** — The alerts of the device that are on, for example "low battery 20%, level drop" or "none".
- **Cycles** — Number of finished cycles.
- **Average**, **Shortest**, **Longest** — Connected time of the finished cycles.
- **Full charge (est.)** — Estimated runtime on a full charge, calculated from how much battery each cycle used. This makes cycles that did not start at 100% comparable.
- **Drain rate** — Battery points used per hour of connection, usually, or per day if the device drains slowly.
- **Recharged every** — Average time between two recharges.
- **Last recharge** — When the last recharge was detected.
- **Trend** — The latest 3 cycles compared with the earlier ones, for example "12% shorter" or "stable" (a difference below 5%). At least 4 cycles are needed.
- **Left now (est.)** — Connected time left at the device's usual drain rate, from the battery level seen last.
- **Case used (charges, est.)** and **Case left (charges, est.)** — Charges of the charging case used and left, only for devices that have a charging case (see Charging Case). These two columns are added the first time you turn a charging case on, and you can hide them.

### Cycles

For each device, only the cycle in progress ("current") is shown at first. The finished cycles, newest first, are collapsed. Press Space on any row of a device, double-click it, or use the context menu (Applications key) to expand them, and do the same to collapse them again. NVDA says "Expanded" or "Collapsed". The columns are:

- **Cycle** — Cycle number.
- **State** — "collapsed" or "expanded" on the row of the cycle in progress, empty for devices that have no finished cycles.
- **Duration** — Connected time of the cycle.
- **Battery** — Battery level at the start of the cycle and the lowest level reached, for example "100% to 23%".
- **Drain rate** — Battery points used per hour during that cycle.
- **Full charge (est.)** — Estimated runtime on a full charge for that cycle.
- **Ended** — When the recharge that ended the cycle was detected.
- **Time counted** — Whether the time of the cycle is connected time or elapsed time (see Devices That Are Not Always Connected). This column is added the first time you count elapsed time, and you can hide it.

Estimates ignore cycles that used fewer than 10 battery points, because Bluetooth battery levels are often reported in coarse steps. An empty cell means there is not enough data yet. Estimates become more reliable as more cycles are recorded.

## Statistics Window Commands

Both lists share the same commands. Most have a key; all are also in the context menu (Applications key). In the menu, the commands that open a submenu or a dialog come first, and the commands that have a key come last.

### Measuring

A submenu with two check items for the device:

- **Measure this device** — Stops or restarts the measurement of the device. Its data is kept.
- **Count elapsed time (for devices that are not always connected)** — Counts the time since the last recharge instead of the connected time. See Devices That Are Not Always Connected.
- **Usual recharge level...** — The battery level at which you usually recharge the device, for devices that report the level unevenly. See Devices That Do Not Go Down to 0%.

### Alerts

The alerts of the device. See Alerts below.

### Select

Toggle current row (**Control+Space**), Select all (**Control+A**), Select none, Invert selection, Select rows of this device. The lists allow several selected rows like any list, so NVDA says "selected" for the rows you selected. Moving with the arrow keys alone selects only the current row. To build a selection, move with Control+arrows and press Control+Space on each row.

### Sort

No key. Choose the order of the devices (report order, name, number of cycles, average time, full charge estimate, last recharge, current cycle time, drain rate, or manual) and the order of the finished cycles of each device (newest, oldest, longest, shortest first, or manual). The checked choice is the one in use, and your choice is remembered. With **Manual**, you decide the order yourself (see Move a device or a cycle).

### Move a device or a cycle

**Control+Shift+Up** and **Control+Shift+Down**. It needs the manual sort: choose Manual in the Sort menu, under Devices by to move devices, and under Cycles by to move cycles. The first time you choose Manual for the devices, the order that was in use becomes your order.

- In the summary list, and on the row of the cycle in progress in the cycle list, the keys move the device, with all its rows.
- On a finished cycle of an expanded device, the keys move that cycle among the finished cycles of the device.

NVDA says the new position, for example "2 of 5", and a beep means that the row is already at the end. The order is remembered. A device that the add-on sees for the first time, and a cycle that has just finished, are put first.

### Move the lists

**Control+Shift+Left** and **Control+Shift+Right** move the list that has the focus before or after the other one. The window opens on the list that comes first, so you can choose the one you look at most. The order is remembered.

### Choose columns

No key. Opens a list of check boxes, one for each optional column of each list. The Device and Cycle columns are always shown. Press Control+Shift+Up or Control+Shift+Down on a column to move it, and the order is the one used to show, copy and export the columns. Your choice is remembered.

### Expand and Collapse

**Space** on the cycle list. Shows or hides the finished cycles of the device.

### Rename device

**F2** gives the device of the current row a name of your own. An empty name, or the original name, goes back to the name Windows gave. The name is used in the statistics, in the spoken report and in the alerts.

### Copy

- **Control+C** copies the current row.
- **Control+Shift+C** copies everything about the current device (its summary and all of its cycles, even the collapsed ones).

Only the columns that are shown are copied, as "Header: value" pairs.

### Mark case charged

**Control+Shift+R**, only for a device that has a charging case. It tells the add-on that you charged the case, so that it counts its charges from zero. See Charging Case.

### Export

**Control+E** opens the Export menu. It has these parts:

- **What to export** — The selected rows, the current device, or all rows of the list. The checked choice is in use.
- **Include detailed values** — Checked by default and remembered. It adds to the columns of the list the identity of the device (its address and both names) and exact values: seconds, battery percentages, battery points used, ISO 8601 dates. Without it, the columns that are shown in the list are exported.
- **Copy to clipboard as** and **Save to a file as** — Plain text, Markdown table, CSV, tab-separated values (to paste into a spreadsheet), JSON (numbers stay numbers), or HTML table. CSV files are saved with a byte order mark so that Excel shows all letters correctly.
- **Open as an HTML report in the browser** — Makes a page with a heading and the table, and opens it in your web browser.

The exports can be given to a person or to an AI tool as they are.

### Refresh

**F5** scans the devices again and updates the window, which is otherwise a picture of the moment it was opened.

### Delete

- **Control+Delete** deletes the current row. If several rows are selected, it deletes all of them.
- **Control+Shift+Delete** deletes the device of the current row with all its data.

A question (Yes or No) always comes first. On the cycle in progress, "delete" restarts the current cycle from zero. In the summary list, deleting a row deletes the device. If the measurement is enabled, a deleted device starts again from zero at the next check.

## Alerts

Each device can have these alerts. They are chosen per device in the statistics window (context menu, **Alerts**; the Alerts column of the summary list shows the active ones). Every alert is given by the alert methods checked in the settings.

### Low battery

Alerts once, when the battery of a connected device gets low, until the battery recovers. It also shows a warning dialog. In the Alerts menu, **Low battery level...** opens a dialog with three choices:

- **Use the default** — The device follows **Enable low battery alert** and the default threshold of the settings. If the low battery alert is turned off in the settings, the device does not alert.
- **Use a level of my own** — A level from 5 to 50%. The device alerts at this level even if the low battery alert is turned off in the settings.
- **Never alert for this device** — No low battery alert, whatever the settings say.

### Battery level drops

Off by default. Alerts each time the battery has dropped by the number of points of the settings since the last alert, counted from the level at which the device was first seen and again whenever the level rises (charging). Bluetooth devices report their level in steps that depend on the device: some report every 1%, others only every 10% or more. With the default of 10 points, a device that reports in steps of 10% alerts at each step. If the same device gets a low battery alert in the same check, only the low battery alert is given.

### Device connects and Device disconnects

Off by default. Alert when a device changes between connected and disconnected. A device counts as connected unless it is known to be disconnected, as for the connection time, so Bluetooth LE devices (whose status is unknown) alert on disconnect only if Windows reports them as disconnected. The first check after NVDA starts only remembers the state. The devices are checked again every few seconds (see the settings).

### Charging case

For true wireless earbuds that come with a charging case. Off by default, for each device. Windows reports the battery of the earbuds, not the one of the case, so the add-on estimates how many times the case has charged the earbuds. In the Alerts menu of the device, **Charging case...** opens a dialog with these fields:

- **Alert about the charging case** — Turns the estimate and the alert on for the device.
- **Earbuds runtime per charge (hours)** and **Total runtime with the case (hours)** — The runtimes of your earbuds, for example 10 hours and 52 hours. The case can then charge the earbuds about 4.2 times: 52 divided by 10, minus the first charge, which the earbuds have in themselves.
- **Use statistics** — Fills the runtime per charge with the full charge estimate of the statistics, to half an hour.
- **Alert when fewer than this many charges are left** — 1 by default.

Every time the add-on sees the earbuds recharged, it adds the battery points they gained to the charges used (100 points are one charge). The alert is given when the battery of the earbuds is low, at the low battery level of the device or at the default level, and the case is estimated to have fewer charges left than the field above. It is the moment to charge the case together with the earbuds. It is given once, until the battery of the earbuds recovers, and it shows a warning dialog like the low battery alert.

The add-on also asks you. After the alert, the next time it sees the earbuds recharged (you took them out of the case and connected them), a question asks whether you charged the case as well. **Yes** counts the charges of the case from zero again. **No**, the default answer, keeps counting.

At any other time, use **Mark case charged** (Control+Shift+R in the statistics window) to count from zero again. Each time the case is marked as charged, the add-on remembers how many charges the case gave in that round. From the third finished round, it uses the typical figure of the latest five rounds instead of the runtimes you gave.

The estimate has limits:

- It works well only if you use the earbuds mainly with this computer. Charges while you use them with another device, such as a phone, are not counted, so the case seems fuller than it is.
- You must say each time that you charged the case, by answering the question or by marking it, because the add-on cannot know it.
- The connection time of the device must be measured, as for the statistics.
- It is an estimate, not a measure.

### Alert Sounds

The alert methods: speech says, for example, "device name connected" or "device name battery 80%"; the double beep is the same for all alerts; the sound of the alert is a .wav file in the `sounds` folder of the add-on (next to the `globalPlugins` folder). Use **Browse sound folder...** in the settings to open it, and replace a file to change a sound. If a file is missing, a beep is played instead. When several alerts come together, their sounds play one after another. The files:

- `lowBattery.wav`
- `levelDrop.wav`
- `deviceConnected.wav`
- `deviceDisconnected.wav`
- `chargingCase.wav`

## Background Monitor

When the low battery alert, the connection time tracking or an alert of a device is enabled, the add-on checks battery levels in the background every 5 minutes. While a device has a connect or disconnect alert, the connections are checked more often (every few seconds, see the settings), and the rest is still done every 5 minutes.

## Data and Settings

The records are stored in `btBatterytics_usage.json` in the NVDA user configuration folder. To back them up, copy this file. Delete the file (while NVDA is not running) to start over.

The first time BT-Batterytics runs, it takes over what was saved under the former name: the records are copied from `blueToothBatteryReport_usage.json` (the old file is left as it is) and the settings are taken from the former settings section. Records from before the devices were identified by address move to the address of the device with the same name the first time it is seen.

## Sound Credits

The sounds of the alerts that come with the add-on are from Pixabay:

- `levelDrop.wav` — Sound Effect by [Vadim](https://pixabay.com/users/vadim_makes_sound-54823268/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614159) from [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614159)
- `lowBattery.wav` — Sound Effect by [Shagor Miah](https://pixabay.com/users/u_31vnwfmzt6-31480456/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=126627) from [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=126627)
- `deviceConnected.wav` — Sound Effect by [juniorsoundays](https://pixabay.com/users/juniorsoundays-19205462/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527856) from [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527856)
- `deviceDisconnected.wav` — Sound Effect by [juniorsoundays](https://pixabay.com/users/juniorsoundays-19205462/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527837) from [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527837)
- `chargingCase.wav` — Sound Effect by [Vadim](https://pixabay.com/users/vadim_makes_sound-54823268/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614153) from [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614153)

## Credits and License

BT-Batterytics is based on [BlueToothBatteryReport](https://github.com/haitun001/BlueToothBatteryReport), Copyright (C) haitun001 and cary-rowen, and modified in 2026 by NVDATH. It is covered by the GNU General Public License version 2, like the original.

### How the modifications were made

The ideas, the decisions about how the add-on behaves, and all the testing with NVDA were done by NVDATH. All the modifications to the code of the original add-on were written by Claude, an AI assistant made by Anthropic, following the instructions of NVDATH. The code was not written by a programmer by hand, so please report any problem you find to NVDATH.

## Supported NVDA Versions

- Minimum version: `2025.1.0`
- Tested up to: `2026.3.1`
