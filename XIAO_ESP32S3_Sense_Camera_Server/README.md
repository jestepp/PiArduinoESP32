# XIAO ESP32-S3 Sense Camera Server

Standalone PlatformIO firmware and Android app scaffold for the Seeed Studio XIAO ESP32-S3 Sense camera board.

## What It Includes

- ESP32-S3 Sense firmware in `src/main.cpp`
- MJPEG web camera stream at `/stream`
- Browser GUI at `/` for viewing the camera, setting resolution/quality, Wi-Fi setup, and GPIO assignment
- SD photo saving, MJPEG recording, file browsing, download, delete, and playback
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
- Web UI: `http://169.254.4.1`

The web UI can save router Wi-Fi credentials. After reboot, the serial monitor prints the LAN URL.

## Boot Mode

Default boot state is intentionally conservative:

- BLE is off.
- Low-power Wi-Fi eco mode is enabled.
- Camera stream is disabled until manually started.
- Camera defaults to `QVGA` with JPEG quality no sharper than `18` for lower heat/load.
- Chip temperature is sampled about every 30 seconds and shown in the web UI.
- Web UI and SD/file APIs are available immediately.
- Single-frame capture and SD photo save still work without starting the live stream.

Use `Start Stream` in the web UI when you want live video. Use `Start BLE` only when you need BLE setup/config, then stop BLE again before streaming or recording.

## Wi-Fi Policy

The access point is configured for predictable local operation:

- AP SSID: `XIAO-S3-Camera`
- AP IP: `169.254.4.1`
- Subnet: `255.255.0.0`
- Channel: `6`
- Max AP clients: `4`
- Hostname: `xiao-s3-camera`
- Wi-Fi credentials are stored in Preferences, but Wi-Fi driver writes are non-persistent.

Eco mode:

- low transmit power
- Wi-Fi modem sleep enabled
- default boot mode
- recommended for setup, file browsing, still captures, and idle operation

Normal mode:

- higher transmit power
- Wi-Fi sleep disabled unless BLE is active
- recommended only when you need stronger range or live streaming stability

Diagnostics:

```text
GET /status
GET /wifi/status
GET /wifi/scan
```

`/status` reports AP clients, station RSSI, Wi-Fi power mode, sleep state, and stream state.

## Camera Tuning

Boot mode defaults to `QVGA`, JPEG quality `18`, fixed XCLK `20 MHz`.

- Higher frame rate: use `VGA` or `QVGA`
- Higher detail: use `XGA`, `SXGA`, or `UXGA`
- Sharper JPEG: lower quality number
- Smaller/faster JPEG: higher quality number

The best usable mode depends on Wi-Fi signal, power quality, browser/client speed, and whether PSRAM initializes.

Low-power mode is available in the web UI. It reduces Wi-Fi transmit power and forces the camera to `QVGA` with lighter JPEG settings. Selecting `VGA` or higher automatically uses normal power mode so the firmware does not clamp the setting back to `QVGA`.

The web UI separates capture/record resolution from stream preview resolution. If high-resolution live playback is unstable, enable lower stream preview mode and set preview to `QVGA`, `CIF`, or `VGA`. Still captures and recordings use the capture/record setting when the stream is stopped. The `/status` response includes both `frameSize` and `activeFrameSize` so you can see what the sensor is currently using.

Changing camera settings stops the live stream before restarting the camera driver. Start the stream again after applying resolution or quality changes. Leave BLE off while streaming or recording for the most stable and coolest operation.

Recording target FPS is capped by resolution:

| Resolution | Max target FPS |
|---|---:|
| `QVGA` | 25 |
| `CIF` | 20 |
| `VGA` | 15 |
| `SVGA` | 10 |
| `XGA` | 6 |
| `SXGA` | 4 |
| `UXGA` | 2 |

These are target caps, not guaranteed output rates. `/status` reports `recordingTargetFps`, `recordingMaxFps`, and `recordingActualFps`.

## Thermal Telemetry

The ESP32-S3 internal temperature sensor is displayed in the web UI and returned by `/status`. This is chip die temperature, not room temperature, so use it as a load/heat warning rather than a calibrated thermometer.

