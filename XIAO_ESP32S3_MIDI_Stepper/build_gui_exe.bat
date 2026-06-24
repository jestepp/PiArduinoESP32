@echo off
setlocal

:: Ensure script runs from project folder
cd /d "%~dp0"

echo Checking for Python 3.12...
py -0p 2>nul | findstr /c:"-V:3.12" >nul
if errorlevel 1 (
  echo Python 3.12 was not found.
  echo Install Python 3.12, then run this build script again.
  echo Download: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo Installing runtime requirements and PyInstaller...
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install -r requirements.txt
py -3.12 -m pip install pyinstaller
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

echo Building GUI executable...
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name MIDI-Stepper-Player --hidden-import=rtmidi midi_stepper_gui.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo Build complete:
echo dist\MIDI-Stepper-Player.exe
pause
endlocal
