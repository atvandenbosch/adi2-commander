# Changelog

All notable changes to ADI-2 Commander are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Import: Level for Fit. Free adjusts the level for the closest fit, as before; Fixed matches filters as they are,
  and a curve centred on 0 dB.
- Import: a Preamp line can be checked; it is used with Fit at a fixed level.
- The graphs show their aspect ratio in dB per decade, in the corner where the axes meet: the response graph, the
  Loudness graph and Import's. In the response graph a click on it sets 10, 25 or 50 dB per decade (IEC 60263), in
  turn with the ratio it had.

### Changed

- Import: Origin and fs come first in the conversion row; Restart and Stop (of a fit) are one
  button.
- The legends of the graphs show what can be clicked and what is shown: each group is one control, the segment of a
  shown item outlined.
- The installer offers Install for all users, in Program Files, and Install for me only. Up to 0.2.0 it installed for
  the current user only, by default in %LOCALAPPDATA%\Programs; updates keep that. To install for all users instead,
  uninstall Commander first.
- Backups are kept per device, named by the model, the serial number and the time: the last five of each device.
- Export offers a file name with the serial number after the model.
- The title bar shows the serial number after the model.
- The tooltip of the letters beside a preset names the outputs it is selected on.
- Presets: the row under the mouse offers Select, over its dot and number, and for a preset Edit and Store at its
  end. Manual and Temp are selected with Select as well; a click on a row selects nothing. A double click selects,
  except on an unused preset and where Select is amber.
- The preview of a preset lies over the left of the graph while the mouse is on its row, at 25 dB per decade.
- The letters of the outputs a preset is selected on follow its name; a name cut short fades out before them.
- The response graph shows what each section adds: point at the switch of an EQ, Bass/Treble or Loudness, or turn
  on Sections in the legend. The legend names the channels Left and Right.
- Import's legend names the channels Left and Right too; Bass/Treble shows with them.

### Fixed

- Import: with Dual EQ, Bass and Treble are drawn once, as bright as the other bands.
- Setup asks to close Commander while it runs, also in another account or Windows session, before it changes
  anything; a cancelled update could leave a Commander that did not start. The uninstaller asks as well.

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

[Unreleased]: https://github.com/atvandenbosch/adi2-commander/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/atvandenbosch/adi2-commander/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/atvandenbosch/adi2-commander/releases/tag/v0.1.0
