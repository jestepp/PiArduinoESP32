# XIAO ESP32-S3 Sense Camera Server

This repo includes a second PlatformIO target for the Seeed Studio XIAO ESP32-S3 Sense camera board.

## Build and Flash

```powershell
pio run -e xiao_esp32s3_sense_camera
pio run -e xiao_esp32s3_sense_camera -t upload
pio device monitor -b 115200
```

The device creates a fallback access point:

- SSID: `XIAO-S3-Camera`
- Password: `camera1234`
- Web UI: `http://192.168.4.1`

If you enter router Wi-Fi credentials in the web UI or over BLE, the serial monitor prints the LAN address after reboot.

## Web UI

The built-in web server provides:

- `/` GUI with live MJPEG camera stream, camera settings, Wi-Fi setup, and GPIO assignment.
- `/stream` MJPEG stream for a browser, VLC, or Android WebView.
- `/capture` single JPEG frame.
- `/status` JSON status.
- `/gpio` GPIO read/write API.

The default camera mode is `SVGA` with JPEG quality `10`, which is a practical starting point for smooth streaming. Try `VGA` or `QVGA` for higher frame rate, and `XGA`, `SXGA`, or `UXGA` for more detail at lower frame rate.

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
xclk=20
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

This firmware also sets reset to GPIO1 and power-down to GPIO21, which are commonly required for reliable OV2640 startup on this board.
