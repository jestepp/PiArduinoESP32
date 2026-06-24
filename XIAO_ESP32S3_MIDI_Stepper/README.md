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
4. On Windows, use Python 3.12 for the MIDI bridge. Python 3.13 may try to build `python-rtmidi` from source and fail unless Visual C++ build tools are installed.
5. Run the one-time setup script:

```powershell
.\setup_midi_player.bat
```

6. Start the MIDI bridge:

```powershell
.\run_midi_player.bat
```

7. Choose live MIDI input or direct MIDI file playback from the menu.

For live MIDI input, start loopMIDI and create a virtual MIDI port, or connect a MIDI input device. Select that MIDI input port and send notes to channels 0, 1, and 2.

For MIDI file playback, choose `Play MIDI file directly` and drag a `.mid` file into the prompt.
When prompted, choose single-stepper mode if you want MIDI sent to motor 0. For dense multi-channel MIDI files, filter to one MIDI channel instead of sending every channel to one stepper.
You can transpose pitch by semitones, for example `12` for one octave up or `-12` for one octave down.
If you have multiple motors connected, use the loudness prompt to duplicate notes across 2-3 motors.

The setup script installs Python packages. The run script does not reinstall or upgrade dependencies each time.

If the bridge says `No MIDI input ports were found`, loopMIDI is not running or no virtual MIDI port has been created yet.

## Wiring
- Connect each stepper driver STEP/DIR pins to the GPIO pins defined in `src/main.cpp`.
- Connect the shared stepper driver enable pin to `ENABLE_PIN`.
- Power the stepper drivers from an external supply (e.g. 12V), not from the XIAO USB.

## Notes
- MIDI is parsed on the host PC and sent to the XIAO over USB serial.
- The firmware accepts commands of the form `s,<motor>,<speed>`, `e,<motor>`, and `d`.
- This project is configured for 3 motors, matching the XIAO's available GPIO and your hardware setup.

## GUI Player

Run the GUI directly from Python:

```powershell
py -3.12 midi_stepper_gui.py
```

Basic use:

1. Choose the XIAO COM port.
2. Browse for a `.mid` file.
3. Keep `Single stepper mode` enabled for one motor, or disable it to use multiple motors.
4. Set `Source MIDI channel` to one channel, such as `3`, for dense MIDI files.
5. Set `Transpose` to shift pitch, such as `12` for one octave up or `-12` for one octave down.
6. Click `Play`.

The GUI includes a scrolling note visualizer. Notes are drawn as colored bars by motor, with a moving playhead synchronized to playback. Use `Pause`, `Resume`, and `Stop` from the GUI while watching the chart. Click or drag on the visualizer to seek to a different point in the MIDI timeline; pressing `Play` after stopping starts from the selected point.

For multiple connected motors, disable `Single stepper mode` and set `Loudness motors` to `2` or `3` to duplicate notes across motors.

Click `Analyze MIDI` after choosing a file to see which MIDI channels contain notes. The GUI will set `Source MIDI channel` to the channel with the most notes.
Click the `Analyzer / Filters` tab or `Arrange Filters` to use the embedded editor-style analyzer. It shows MIDI notes by channel across the timeline. Use the zoom slider, mouse wheel, position slider, or right/middle-button drag to navigate. Left-click note bars to mute/unmute that channel/note value, or left-click channel lanes and checkboxes to include/exclude channels. Applying filters rebuilds the main visualizer, resets the timeline to the beginning, and makes playback use the filtered arrangement.
Enable `Auto-simplify for 1 motor` to let the player choose the best melodic channel and send only that channel to motor 0. This is the cleanest mode when only one stepper is connected.
Enable `Auto-arrange for 3 motors` to let the player split the MIDI file across motors 0-2. It ignores percussion channel 10, then maps the busiest melodic channels to separate motors. If a file only has one melodic channel, it splits low, mid, and high notes across the three motors.

Command-line analyzer:

```powershell
py -3.12 midi_analyzer.py "D:\Media\Max_Verstappen_Motif.mid"
```

## Building the GUI EXE

Run the build script:

```powershell
.\build_gui_exe.bat
```

The built app will be:

```powershell
dist\MIDI-Stepper-Player.exe
```

Manual build commands:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m pip install pyinstaller
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name MIDI-Stepper-Player --hidden-import=rtmidi midi_stepper_gui.py
```

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
