# XIAO ESP32-S3 MIDI Stepper Player

Standalone project for a Seeed XIAO ESP32-S3-based MIDI stepper controller.
This repository is separate from the Gauge workspace and is designed to use a host MIDI bridge and serial-controlled stepper drivers.

## Features
- XIAO ESP32-S3 PlatformIO project using `AccelStepper`
- Three independent stepper outputs with a shared enable pin
- Host-side MIDI parsing with serial commands
- Compatible with the BarlowTJ48 MIDI stepper example flow

## Getting started
1. Open this folder in VS Code.
2. Build with PlatformIO.
3. Flash the XIAO ESP32-S3 with the firmware in `src/main.cpp`.
4. Install Python dependencies: `pip install -r requirements.txt`.
5. Run `python midi_interface.py COMx` (replace `COMx` with your XIAO serial port).
6. Select a MIDI input port and send notes to channels 0, 1, and 2.

## Wiring
- Connect each stepper driver STEP/DIR pins to the GPIO pins defined in `src/main.cpp`.
- Connect the shared stepper driver enable pin to `ENABLE_PIN`.
- Power the stepper drivers from an external supply (e.g. 12V), not from the XIAO USB.

## Notes
- MIDI is parsed on the host PC and sent to the XIAO over USB serial.
- The firmware accepts commands of the form `s,<motor>,<speed>`, `e,<motor>`, and `d`.
- This project is configured for 3 motors, matching the XIAO's available GPIO and your hardware setup.

## Packaging as a single Windows EXE (PyInstaller)

1. Install Python requirements in the environment you'll run PyInstaller from:

```powershell
python -m pip install -r requirements.txt
```

2. Build a one-file EXE using PyInstaller (console output):

```powershell
pyinstaller --onefile --console launcher.py
```

3. To embed an icon, place an ICO at `assets/app.ico` and either:

```powershell
pyinstaller --onefile --icon=assets/app.ico launcher.py
```

or use the provided spec file:

```powershell
pyinstaller launcher.spec
```

4. The built executable will be at `dist\launcher.exe`. Run it with the COM port:

```powershell
dist\launcher.exe COM3
```

Notes:
- Use `--noconsole` to hide the console window (not recommended for debugging).
- If PyInstaller misses imports (e.g., `rtmidi`), add `--hidden-import=rtmidi` or edit `launcher.spec`.
- Test the EXE on the target Windows machine where the XIAO is connected.
