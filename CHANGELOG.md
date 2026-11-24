# Changelog

All notable changes to ADI-2 Commander are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- More options has MIDI traffic, to open the MIDI traffic panel.

### Changed

- Ctrl+Shift+T opens the MIDI traffic panel, also when it is open already, and puts the cursor in its filter. Its
  tab closes it.
- The window opens with the panels that were open when it last closed, the MIDI traffic included.
- On each device, the window opens on the output last chosen on it.
- Balance names its ends L and R.
- In a narrower window, the top bar shortens the names and narrows the switches, step by step, before Volume
  takes a line of its own.

## [0.3.0] - 2026-11-21

### Added

- The window opens where and as large as it was when it last closed.
- The graphs show their scale in dB per decade where the axes meet. In the response graph, point at it to choose
  10, 25 or 50.
- Import: Fit can adjust the level (Free) or keep it (Fixed); with Fixed, the file's Preamp line can be included.
- Under DEVICE, Factory Settings resets Remap Keys and the functions of the keys.
- A panel that logs the MIDI traffic with the device, to save and share: Ctrl+click the connection light, or press
  Ctrl+Shift+T.

### Changed

- Volume, Lock Volume, Mute, Dim and Balance are in the top bar, with switches for the EQ, Bass/Treble and
  Loudness. Volume has a slider; Ctrl+Shift+M switches Mute.
- The response graph shows the curve of each section (EQ, Bass/Treble, Loudness): point at its switch, or turn on
  Sections in the legend. The legends name the channels Left and Right.
- Import's graph and the Loudness graph match the response graph.
- Dragging a point in a graph outlines the values it changes in the tables.
- Presets: Select, Edit and Store appear on the row under the mouse, and a double click selects. A preset's preview
  shows while the mouse is on its row.
- Import: the conversion settings row is rearranged.
- Under DEVICE, the tooltip of each key says what the key does with Remap Keys as set.
- The device's serial number names its backups, the last five of each device, and shows in the title bar and in
  Export's file name.
- The installer offers Install for all users or Install for me only. Updates keep the existing installation; to
  install for all users instead, uninstall Commander first.

### Fixed

- Import: with Dual EQ, Bass and Treble are drawn once.
- The connection stays when the device is slow to send a preset, or its reply stays incomplete. Such a preset is
  "not read", and the backup waits for it.
- Setup and the uninstaller ask to close a running Commander, also in another Windows session. A cancelled update
  could leave a Commander that did not start.

## [0.2.0] - 2026-11-14

### Added

- ADI-2 Pro (all versions, including EX) and ADI-2/4 Pro (SE and EX), not tested with an actual device:
  - Line Out, Phones 3/4, and Phones 1/2 with Dual Phones on: EQ, Bass/Treble, Loudness, presets, output settings.
  - Input panel: Source, Clock Source, the settings of the analog input.
  - Analog In tab: the EQ of the analog input, with presets.
  - ADI-2/4 Pro: the Rumble preset.
- Device panel: the settings of the device itself, such as its display, Auto Standby and the functions of the keys on
  the device and its remote control.
- A backup of the device's state at each connection, as an ADI-2 Remote setup file.
- Export as an ADI-2 Remote preset (.adieqpr).
- Simulated mode: a choice of model.
- A menu (⋮) at the top right: View backups, About (F1).
- The connected or simulated model in the window title.

### Changed

- Load and Save are now Import and Export.
- Tooltips appear only once the mouse rests.
- Import: the deviation is drawn as a filled area.

### Fixed

- DA Filter names its filters after the device's D/A converter; the sixth was always shown as Brickwall.
- Side panels no longer push the window off the screen; to make room, the one open longest closes.

## [0.1.0] - 2026-11-04

### Added

- First release: control of the ADI-2 DAC FS over USB MIDI, filter set and curve conversion, and Simulated mode.
  See the [README](README.md).

[Unreleased]: https://github.com/atvandenbosch/adi2-commander/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/atvandenbosch/adi2-commander/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/atvandenbosch/adi2-commander/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/atvandenbosch/adi2-commander/releases/tag/v0.1.0
