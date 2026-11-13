# Changelog

All notable changes to ADI-2 Commander are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Import: a refined deviation graph.

### Fixed

- DA Filter names its filters after the device's D/A converter; the sixth was always shown as Brickwall.
- Side panels no longer push the window off the screen; to make room, the one open longest closes.

## [0.1.0] - 2026-11-04

### Added

- First release: control of the ADI-2 DAC FS over USB MIDI, filter set and curve conversion, and Simulated mode.
  See the [README](README.md).

[Unreleased]: https://github.com/atvandenbosch/adi2-commander/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/atvandenbosch/adi2-commander/releases/tag/v0.1.0
