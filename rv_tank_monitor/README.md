# RV Tank Monitor for Raspberry Pi Pico W

This example shows how to read up to eight RV tank level sensors through an
8-channel optocoupler ("octocoupler") board using MicroPython on a Raspberry
Pi Pico W.  Many RV tank probes switch 12 V, which cannot be connected to the
Pico directly.  The optocoupler isolates the high-voltage side and outputs safe
5 V logic that the Pico can read.

## Hardware overview

- Raspberry Pi Pico W running MicroPython 1.20 or newer.
- 8-channel optocoupler or isolator board (for example PC817-based boards).
- RV tank level sensors (commonly empty, 1/3, 2/3 and full probes).
- Optional: two tanks can be monitored at once (fresh and grey) with the eight
  channels.  Update the configuration in `main.py` if you need a different
  mapping.

Wire the optocoupler outputs to the GPIO pins listed in `TANK_CONFIG`.  The
script assumes the outputs go HIGH (3.3 V) when a sensor is active.  If your
board pulls the pin low instead, set `ACTIVE_HIGH = False` in the script.

### Example wiring schematic

The figure below shows one way to wire the example `TANK_CONFIG` where the
"fresh" tank uses GPIO 0–3 and the "grey" tank uses GPIO 4–7.  Most
8-channel optocoupler breakout boards share the same pin order; adjust the
channel numbers if yours differs.

```
 RV Tank Probes (12 V)                           Optocoupler Board                     Pico W / 5 V Side
 ────────────────────────────                ────────────────────────────          ─────────────────────────
 Fresh tank EMPTY ───┬─[1 kΩ]──> IN0 LED  ->| ch0 |---- OUT0 ---------------------> GP0 (fresh empty)
 Fresh tank 1/3   ───┼─[1 kΩ]──> IN1 LED  ->| ch1 |---- OUT1 ---------------------> GP1 (fresh 1/3)
 Fresh tank 2/3   ───┼─[1 kΩ]──> IN2 LED  ->| ch2 |---- OUT2 ---------------------> GP2 (fresh 2/3)
 Fresh tank FULL  ───┴─[1 kΩ]──> IN3 LED  ->| ch3 |---- OUT3 ---------------------> GP3 (fresh full)
 Grey tank EMPTY  ───┬─[1 kΩ]──> IN4 LED  ->| ch4 |---- OUT4 ---------------------> GP4 (grey empty)
 Grey tank 1/3    ───┼─[1 kΩ]──> IN5 LED  ->| ch5 |---- OUT5 ---------------------> GP5 (grey 1/3)
 Grey tank 2/3    ───┼─[1 kΩ]──> IN6 LED  ->| ch6 |---- OUT6 ---------------------> GP6 (grey 2/3)
 Grey tank FULL   ───┴─[1 kΩ]──> IN7 LED  ->| ch7 |---- OUT7 ---------------------> GP7 (grey full)
                           │                 │   │                                  │
                           └─ Tank return ───┴───┴──> GND <─────────────────────────┘

 5 V supply (from RV or Pico VBUS) ───────────────────────────────────────────────> VCC (board) & Pico VSYS
 Pico GND ───────────────────────────────────────────────────────────────────────> GND (board)
```

Key points:

- Each probe feeds the LED side of a single optocoupler channel through a
  current-limiting resistor (1 kΩ is typical for 12 V probes).  The LED side
  shares the RV tank return/ground.
- Power the board's transistor side from 5 V (`VCC`) and connect its ground to
  the Pico W ground so the outputs share a reference.
- Route each channel output to the matching GPIO pin listed in
  `TANK_CONFIG`.  The example mapping above mirrors the default configuration
  in `main.py`.

## Usage

1. Copy `main.py` to the Pico's filesystem and rename it to `main.py` if you
   want it to run automatically on boot.
2. Edit the `TANK_CONFIG` dictionary to match the GPIO pins used for each tank.
3. Open a serial console (for example with Thonny) to watch the printed level
   updates.  Changes are only logged when a sensor transitions.

You can also import the `TankLevelSensor` class from another MicroPython module
if you plan to publish the readings over Wi-Fi or integrate them with Home
Assistant.
