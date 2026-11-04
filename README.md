# ADI-2 Commander

A Windows app to control the RME ADI-2 DAC FS[^rme], and to load and convert externally generated filter sets.
A personal project, shared as is.

![ADI-2 Commander: the main window, the panels, Load, presets and Loudness](docs/feature-tour.gif)

## Features

- **Device control:** EQ, Bass/Treble, Loudness and the output settings of Line Out, Phones and IEM.
- **In-graph editing:** the EQ as a response curve, edited in place.
- **Table input:** every value entered or stepped directly, by keyboard or mouse.
- **Device-accurate curves:** curves and conversions follow the device implementation.
- **Filter set and curve conversion** from AutoEQ, squig.link, REW, Equalizer APO and others.
- **Loudness view:** what Loudness does at the current settings and volume.
- **Preset management:** preview, edit and store.
- **Simulated mode:** explore Commander without a device, and convert filter sets and curves for any ADI-2 model.

## Also

- Save the EQ to a .txt file that is both portable and ADI-2 compatible.
- Drag and drop filter files and curves to load them.
- Map filters one to one, or fit them for the closest possible match.
- Monitor the device's inputs and clock.
- View the curves at any sample rate, or compare them with the rate the device runs at.

## Requirements

- Windows 10 (1809) or later, 64-bit.
- An ADI-2 DAC FS over USB, with MIDI Control set to ON (menu Remap Keys/Diag). Simulated mode needs no device.
- Windows' built-in USB MIDI class driver, or RME's MADIface driver (tested with 1.015).
- A screen of at least 1280×720.

## Install

Download `ADI-2-Commander-0.1.0-setup.exe` from [Releases](../../releases) and run it. Windows may warn about an
unknown publisher: choose More info, then Run anyway.

Commander makes no internet connections and collects no data.

## Before first use

Back up your device with RME's ADI-2 Remote first: File → Save Setup as… keeps everything, presets included, and
restores it.

Commander writes every change to the device at once. Try Simulated mode first to get to know it: start
ADI-2 Commander (simulated) from the Start menu.

## Building from source

Commander runs on Python 3.14 on Windows.

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\pythonw Commander.pyw
```

Add `--simulate` for Simulated mode. To build the installer, also install `requirements-build.txt` and Inno Setup 6,
then run `.venv\Scripts\python tools\build.py`.

## Tested with

- ADI-2 DAC FS, firmware DSP 62, USB 81
- RME MADIface driver 1.015, and Windows' built-in USB MIDI class driver
- Windows 11 Pro 26H2 (build 26300)

## License

[GPL-3.0-or-later](LICENSE); the licenses of the software it includes are in the installation's licenses folder.

[^rme]: Not affiliated with or endorsed by RME, the maker of the ADI-2; both names are trademarks of their owner.
