"""RV tank level monitor for Raspberry Pi Pico W.

This module reads up to eight digital inputs connected through an
8-channel optocoupler board that translates 12 V tank sensor signals to
5 V logic that is safe for the Pico W.  The script groups the inputs
into named tanks and exposes helper classes that debounce the signals
and compute a coarse fill percentage.

Usage
-----
Copy this file to the board (for MicroPython place it as ``main.py`` or
``rv_tank_monitor.py`` on the Pico W).  Adjust the ``TANK_CONFIG``
dictionary below to match the pins you use for each tank.  Each tank
expects a list of four pins that correspond to sensors installed at the
Empty, 1/3, 2/3 and Full positions.  Additional tanks can be added as
long as you stay within the eight available channels.

By default the script prints level changes to the serial console.  The
``TankLevelSensor`` class can also be imported from another module if
you want to integrate the readings into a network service.

Hardware assumptions
--------------------
* The optocoupler output is ``HIGH`` (logic 1) when the corresponding
  tank sensor is active.  Set ``ACTIVE_HIGH`` to ``False`` if your board
  pulls the signal low instead.
* The Pico W pins use the built-in pull-down resistors so that inactive
  channels read as logic ``0``.  Adjust the ``pin_kwargs`` argument of
  ``DebouncedInput`` if you need a different pull configuration.
"""

import time
from machine import Pin

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Time (in milliseconds) the input must stay stable before a state change is
# accepted.  Increase this value if your tank sensors cause more bounce.
DEBOUNCE_MS = 100

# Whether the optocoupler outputs are active-high.  Set to False if a sensor
# pulls the line low when active.
ACTIVE_HIGH = True

# Map each tank name to the GPIO pins that feed the corresponding sensors.
# The order is: Empty, 1/3, 2/3, Full.
TANK_CONFIG = {
    "fresh": [0, 1, 2, 3],
    "grey": [4, 5, 6, 7],
}

# ---------------------------------------------------------------------------
# Helper classes
# ---------------------------------------------------------------------------


class DebouncedInput:
    """A digital input pin with simple debounce filtering."""

    def __init__(self, pin, *, active_value=1, debounce_ms=DEBOUNCE_MS):
        self.pin = pin
        self.active_value = active_value
        self.debounce_ms = debounce_ms
        self._last_state = self.pin.value()
        self._stable_state = self._last_state
        self._last_change = time.ticks_ms()

    def raw_state(self):
        return self.pin.value()

    def is_active(self):
        now = time.ticks_ms()
        state = self.raw_state()
        if state != self._last_state:
            self._last_state = state
            self._last_change = now
        elif time.ticks_diff(now, self._last_change) >= self.debounce_ms:
            self._stable_state = self._last_state
        return self._stable_state == self.active_value


class TankLevelSensor:
    """Tracks a single RV tank using multiple float/probe sensors."""

    def __init__(
        self,
        name: str,
        pins,
        *,
        active_high=ACTIVE_HIGH,
        debounce_ms=DEBOUNCE_MS,
        labels=None,
    ):
        self.name = name
        pin_numbers = list(pins)
        if labels is None:
            labels = ["empty", "one_third", "two_thirds", "full"]
        self.labels = list(labels)
        if len(self.labels) != len(pin_numbers):
            raise ValueError("labels and pins must have the same length")
        active_value = 1 if active_high else 0
        pin_kwargs = {"mode": Pin.IN, "pull": Pin.PULL_DOWN if active_high else Pin.PULL_UP}
        self.inputs = [
            DebouncedInput(Pin(pin_number, **pin_kwargs), active_value=active_value, debounce_ms=debounce_ms)
            for pin_number in pin_numbers
        ]
        step_count = len(self.inputs)
        if step_count < 2:
            raise ValueError("Each tank needs at least two sensors")
        self.percent_lookup = [int((100 * idx) / (step_count - 1)) for idx in range(step_count)]
        self._last_report = None

    def read_levels(self):
        return {label: input_.is_active() for label, input_ in zip(self.labels, self.inputs)}

    def fill_percentage(self, levels=None):
        if levels is None:
            levels = self.read_levels()
        highest = -1
        for idx, label in enumerate(self.labels):
            if levels[label]:
                highest = idx
        if highest < 0:
            return 0
        return self.percent_lookup[highest]

    def snapshot(self):
        levels = self.read_levels()
        return {
            "tank": self.name,
            "levels": levels,
            "percentage": self.fill_percentage(levels),
        }

    def has_changed(self, levels):
        if self._last_report is None:
            return True
        for label, state in levels.items():
            if self._last_report.get(label) != state:
                return True
        return False

    def remember(self, levels):
        self._last_report = dict(levels)


# ---------------------------------------------------------------------------
# Top-level polling loop
# ---------------------------------------------------------------------------


def build_sensors():
    return [TankLevelSensor(name, pins) for name, pins in TANK_CONFIG.items()]


def log_snapshot(snapshot):
    levels = snapshot["levels"]
    parts = [f"{label}={'ON' if state else 'off'}" for label, state in levels.items()]
    parts.append(f"fill={snapshot['percentage']}%")
    print(f"[{snapshot['tank']}] " + ", ".join(parts))


def main(poll_interval_s=1.0):
    sensors = build_sensors()
    print("RV tank monitor started. Press Ctrl+C to stop.")
    while True:
        for sensor in sensors:
            levels = sensor.read_levels()
            if sensor.has_changed(levels):
                snapshot = {
                    "tank": sensor.name,
                    "levels": levels,
                    "percentage": sensor.fill_percentage(levels),
                }
                log_snapshot(snapshot)
                sensor.remember(levels)
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    main()
