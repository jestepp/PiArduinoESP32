# SD Module Architecture

SD modules are configuration and asset packs stored on the microSD card.

They are not dynamically loaded Arduino C++ libraries. The ESP32 firmware must already contain the compiled capability that a module wants to control.

## Core Rule

```text
Firmware = compiled capabilities
SD modules = runtime configuration for those capabilities
```

Examples:

- If the firmware includes NeoPixel support, an SD module can define LED pin, count, colors, animations, and brightness.
- If the firmware does not include NeoPixel support, the module can be detected and reported, but it cannot run LED code.
- If the firmware includes stepper support, an SD module can define STEP/DIR pins, speed, acceleration, scan patterns, and tracking behavior.
- If the firmware does not include stepper support, the SD module acts as a pending requirement until firmware is rebuilt.

## Boot-Time Scan

At boot, the firmware mounts the SD card and scans:

```text
/camera/modules/*/module.json
```

The scan result is:

- printed to serial
- included in `/status` as `moduleCount`
- exposed through `/modules`

The scanner currently reads each `module.json` and extracts lightweight metadata:

- `name`
- `version`
- `type`
- module folder path
- manifest path

## Folder Layout

Recommended layout:

```text
/camera/modules/module-name/module.json
/camera/modules/module-name/config.json
/camera/modules/module-name/assets/
/camera/modules/module-name/scripts/
```

Example:

```text
/camera/modules/example-neopixel/module.json
/camera/modules/example-neopixel/config.json
```

## Manifest Format

Example `module.json`:

```json
{
  "name": "example-neopixel",
  "version": "0.1.0",
  "type": "lighting",
  "requiresFirmware": ["neopixel"],
  "description": "LED status and animation config.",
  "entry": "config.json"
}
```

Expected fields:

- `name`: stable module name
- `version`: module config version
- `type`: broad category such as `lighting`, `motion`, `tracking`, `theme`, `automation`, or `sensor`
- `requiresFirmware`: firmware capabilities required before this module can run
- `entry`: primary config file

## Update Workflow

Use this workflow when adding new behavior:

1. Add a module folder to `/camera/modules`.
2. Add a `module.json` with `requiresFirmware`.
3. Reboot or refresh the module inventory.
4. Check `/modules`.
5. If the required capability is already compiled into firmware, the module can be used by that firmware handler.
6. If the required capability is missing, add the C++ library and firmware handler to the PlatformIO project, rebuild, and flash.
7. After the capability exists in firmware, update config files on SD without reflashing.

## What SD Modules Are Good For

- pin assignments
- camera presets
- LED animation presets
- motor profiles
- movement sequences
- tracking thresholds
- timelapse schedules
- saved UI themes
- generated assets
- automation rules
- per-device configuration

## What SD Modules Cannot Do

SD modules cannot:

- load new compiled C++ code at runtime
- install Arduino libraries directly onto the ESP32
- add `AccelStepper`, `Adafruit_NeoPixel`, ESP-WHO, or other libraries without rebuilding firmware
- change flash partition layout
- replace bootloader or firmware binaries

## Example Module Ideas

### `neopixel-status`

Built for LED strips or pixels.

Possible config:

- data pin
- LED count
- brightness
- boot color
- recording animation
- Wi-Fi connected animation
- error animation

Requires firmware capability:

```json
"requiresFirmware": ["neopixel"]
```

### `stepper-pan-tilt`

Built for stepper-controlled camera aiming.

Possible config:

- pan STEP/DIR pins
- tilt STEP/DIR pins
- max speed
- acceleration
- home position
- scan pattern
- tracking response scale

Requires firmware capability:

```json
"requiresFirmware": ["stepper"]
```

### `servo-pan-tilt`

Built for hobby-servo camera aiming.

Possible config:

- pan pin
- tilt pin
- min/max pulse
- center angle
- smoothing
- tracking gain

Requires firmware capability:

```json
"requiresFirmware": ["servo"]
```

### `ai-face-tracking`

Built for face/object tracking configuration.

Possible config:

- detection threshold
- target box size
- tracking smoothing
- snapshot-on-detect
- pan/tilt output mode

Requires firmware capability:

```json
"requiresFirmware": ["tracking"]
```

### `theme-pack-anime-beach`

Built for UI styling.

Possible config/assets:

- `/camera/assets/theme.png`
- colors
- dashboard labels
- icon files

Requires firmware capability:

```json
"requiresFirmware": ["sd-assets"]
```

## Current Implementation Status

Implemented now:

- SD card mount
- `/camera/modules` directory creation
- boot-time module scan
- serial module count logging
- `/modules` JSON endpoint
- `/status` module count
- SD explorer upload/download/delete support
- example module seed in `sdcard_seed`

Not implemented yet:

- executing module behavior
- validating `requiresFirmware` against a capability registry
- applying module configs to hardware handlers
- module enable/disable state
- module version migration

Those are the next firmware layers after the basic SD module inventory is stable.
