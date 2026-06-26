# XIAO ESP32-S3 MIDI Stepper Player

Standalone project for a Seeed XIAO ESP32-S3-based MIDI stepper controller.
This repository is separate from the Gauge workspace and is designed to use a host MIDI bridge and serial-controlled stepper drivers.

## Features
- XIAO ESP32-S3 PlatformIO project using `AccelStepper`
- Three independent stepper outputs with a shared enable pin
- Three NeoPixel status LEDs, one per motor, using a single data pin
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
- Connect a 3-pixel NeoPixel chain data input to `GPIO9` / `D10`. Pixel 0 follows motor 0, pixel 1 follows motor 1, and pixel 2 follows motor 2.
- Power the stepper drivers from an external supply (e.g. 12V), not from the XIAO USB.
- For NeoPixels, use an external 5V supply for more than a tiny test LED setup, connect LED supply ground to XIAO ground, and add a 330-470 ohm resistor in series with the data line.

## Notes
- MIDI is parsed on the host PC and sent to the XIAO over USB serial.
- The firmware accepts commands of the form `s,<motor>,<speed>`, `e,<motor>`, and `d`.
- NeoPixels light on note-on and turn off on note-off. The color is derived from the note frequency: lower notes and higher notes move through different hues.
- This project is configured for 3 motors, matching the XIAO's available GPIO and your hardware setup.

## GUI EXE Player

The main Windows app is:

```powershell
dist\MIDI-Stepper-Player.exe
```

You can also run the same GUI from Python while developing:

```powershell
py -3.12 midi_stepper_gui.py
```

The GUI is the recommended way to play MIDI files, preview arrangements, filter crowded files, and assign notes to specific motors.

### Top Controls

- Option summary line: shows the current playback mode, source channel, transpose amount, loudness motor count, and pitch profile.
- `Playback Settings`: opens the playback settings popup.
- `Play`: starts playback from the current timeline position. If playback was stopped after seeking, it starts from the selected point.
- `Pause`: pauses playback and disables motor outputs while paused.
- `Resume`: continues from the paused position.
- `Stop`: stops playback and disables motor outputs.
- `Analyze MIDI`: scans the selected MIDI file, logs channel note counts, and updates the recommended source channel.
- `Arrange Filters`: loads the analyzer tab for visual filtering and note assignment.
- `Clear Log`: clears the status log in the Player tab.

### Menu Bar

- `File > Import MIDI File...`: choose a `.mid` or `.midi` file.
- `Connection > Refresh Serial Ports`: rescan COM ports.
- `Connection > COM...`: choose the XIAO ESP32-S3 serial port. Use the port that appears when the board is plugged in over USB.
- `File > Exit`: close the app.
- `Playback > Play`: start playback.
- `Playback > Pause / Resume`: toggle pause.
- `Playback > Stop`: stop playback.
- `Playback > Analyze MIDI`: run MIDI analysis.
- `Playback > Arrange Filters`: switch to the analyzer/filter editor.
- `Options > Single Stepper Mode`: send playable notes to motor 0.
- `Options > Auto-Simplify for 1 Motor`: automatically choose the best melodic channel and send it to motor 0.
- `Options > Auto-Arrange for 3 Motors`: automatically split melodic content across motors 0-2.
- `Options > Playback Settings...`: open the playback settings popup.
- `View > Show Player`: switch to the Player tab.
- `View > Show Analyzer / Filters`: switch to the Analyzer / Filters tab.
- `View > Show Pitch Mapping`: switch to the custom pitch editor tab.
- `View > Show Status Log`: show or hide the Player tab status log to give the visualizer more room.
- `View > Reset Layout`: restore the default split positions, analyzer zoom, lane height, and timeline position.
- `View > Clear Log`: clear the status log.

### Playback Settings Popup

- `Single stepper mode`: forces playback to motor 0. Use this when only one motor is connected.
- `Auto-simplify for 1 motor`: lets the analyzer choose the busiest melodic channel and route only that channel to motor 0.
- `Auto-arrange for 3 motors`: routes melodic channels or pitch bands across motors 0-2.
- `Source MIDI channel`: limits playback to one MIDI channel using 1-16 numbering. Leave blank for all channels.
- `Transpose`: shifts pitch by semitones. Use `12` for one octave up, `-12` for one octave down.
- `Loudness motors`: duplicates each note across 2-3 motors when not using single-stepper or auto modes. Only use this when those motors are physically connected.
- `Pitch profile`: selects how MIDI note numbers become stepper pulse rates.
  - `Standard equal temperament`: normal A4=440 Hz calculation.
  - `David Scholten stepper table`: uses a separate MIDI-note pulse table from the inspected `MidiSynth` stepper synth project.
  - `Custom: ...`: saved profiles created in the Pitch Mapping tab.

The three playback modes are mutually exclusive. Enabling an auto mode disables the other routing modes and sets loudness motors back to `1`.

### Player Tab

The Player tab has a draggable divider between the visualizer and the status log.

