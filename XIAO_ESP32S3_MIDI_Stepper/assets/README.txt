Place a Windows ICO file here named `app.ico` if you want an embedded icon in the EXE.

Recommended size: include multiple sizes in the ICO (16x16, 32x32, 48x48, 256x256) for best results.

Example usage with PyInstaller (from project root):

pyinstaller --onefile --icon=assets/app.ico launcher.py

Or use the provided spec file:

pyinstaller launcher.spec

Note: The spec references `assets/app.ico` as the icon path.
