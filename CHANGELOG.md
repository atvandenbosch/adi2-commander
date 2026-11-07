# Changelog

All notable changes to ADI-2 Commander are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ADI-2 Pro (all versions, including EX) and ADI-2/4 Pro (SE and EX): the EQ of Line Out and Phones 3/4, with
  Bass/Treble, Loudness, presets, Load and Save. Phones 1/2 and the other settings are not yet available. Not tested
  with an actual device; a notice says so when one is connected.
- Simulated mode asks which ADI-2 to simulate: ADI-2 DAC FS, ADI-2 Pro, ADI-2/4 Pro SE or EX. The choice made last
  is preselected.
- Save as an ADI-2 Remote preset (.adieqpr), to store it to a preset slot with ADI-2 Remote's EQ Preset Editor,
  also from Simulated mode.
- At each connection, a copy of the device's state as an ADI-2 Remote setup file, in
  %LOCALAPPDATA%\ADI-2 Commander\Backups: the last five per model that differ.
- A menu at the top right (⋮): View backups, and About (F1).

### Fixed

- DA Filter follows the device's D/A converter: SD LD with the AK4493, Brickwall with the ES9028Q2M, five filters
  with the AK4490. The sixth was always shown as Brickwall.

## [0.1.0] - 2026-11-04

### Added

- First release: control of the ADI-2 DAC FS over USB MIDI, filter set and curve conversion, and Simulated mode.
  See the [README](README.md).

[Unreleased]: https://github.com/atvandenbosch/adi2-commander/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/atvandenbosch/adi2-commander/releases/tag/v0.1.0