- `Timeline zoom`: changes how many seconds are visible in the player visualizer.
- Note bars: show what each motor will play.
- Motor lanes: `Motor 0`, `Motor 1`, and `Motor 2`.
- Playhead: vertical line showing the current playback position.
- Click or drag in the visualizer: seek to a different point in the file.
- Status log: shows COM port detection, connection messages, analysis results, playback status, and errors.

### Analyzer / Filters Tab

The Analyzer / Filters tab is the editor-style view for cleaning up MIDI files before playback. It has a draggable divider between the compact filter controls and the visual note editor.

Analysis area:

- Shows the MIDI file name, length, track count, recommended channel, muted note count, and assigned note count.

Visual edits area:

- `Loaded notes`: shows how many MIDI parts were loaded into the visual editor. These are internal MIDI file parts, not motor lanes.
- `Clear Muted Notes`: removes all muted note filters.
- `Apply Filters`: applies muted notes and manual motor assignments to playback. It rebuilds the main visualizer and resets playback to the beginning.

Visual note editor:

- Motor lanes: shows the final result by `Motor 0`, `Motor 1`, and `Motor 2`, using motor colors.
- Pitch scale: the left side shows note names and pitch-profile frequencies for the visible notes.
- Lane height: each motor lane automatically shrinks or grows based on the pitches currently visible in that lane.
- `Assign notes to`: choose `Motor 0`, `Motor 1`, or `Motor 2` as the target motor for Shift+left-click assignment.
- `Assignments`: compact count of active manual note assignments.
- `Clear Assignments`: removes all manual note-to-motor assignments.
- `Zoom`: controls horizontal timeline zoom.
- `Position`: pans through the MIDI timeline.
- `Lane height`: vertically expands motor lanes so individual pitch rows are easier to see.
- Mouse wheel: zooms the analyzer timeline around the pointer.
- Right-click drag or middle-click drag: pans the analyzer timeline horizontally.
- Ctrl+middle-click drag: scrolls the analyzer vertically when lane height is expanded.
- Left-click a note bar: mute or unmute that channel/note value.
- `Refresh Preview`: redraws the analyzer after filter value changes.
- Shift+left-click a note bar: assign that channel/note value to the selected motor.
- Shift+left-click the same assigned note with the same motor selected: clear that assignment.
- `Apply Filters`: applies muted notes and note assignments to playback. It rebuilds the main visualizer and resets playback to the beginning.

Assigned notes are colored by their target motor and move to that motor lane in `Motor routing` view. Manual note assignments override the normal channel routing and auto-arrange routing after channel/range/mute filters have been applied.

### Routing Behavior

- `Single stepper mode`: all playable notes go to motor 0.
- `Auto-simplify for 1 motor`: the best melodic channel is selected and routed to motor 0.
- `Auto-arrange for 3 motors`: the analyzer maps busy melodic channels to separate motors. If only one melodic channel is available, it splits low, middle, and high notes across motors.
- Direct motor mode: when no single/auto/loudness mode is active, the first three playable MIDI parts map to motors 0, 1, and 2 internally.
- Manual note assignments: specific channel/note values can be forced to motor 0, 1, or 2 from the Analyzer / Filters tab.
- Muted notes: muted channel/note values are not played.
- Note range: notes outside the min/max range are not played.
- Pitch profile: changes the frequency/step-rate sent for each MIDI note. This can make the same MIDI file sound slightly different without editing the MIDI file.

### Pitch Mapping Tab

The Pitch Mapping tab creates custom note-to-step-frequency profiles. Custom profiles are saved as JSON files in the `pitch_profiles` folder and appear in `Playback Settings > Pitch profile`.

- `Profile name`: name for the custom profile.
- `Start from`: chooses a built-in profile to copy into the editor.
- `Load Source`: fills the table from the selected built-in profile.
- `Save Custom Profile`: writes the current table to `pitch_profiles\<name>.json`.
- `Reload Saved Profiles`: rescans the `pitch_profiles` folder.
- `Use This Profile`: saves if needed, then selects the custom profile for playback.
- Pitch table: shows all MIDI notes 0-127.
- `Frequency Hz`: the step frequency sent to the XIAO for that MIDI note.
- `Pulse us`: derived timing value, calculated as `1,000,000 / Frequency`.
- Double-click a row: edit that MIDI note's frequency.

Use this tab when a specific note sounds bad on your physical motor. Change only that note first, save the profile, then replay the same section from the Player tab.

### NeoPixel Behavior

The firmware supports three NeoPixels, one per motor. During GUI playback, the PC still sends normal motor commands. The XIAO firmware lights the matching pixel when a motor note starts, turns it off when that note ends, and chooses color from the note frequency.

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

The GUI build uses `--windowed`, so normal status appears inside the app's Status log instead of a console window. If PyInstaller misses MIDI support on another machine, keep `--hidden-import=rtmidi` in the command.

## Credits

- The `David Scholten stepper table` pitch profile is based on `pitches.h` from the local `MidiSynth` stepper synth project, credited in that file as `Made By David Scholten, July 2020`.
