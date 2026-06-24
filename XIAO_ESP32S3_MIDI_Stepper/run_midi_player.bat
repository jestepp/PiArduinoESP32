@echo off
setlocal

:: Ensure script runs from project folder
cd /d "%~dp0"

echo Checking for Python...
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Please install Python 3 and add it to PATH.
  pause
  exit /b 1
)

echo Installing/upgrading pip and required Python packages (may take a minute)...
python -m pip install --upgrade pip
python -m pip install -r "requirements.txt"
if errorlevel 1 (
  echo Failed to install Python dependencies. If you have a virtualenv, activate it and re-run this script.
  pause
)

echo.
echo Ensure loopMIDI (or your MIDI port provider) is running before starting.
echo.
set /p COMPORT=Enter XIAO COM port (for example COM3):
if "%COMPORT%"=="" (
  echo No COM port provided. Exiting.
  pause
  exit /b 1
)

set /p PITCH=Enable pitch bending? (y/N):
if /I "%PITCH%"=="y" (
  set "PB=pitch_bending"
) else (
  set "PB="
)

echo Starting MIDI bridge connecting to %COMPORT%...

REM Launch Python bridge. It will prompt to choose a MIDI input port.
python midi_interface.py "%COMPORT%" %PB%

echo.
echo MIDI bridge exited. Press any key to close.
pause >nul
endlocal
