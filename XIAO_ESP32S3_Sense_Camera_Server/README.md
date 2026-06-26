# XIAO ESP32-S3 Sense Camera Server

Standalone PlatformIO firmware and Android app scaffold for the Seeed Studio XIAO ESP32-S3 Sense camera board.

## What It Includes

- ESP32-S3 Sense firmware in `src/main.cpp`
- MJPEG web camera stream at `/stream`
- Browser GUI at `/` for viewing the camera, setting resolution/quality, Wi-Fi setup, and GPIO assignment
- BLE configuration service for Android setup
- Minimal Android app project in `android/CameraControlApp`

## Firmware Build

Open this folder in VS Code with PlatformIO, then run:

```powershell
pio run -e xiao_esp32s3_sense_camera
pio run -e xiao_esp32s3_sense_camera -t upload
pio device monitor -b 115200
```

After boot, connect to the fallback access point:

- SSID: `XIAO-S3-Camera`
- Password: `camera1234`
- Web UI: `http://192.168.4.1`

The web UI can save router Wi-Fi credentials. After reboot, the serial monitor prints the LAN URL.

## Camera Tuning

Default mode is `SVGA`, JPEG quality `10`, XCLK `20 MHz`.

- Higher frame rate: use `VGA` or `QVGA`
- Higher detail: use `XGA`, `SXGA`, or `UXGA`
- Sharper JPEG: lower quality number
- Smaller/faster JPEG: higher quality number

The best usable mode depends on Wi-Fi signal, power quality, browser/client speed, and whether PSRAM initializes.

## Android App

Open `android/CameraControlApp` in Android Studio and build an APK from:

```text
Build > Build Bundle(s) / APK(s) > Build APK(s)
```

The app loads the camera web UI in a WebView and can send Wi-Fi credentials over BLE.

This computer currently has Java on `PATH`, but no `pio`, `gradle`, or Android SDK command-line build tools, so I could not compile firmware or produce an APK locally from the terminal.

## BLE Config

Device name: `XIAO-S3-Camera`

Service UUID:

```text
b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201
```

Config characteristic UUID:

```text
b2b7f441-1c2a-45a8-a7c7-8fd6f7d90201
```

Write UTF-8 commands:

```text
ssid=YourRouterName
pass=YourRouterPassword
framesize=VGA
quality=10
xclk=20
reboot=1
```

## Notes

ESP32-S3 supports BLE, not Bluetooth Classic serial. Video is streamed over Wi-Fi because BLE does not have the bandwidth for a practical live camera feed.

See `docs/xiao_esp32s3_sense_camera.md` for endpoint and GPIO details.
