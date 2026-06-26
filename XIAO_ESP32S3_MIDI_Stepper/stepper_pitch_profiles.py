"""Pitch-to-step-rate profiles for stepper MIDI playback."""

import json
import re
from pathlib import Path

A4_KEY = 69
A4_FREQ = 440.0

STANDARD_PROFILE = "Standard equal temperament"
DAVID_SCHOLTEN_PROFILE = "David Scholten stepper table"
PITCH_PROFILES = (STANDARD_PROFILE, DAVID_SCHOLTEN_PROFILE)
CUSTOM_PROFILE_PREFIX = "Custom: "
CUSTOM_PROFILE_DIR = Path(__file__).resolve().parent / "pitch_profiles"

# Source: D:\Pi and Arduino\Stepper Synth\MidiSynth\pitches.h
# Original header: "Made By David Scholten, July 2020".
# Values are pulse intervals in microseconds indexed by MIDI note number.
DAVID_SCHOLTEN_PULSE_MICROS = (
    122324, 115473, 108992, 102828, 97087, 91617, 86505, 81633,
    77042, 72727, 68634, 64788, 61162, 57737, 54496, 51414,
    48544, 45809, 43253, 40816, 38521, 36364, 34317, 32394,
    30581, 28860, 27241, 25714, 24272, 22910, 21622, 20408,
    19264, 18182, 17161, 16197, 15288, 14430, 13620, 12857,
    12134, 11453, 10811, 10204, 9631, 9091, 8581, 8099,
    7645, 7216, 6811, 6428, 6068, 5727, 5405, 5102,
    4816, 4545, 4290, 4050, 3822, 3608, 3405, 3214,
    3034, 2863, 2703, 2551, 2408, 2273, 2145, 2025,
    1911, 1804, 1703, 1607, 1517, 1432, 1351, 1276,
    1204, 1136, 1073, 1012, 956, 902, 851, 804,
    758, 716, 676, 638, 602, 568, 536, 506,
    478, 451, 426, 402, 379, 358, 338, 319,
    301, 284, 268, 253, 239, 225, 213, 201,
    190, 179, 169, 159, 150, 142, 134, 127,
    119, 113, 106, 100, 95, 89, 84, 80,
)


def clamp_midi_note(note):
    return max(0, min(127, int(note)))


def standard_note_to_frequency(note):
    note = clamp_midi_note(note)
    return A4_FREQ * 2 ** ((note - A4_KEY) / 12)


def david_scholten_note_to_frequency(note):
    note = clamp_midi_note(note)
    pulse_micros = DAVID_SCHOLTEN_PULSE_MICROS[note]
    return 1_000_000.0 / pulse_micros


def built_in_profile_values(profile):
    if profile == DAVID_SCHOLTEN_PROFILE:
        return [david_scholten_note_to_frequency(note) for note in range(128)]
    return [standard_note_to_frequency(note) for note in range(128)]


def safe_profile_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "_", name.strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "Custom Profile"


def custom_profile_path(name):
    return CUSTOM_PROFILE_DIR / f"{safe_profile_name(name)}.json"


def load_custom_profiles():
    profiles = {}
    if not CUSTOM_PROFILE_DIR.exists():
        return profiles
    for path in sorted(CUSTOM_PROFILE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = safe_profile_name(str(data.get("name") or path.stem))
            values = [float(value) for value in data["frequencies"]]
            if len(values) != 128:
                continue
            profiles[name] = values
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return profiles


def save_custom_profile(name, frequencies):
    CUSTOM_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = safe_profile_name(name)
    values = [float(value) for value in frequencies]
    if len(values) != 128:
        raise ValueError("Custom pitch profiles must contain 128 frequency values.")
    data = {
        "name": safe_name,
        "format": "midi-note-step-frequency-v1",
        "frequencies": values,
    }
    custom_profile_path(safe_name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return safe_name


def profile_names(include_custom=True):
    names = list(PITCH_PROFILES)
    if include_custom:
        names.extend(f"{CUSTOM_PROFILE_PREFIX}{name}" for name in load_custom_profiles())
    return tuple(names)


def profile_values(profile):
    if profile in PITCH_PROFILES:
        return built_in_profile_values(profile)
    if profile.startswith(CUSTOM_PROFILE_PREFIX):
        custom_name = profile[len(CUSTOM_PROFILE_PREFIX):]
        custom_profiles = load_custom_profiles()
        if custom_name in custom_profiles:
            return custom_profiles[custom_name]
    return built_in_profile_values(STANDARD_PROFILE)


def note_to_step_frequency(note, profile=STANDARD_PROFILE):
    note = clamp_midi_note(note)
    return profile_values(profile)[note]
