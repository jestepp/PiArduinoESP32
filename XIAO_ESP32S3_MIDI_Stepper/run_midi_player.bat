@echo off
setlocal EnableDelayedExpansion

:: Ensure script runs from project folder
cd /d "%~dp0"

:menu
cls
echo XIAO ESP32-S3 MIDI Stepper Player
echo.
echo 1. Start live MIDI bridge
echo 2. Play MIDI file directly
echo 3. Exit
echo.
choice /c 123 /n /m "Choose an option [1-3]: "
if errorlevel 3 goto exit_script
if errorlevel 2 goto play_file
if errorlevel 1 goto start_bridge

:start_bridge
cls
set "COMPORT="
set "PB="
echo.
echo Ensure loopMIDI (or your MIDI port provider) is running before starting.
echo.
set /p COMPORT=Enter XIAO COM port (for example COM3):
if "%COMPORT%"=="" (
  echo No COM port provided.
  echo Press any key to return to the main menu.
  pause >nul
  goto menu
)

set /p PITCH=Enable pitch bending? (y/N):
if /I "%PITCH%"=="y" (
  set "PB=pitch_bending"
) else (
  set "PB="
)

echo Starting MIDI bridge connecting to %COMPORT%...

REM Launch Python bridge. It will prompt to choose a MIDI input port.
py -3.12 midi_interface.py "%COMPORT%" %PB%

echo.
echo MIDI bridge exited.
echo Press any key to return to the main menu.
pause >nul
goto menu

:play_file
cls
set "COMPORT="
set "MIDIFILE="
set "PLAYMODE="
set "SOURCECHANNEL="
set "TRANSPOSE="
set "LOUDNESSMOTORS="
echo.
set /p COMPORT=Enter XIAO COM port (for example COM3):
if "%COMPORT%"=="" (
  echo No COM port provided.
  echo Press any key to return to the main menu.
  pause >nul
  goto menu
)

echo.
echo Drag a .mid file here, or type its full path.
set /p MIDIFILE=MIDI file:
set "MIDIFILE=%MIDIFILE:"=%"
if "%MIDIFILE%"=="" (
  echo No MIDI file provided.
  echo Press any key to return to the main menu.
  pause >nul
  goto menu
)

set /p AUTOSINGLE=Auto-simplify for 1 motor? (y/N):
if /I "%AUTOSINGLE%"=="y" (
  set "PLAYMODE=--auto-single-motor"
) else (
set /p AUTOARRANGE=Auto-arrange for 3 motors? (y/N):
if /I "!AUTOARRANGE!"=="y" (
  set "PLAYMODE=--auto-three-motor"
) else (
set /p SINGLEMOTOR=Play all notes on one stepper only? (y/N):
if /I "!SINGLEMOTOR!"=="y" (
  set "PLAYMODE=--motor 0"
  set /p SOURCECHANNEL=Only play one MIDI channel? Enter 1-16, or press Enter for all:
  if not "!SOURCECHANNEL!"=="" set "PLAYMODE=!PLAYMODE! --source-channel !SOURCECHANNEL!"
) else (
  set "PLAYMODE="
  set /p LOUDNESSMOTORS=Duplicate notes across how many motors for loudness? Enter 1-3:
  if not "!LOUDNESSMOTORS!"=="" set "PLAYMODE=!PLAYMODE! --loudness-motors !LOUDNESSMOTORS!"
  set /p SOURCECHANNEL=Only play one MIDI channel? Enter 1-16, or press Enter for all:
  if not "!SOURCECHANNEL!"=="" set "PLAYMODE=!PLAYMODE! --source-channel !SOURCECHANNEL!"
)
)
)
set /p TRANSPOSE=Transpose pitch in semitones? Examples 12, -12, or press Enter for none:
if not "!TRANSPOSE!"=="" set "PLAYMODE=!PLAYMODE! --transpose !TRANSPOSE!"

:play_selected_file
echo Playing MIDI file on %COMPORT%...
py -3.12 midi_file_player.py "%COMPORT%" "%MIDIFILE%" %PLAYMODE%

echo.
echo MIDI file playback finished.
echo.
echo 1. Play this file again
echo 2. Wait 60 seconds, then play this file again
echo 3. Choose another MIDI file
echo 4. Return to main menu
echo.
choice /c 1234 /n /m "Choose an option [1-4]: "
if errorlevel 4 goto menu
if errorlevel 3 goto choose_another_file
if errorlevel 2 goto cooldown_then_replay
if errorlevel 1 goto play_selected_file

:cooldown_then_replay
echo.
echo Cooling down for 60 seconds...
timeout /t 60
goto play_selected_file

:choose_another_file
cls
set "MIDIFILE="
echo.
echo Drag a .mid file here, or type its full path.
set /p MIDIFILE=MIDI file:
set "MIDIFILE=%MIDIFILE:"=%"
if "%MIDIFILE%"=="" (
  echo No MIDI file provided.
  echo Press any key to return to the main menu.
  pause >nul
  goto menu
)
set /p AUTOSINGLE=Auto-simplify for 1 motor? (y/N):
if /I "%AUTOSINGLE%"=="y" (
  set "PLAYMODE=--auto-single-motor"
) else (
set /p AUTOARRANGE=Auto-arrange for 3 motors? (y/N):
if /I "!AUTOARRANGE!"=="y" (
  set "PLAYMODE=--auto-three-motor"
) else (
set /p SINGLEMOTOR=Play all notes on one stepper only? (y/N):
if /I "!SINGLEMOTOR!"=="y" (
  set "PLAYMODE=--motor 0"
  set /p SOURCECHANNEL=Only play one MIDI channel? Enter 1-16, or press Enter for all:
  if not "!SOURCECHANNEL!"=="" set "PLAYMODE=!PLAYMODE! --source-channel !SOURCECHANNEL!"
) else (
  set "PLAYMODE="
  set /p LOUDNESSMOTORS=Duplicate notes across how many motors for loudness? Enter 1-3:
  if not "!LOUDNESSMOTORS!"=="" set "PLAYMODE=!PLAYMODE! --loudness-motors !LOUDNESSMOTORS!"
  set /p SOURCECHANNEL=Only play one MIDI channel? Enter 1-16, or press Enter for all:
  if not "!SOURCECHANNEL!"=="" set "PLAYMODE=!PLAYMODE! --source-channel !SOURCECHANNEL!"
)
)
)
set /p TRANSPOSE=Transpose pitch in semitones? Examples 12, -12, or press Enter for none:
if not "!TRANSPOSE!"=="" set "PLAYMODE=!PLAYMODE! --transpose !TRANSPOSE!"
goto play_selected_file

:exit_script
endlocal
exit /b 0
