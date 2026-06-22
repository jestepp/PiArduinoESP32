# DROK 200310 UART Dashboard for Raspberry Pi Pico W (PlatformIO)

This is a **PlatformIO-ready** project for a **Raspberry Pi Pico W** that:

- reads live **output voltage** from the DROK 200310
- reads live **output current**
- calculates **watts**
- provides a simple web UI for:
  - setting voltage
  - setting current
  - output ON/OFF
  - recalling memory slots M0-M9
- shows a simple **scope-style trend graph** of UART data history

## Important note
This is for **Raspberry Pi Pico W**, not a Linux Raspberry Pi 4/5.

Why: **PlatformIO is a much better fit for microcontrollers** like Pico W / ESP32. If you wanted this to run on a full Raspberry Pi OS machine instead, I can build a separate Python + Flask version.

## Wiring

DROK UART -> Pico W

- DROK TX -> Pico W GP5 (UART RX)
- DROK RX -> Pico W GP4 (UART TX)
- DROK GND -> Pico W GND

### Safety note
Only connect UART directly if your DROK UART lines are actually 3.3V-safe.
If the DROK board is outputting higher logic, use a level shifter before the Pico RX pin.

## Config
Edit these at the top of `src/main.cpp`:

- `WIFI_SSID`
- `WIFI_PASS`
- `UART_TX_PIN`
- `UART_RX_PIN`
- `UART_BAUD`

Default baud is `4800`.

## Build / upload

1. Open this folder in VS Code
2. Open PlatformIO
3. Build
4. Upload
5. Open serial monitor at `115200`
6. Note the assigned IP address
7. Browse to that IP from your phone or PC

## UART commands used
The code currently uses these basic commands:

- `aru` read actual voltage
- `ari` read actual current
- `awu####` set voltage
- `awi####` set current
- `awo0` / `awo1` output off/on
- `awm0..9` recall memory slots

## Known limitation
This is **not a real oscilloscope**.
It is a **trend graph** based on UART measurements from the power supply.
That is good for slow changes, ramps, current draw, battery charging, and load monitoring.
It is not good for viewing fast ripple or switching waveforms.
