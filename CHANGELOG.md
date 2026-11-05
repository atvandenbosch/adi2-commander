# Changelog

All notable changes to ADI-2 Commander are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- DA Filter follows the device's D/A converter: SD LD with the AK4493, Brickwall with the ES9028Q2M, five filters
  with the AK4490. The sixth was always shown as Brickwall.

## [0.1.0] - 2026-11-04

### Added

- First release: control of the ADI-2 DAC FS over USB MIDI, filter set and curve conversion, and Simulated mode.
  See the [README](README.md).

[Unreleased]: https://github.com/atvandenbosch/adi2-commander/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/atvandenbosch/adi2-commander/releases/tag/v0.1.0
