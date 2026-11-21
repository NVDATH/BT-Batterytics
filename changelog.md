## 1.0.0

First release as BT-Batterytics, a modified version of BlueToothBatteryReport 0.4 by haitun001 and cary-rowen. It keeps its own single-file code: it does not include the refactoring of version 0.4.

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
- The "Only report connected devices" option of version 0.4 is replaced by one option for each status.
