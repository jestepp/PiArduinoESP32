# Wiring (text-only)

This project uses a Seeed XIAO ESP32-S3 as the controller, three stepper motor drivers, and an external motor power supply.

XIAO -> Stepper driver signal wiring (default pins used in `src/main.cpp`):

- GPIO2  -> STEP0
- GPIO5  -> DIR0
- GPIO3  -> STEP1
- GPIO6  -> DIR1
- GPIO4  -> STEP2
- GPIO7  -> DIR2
- GPIO8  -> ENABLE (shared enable for drivers)
- GPIO9  -> NeoPixel DIN (3 LEDs chained, one LED per motor)

Important notes and safety:

- Connect all stepper driver GND pins to the XIAO GND. The drivers and XIAO must share a common ground.
- Power the stepper drivers from an external motor supply (for example 12V). Do NOT power the motors from the XIAO USB.
- Keep motor power wiring separate from logic wiring as much as possible; use short, thick wires for motor supply and twisted pairs where appropriate.
- Before connecting motors to drivers, verify coil pair polarity using a multimeter or the paperclip polarity test; reversed coils will reduce torque or cause poor operation.
- Set current limit on your driver (A4988/DRV8825 or similar) appropriately for your motors before running at full speed.
- NeoPixels should share ground with the XIAO. Use an external 5V LED supply for anything beyond a tiny test setup, and keep the LED 5V supply separate from the stepper motor supply.
- Add a 330-470 ohm resistor between GPIO9 and the first NeoPixel DIN. A capacitor across the LED 5V/GND input is also recommended for strips or rings.
- Pixel order is motor order: pixel 0 = motor 0, pixel 1 = motor 1, pixel 2 = motor 2. A pixel turns on with its motor note and turns off when that motor note ends.

MIDI and host-side bridge (recommended flow):

- The XIAO runs a serial command firmware (see `src/main.cpp`). MIDI is parsed on the host PC by `midi_interface.py`.
- Connect the XIAO to the PC over USB. Run the Python bridge:

```bash
.\setup_midi_player.bat
.\run_midi_player.bat
```

- Start loopMIDI and create a virtual MIDI port, or connect a MIDI input device.
- Select the desired MIDI input port when prompted and play notes on MIDI channels 0, 1 and 2 (they map to motors 0..2).

Troubleshooting quick tips:

- If motors do not move, verify the shared `ENABLE` pin state and that each driver's `STEP`/`DIR` pins are connected to the pins listed above.
- If movement sounds wrong, re-check motor coil polarity and driver current limit.
- Use the serial monitor at `115200` to view status messages from the firmware.

If you want the wiring document converted to a printable PDF or a separate schematic SVG later, say so and I will add that.
# Wiring Diagrams

This project uses a Seeed XIAO ESP32-S3 as the controller, three stepper motor drivers, and an external power supply for the motors.

## XIAO to Stepper Driver Wiring

- `GPIO2` -> `STEP0`
- `GPIO5` -> `DIR0`
- `GPIO3` -> `STEP1`
- `GPIO6` -> `DIR1`
- `GPIO4` -> `STEP2`
- `GPIO7` -> `DIR2`
- `GPIO8` -> `ENABLE`
- `GPIO9` / `D10` -> `NeoPixel DIN`

### Notes
- All stepper driver grounds must be connected to the XIAO ground.
- Motor power must come from the stepper driver power supply, not the XIAO USB.
- Use separate wiring for motor power and logic power when possible.
- NeoPixel ground must also connect to XIAO ground. NeoPixel 5V should come from a suitable 5V supply, not the 24V motor supply.

## NeoPixel Status LEDs

This project supports one NeoPixel per motor without changing the stepper wiring.

- Use a 3-pixel WS2812/NeoPixel strip, stick, or three chained pixels.
- Wire `GPIO9` / `D10` to the first pixel `DIN`.
- Wire first pixel `DOUT` to second pixel `DIN`, then second `DOUT` to third `DIN`.
- Pixel 0 follows motor 0, pixel 1 follows motor 1, and pixel 2 follows motor 2.
- The firmware lights a pixel when a note starts, turns it off when that note ends, and chooses the color from the note frequency.

NeoPixel power wiring:

- XIAO `GND` -> NeoPixel `GND`
- External regulated `5V` -> NeoPixel `5V`
- XIAO `GPIO9` / `D10` -> `330-470 ohm resistor` -> first NeoPixel `DIN`
- Do not connect NeoPixels directly to the stepper motor voltage supply.

## Example Diagram

![XIAO Stepper Wiring](images/xiao_stepper_wiring.svg)

## Reference Images

The following real-device reference photos are pulled from the example MIDI stepper project and show the type of stepper enable wiring and motor driver setup used in similar builds.

![Stepper driver enable jumper](images/a_stepper_enable.png)
*Example: stepper driver enable jumper configuration.*

![Stepper motor polarity test](images/polarity_test.jpg)
*Example: verifying stepper coil polarity before connecting to the driver.*

![Driver and motor layout](images/motor_5_configuration.png)
*Example: stepper driver board and motor wiring layout.*

## MIDI / Serial Bridge Wiring

For this project, MIDI is interpreted on the host PC and sent to the XIAO via USB serial.

- XIAO USB -> PC USB
- Host runs `midi_interface.py`
- MIDI input port selected from your DAW or MIDI device
