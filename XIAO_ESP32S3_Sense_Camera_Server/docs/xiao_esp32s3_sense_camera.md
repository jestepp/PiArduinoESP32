# XIAO ESP32-S3 Sense Camera Server

This repo is a standalone PlatformIO project for the Seeed Studio XIAO ESP32-S3 Sense camera board.

## Build and Flash

```powershell
pio run -e xiao_esp32s3_sense_camera
pio run -e xiao_esp32s3_sense_camera -t upload
pio device monitor -b 115200
```

The device creates a fallback access point:

- SSID: `XIAO-S3-Camera`
- Password: `camera1234`
- Web UI: `http://169.254.4.1`

If you enter router Wi-Fi credentials in the web UI or over BLE, the serial monitor prints the LAN address after reboot.

## Boot Mode

The firmware boots in a low-load state:

- BLE off
- low-power Wi-Fi eco mode
- live MJPEG stream off
- camera configured for low-power defaults
- chip temperature sampled about every 30 seconds

The web UI remains available at boot. Start live video manually from the web UI when needed.

## Wi-Fi Operation

The fallback AP is intentionally deterministic:

- IP: `169.254.4.1`
- subnet: `255.255.0.0`
- channel: `6`
- max clients: `4`
- hostname: `xiao-s3-camera`

Eco mode uses lower transmit power and modem sleep. Normal mode raises transmit power and disables modem sleep unless BLE is active. BLE and Wi-Fi together require modem sleep on ESP32-S3.

Useful endpoints:

- `/wifi/status`
- `/wifi/scan`

## Web UI

The built-in web server provides:

- `/` GUI with live MJPEG camera stream, camera settings, Wi-Fi setup, and GPIO assignment.
- `/stream` MJPEG stream for a browser, VLC, or Android WebView.
- `/capture` single JPEG frame.
- `/photo/save` saves one JPEG frame to SD.
- `/record/start` starts MJPEG recording to SD. POST `fps=5` or another value from 1-15.
- `/record/stop` stops recording.
- `/files` lists saved photos and videos.
- `/play?path=...` plays back a saved JPEG or MJPEG clip.
- `/file/download?path=...` downloads a saved file.
- `/file/delete` deletes a saved file. POST `path=/camera/photos/name.jpg`.
- `/status` JSON status.
- `/gpio` GPIO read/write API.

Boot mode defaults to `QVGA` with JPEG quality `18`. The camera XCLK is fixed at `20 MHz`; the lower XCLK options were removed because they were not reliable on this board. Try `VGA` for higher detail than boot mode, and `XGA`, `SXGA`, or `UXGA` for more detail at lower frame rate and higher heat/load.

Low-power mode is available in the web UI and over BLE with `power=low`. It lowers Wi-Fi transmit power and forces `QVGA` with lighter JPEG settings. Selecting `VGA` or higher in the web UI automatically uses normal power mode so the firmware does not clamp the setting back to `QVGA`.

The web UI has separate controls for capture/record resolution and stream preview resolution. Enable lower stream preview mode when live playback is unstable, then use `QVGA`, `CIF`, or `VGA` for the stream while keeping a higher capture/record target. Because the OV2640 only outputs one frame size at a time, `/status` reports both `frameSize` and `activeFrameSize`.

Applying camera settings stops the live stream, restarts the camera driver, and leaves the stream off until you manually start it again.

Recording target FPS is capped by the selected capture/record resolution:

| Resolution | Max target FPS |
|---|---:|
| `QVGA` | 25 |
| `CIF` | 20 |
| `VGA` | 15 |
| `SVGA` | 10 |
| `XGA` | 6 |
| `SXGA` | 4 |
| `UXGA` | 2 |

The cap is a requested target, not a guaranteed saved frame rate. `/status` reports `recordingTargetFps`, `recordingMaxFps`, and `recordingActualFps`.

## Thermal Display and Protection

The web UI displays the ESP32-S3 internal chip temperature. This is die temperature, not ambient temperature, and is meant as a rough load/heat indicator.

The firmware samples every 30 seconds. Thermal states are:

- `normal`: below `55 C`
- `warm`: `55 C` to `69 C`
- `hot`: `70 C` to `79 C`
- `critical`: `80 C` or higher

Default behavior is to auto-stop live stream and active MJPEG recording at `critical`. You can change this in the web UI to warn-only mode. Warn-only mode keeps showing the warning but leaves stream/recording control to you and the ESP32-S3 hardware/system protections.

Relevant APIs:

- `POST /thermal` with `autoStop=on` or `autoStop=off`
- `/status` fields `chipTempC`, `chipTempValid`, `thermalState`, `thermalAutoStop`, `thermalStoppedStream`, `thermalSampleIntervalMs`, and `thermalSampleAgeMs`
- BLE writes `thermal=stop` or `thermal=warn`

## SD Storage

The firmware mounts the Sense microSD slot during startup and creates:

```text
/camera/photos
/camera/videos
/camera/assets
/camera/modules
```

Still captures are stored as `.jpg`. Recordings are stored as `.mjpeg` multipart frame streams. The ESP32-S3 does not encode MP4/H.264 in this firmware; use a PC tool later if you need to convert MJPEG clips to another container.

The SD slot uses:

- CS: GPIO21
- SCK: GPIO7
- MISO: GPIO8
- MOSI: GPIO9

Use a FAT32 microSD card, 32GB or smaller. If mounting fails, fully reformat the card as FAT32 and check the Sense board SD jumper/pads.

Large web UI assets are served from `/camera/assets` through URLs like `/assets/theme.png`. If `/camera/assets/theme.png` is present, the camera GUI and explorer use it as the background. If it is missing, the embedded CSS fallback remains active.

## SD Modules

At boot, the firmware scans `/camera/modules/*/module.json` and reports the discovered modules on serial and at `/modules`.

This supports SD-based configuration packs and update bundles. It does not load new compiled C++ libraries from SD at runtime. Add compiled capabilities in firmware first, then use SD module manifests and config files to control those capabilities.

## BLE Setup

The ESP32-S3 has BLE, not Bluetooth Classic serial. The firmware advertises as `XIAO-S3-Camera`.

Service UUID:

```text
b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201
```

Config characteristic UUID:

```text
b2b7f441-1c2a-45a8-a7c7-8fd6f7d90201
```

Write UTF-8 lines:

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

Reading the characteristic returns the same JSON status as `/status`.

## GPIO Notes

The camera consumes GPIO `1`, `10`-`18`, `21`, `38`-`40`, `47`, and `48`. The GUI intentionally exposes regular user pins only. Avoid reassigning camera pins unless the camera module is removed.

## Camera Pin Source

The Sense camera connector mapping follows Seeed's XIAO ESP32-S3 Sense camera documentation:

- XCLK: GPIO10
- D0-D7: GPIO15, GPIO17, GPIO18, GPIO16, GPIO14, GPIO12, GPIO11, GPIO48
- PCLK: GPIO13
- VSYNC: GPIO38
- HREF: GPIO47
- SCCB SCL/SDA: GPIO39/GPIO40

This firmware leaves camera reset and power-down disabled (`-1`) to match the common XIAO ESP32-S3 Sense camera definition and avoid conflicting with GPIO21, which is used by the microSD card chip select.
