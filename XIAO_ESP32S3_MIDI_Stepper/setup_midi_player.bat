@echo off
setlocal EnableDelayedExpansion

:: Ensure script runs from project folder
cd /d "%~dp0"

echo Checking for Python 3.12...
py -0p 2>nul | findstr /c:"-V:3.12" >nul
if errorlevel 1 (
  echo Python 3.12 was not found.
  echo Install Python 3.12, then run this setup script again.
  echo Download: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo Installing/upgrading pip and required Python packages...
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install -r "requirements.txt"
if errorlevel 1 (
  echo Failed to install Python dependencies.
  pause
  exit /b 1
)

echo.
echo Setup complete. You can now run run_midi_player.bat.
pause
endlocal