The firmware samples temperature every 30 seconds to avoid adding unnecessary CPU load. Thermal states are:

- `normal`: below `55 C`
- `warm`: `55 C` to `69 C`
- `hot`: `70 C` to `79 C`
- `critical`: `80 C` or higher

By default, critical temperature auto-stops the stream and any active MJPEG recording. The web UI can switch this to warn-only mode if you want to ignore firmware warnings and rely on the ESP32-S3 hardware/system protections instead. Warn-only mode still displays the temperature and state.

Status fields:

```text
chipTempC
chipTempValid
thermalState
thermalAutoStop
thermalStoppedStream
thermalSampleIntervalMs
thermalSampleAgeMs
```

Controls:

```text
POST /thermal autoStop=on
POST /thermal autoStop=off
BLE write: thermal=stop
BLE write: thermal=warn
```

## SD Storage

The web UI can save still photos and record short MJPEG clips to the XIAO ESP32-S3 Sense microSD slot.

Open the SD file manager at:

```text
http://169.254.4.1/explorer
```

Storage endpoints:

```text
POST /photo/save
POST /record/start      fps=1..15
POST /record/stop
GET  /files             optional dir=/camera
GET  /explorer
GET  /file/view?path=/camera/photos/example.jpg
GET  /play?path=/camera/videos/example.mjpeg
GET  /file/download?path=/camera/photos/example.jpg
POST /file/delete       path=/camera/photos/example.jpg
POST /mkdir             dir=/camera name=profiles
POST /upload            dir=/camera/uploads multipart file upload
```

Photos are saved as JPEG files under `/camera/photos`. Videos are saved as `.mjpeg` files under `/camera/videos`. These are multipart MJPEG clips, not MP4/H.264 files. They play back through the built-in `/play` endpoint and can be downloaded for conversion later on a PC.

The Sense SD slot uses GPIO21 for CS, GPIO7 for SCK, GPIO8 for MISO, and GPIO9 for MOSI. Those pins are reserved while SD support is enabled.

The SD card can store media, configuration files, presets, command scripts, profiles, and uploaded assets. It cannot add compiled Arduino C++ libraries at runtime. Support for hardware such as stepper motors, NeoPixels, servos, or sensors must be compiled into the firmware first; SD files can then configure pins, presets, sequences, and behavior for those compiled features.

## SD Theme Assets

Large GUI assets are loaded from the SD card instead of firmware flash. The web UI looks for:

```text
/camera/assets/theme.png
```

The repo includes a ready-to-copy seed file:

```text
sdcard_seed/camera/assets/theme.png
```

Copy the contents of `sdcard_seed` to the root of the microSD card, or upload `theme.png` to `/camera/assets` using `/explorer`. If the image is missing, the firmware falls back to the embedded CSS gradient theme.

## SD Module Workflow

The firmware checks the SD card at boot for module manifests in:

```text
/camera/modules
```

Each module gets its own folder with a `module.json` file:

```text
/camera/modules/example-neopixel/module.json
/camera/modules/example-neopixel/config.json
```

The scanner exposes the inventory at:

```text
GET /modules
```

This is a runtime configuration and update workflow, not dynamic C++ linking. A module can declare required firmware capabilities such as `neopixel`, `stepper`, `servo`, or `sensor`, and store configs/scripts/assets on SD. If a module needs a new compiled Arduino library, add that library to `platformio.ini`, implement the firmware handler, rebuild, and flash. After that, SD module files can configure and update behavior without recompiling.

The repo includes a seed example:

```text
sdcard_seed/camera/modules/example-neopixel/module.json
```

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
power=low
power=normal
photo=1
record=start
record=stop
reboot=1
```

## Notes

ESP32-S3 supports BLE, not Bluetooth Classic serial. Video is streamed over Wi-Fi because BLE does not have the bandwidth for a practical live camera feed.

See `docs/xiao_esp32s3_sense_camera.md` for endpoint and GPIO details.

See `docs/ai_tracking_options.md` for AI/object/face tracking implementation options.

See `docs/sd_modules.md` for SD module expectations, limits, and update workflow.
