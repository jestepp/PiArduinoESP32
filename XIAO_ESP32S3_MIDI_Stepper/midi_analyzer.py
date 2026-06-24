import argparse
from collections import Counter
from pathlib import Path

import mido


def _message_allowed(msg, allowed_channels=None, min_note=0, max_note=127, include_percussion=False):
    if not hasattr(msg, "channel"):
        return False
    channel = msg.channel + 1
    if channel == 10 and not include_percussion:
        return False
    if allowed_channels is not None and channel not in allowed_channels:
        return False
    if hasattr(msg, "note") and not (min_note <= msg.note <= max_note):
        return False
    return True


def build_single_motor_plan(path, allowed_channels=None, min_note=0, max_note=127, include_percussion=False):
    midi_path = Path(path)
    midi_file = mido.MidiFile(midi_path)
    note_counts = Counter()

    for track in midi_file.tracks:
        for msg in track:
            if not _message_allowed(msg, allowed_channels, min_note, max_note, include_percussion):
                continue
            if msg.type == "note_on" and msg.velocity > 0:
                note_counts[msg.channel + 1] += 1

    if not note_counts:
        return {
            "mode": "none",
            "source_channel": None,
        }

    return {
        "mode": "channel",
        "source_channel": note_counts.most_common(1)[0][0],
    }


def build_three_motor_plan(path, motor_count=3, allowed_channels=None, min_note=0, max_note=127, include_percussion=False):
    midi_path = Path(path)
    midi_file = mido.MidiFile(midi_path)
    note_counts = Counter()
    notes_by_channel = {}

    for track in midi_file.tracks:
        for msg in track:
            if not _message_allowed(msg, allowed_channels, min_note, max_note, include_percussion):
                continue
            if msg.type == "note_on" and msg.velocity > 0:
                channel = msg.channel + 1
                note_counts[channel] += 1
                notes_by_channel.setdefault(channel, []).append(msg.note)

    selected_channels = [channel for channel, _ in note_counts.most_common(motor_count)]
    if len(selected_channels) >= 2:
        return {
            "mode": "channels",
            "channel_to_motor": {channel: index for index, channel in enumerate(selected_channels)},
            "selected_channels": selected_channels,
            "pitch_thresholds": [],
        }

    all_notes = []
    for notes in notes_by_channel.values():
        all_notes.extend(notes)

    if not all_notes:
        return {
            "mode": "none",
            "channel_to_motor": {},
            "selected_channels": [],
            "pitch_thresholds": [],
        }

    sorted_notes = sorted(all_notes)
    low_threshold = sorted_notes[len(sorted_notes) // 3]
    high_threshold = sorted_notes[(len(sorted_notes) * 2) // 3]
    return {
        "mode": "pitch_bands",
        "channel_to_motor": {},
        "selected_channels": selected_channels,
        "pitch_thresholds": [low_threshold, high_threshold],
    }


def analyze_midi_file(path):
    midi_path = Path(path)
    midi_file = mido.MidiFile(midi_path)
    note_counts = Counter()
    event_counts = Counter()

    for track in midi_file.tracks:
        for msg in track:
            if not hasattr(msg, "channel"):
                continue
            channel = msg.channel + 1
            if msg.type in ("note_on", "note_off"):
                event_counts[channel] += 1
            if msg.type == "note_on" and msg.velocity > 0:
                note_counts[channel] += 1

    recommended = None
    recommended_any = None
    if note_counts:
        recommended_any = note_counts.most_common(1)[0][0]
        melodic_counts = Counter({channel: count for channel, count in note_counts.items() if channel != 10})
        recommended = melodic_counts.most_common(1)[0][0] if melodic_counts else recommended_any

    single_motor_plan = build_single_motor_plan(midi_path)
    three_motor_plan = build_three_motor_plan(midi_path)

    return {
        "path": midi_path,
        "type": midi_file.type,
        "tracks": len(midi_file.tracks),
        "ticks_per_beat": midi_file.ticks_per_beat,
        "length": midi_file.length,
        "note_counts": dict(sorted(note_counts.items())),
        "event_counts": dict(sorted(event_counts.items())),
        "recommended_channel": recommended,
        "busiest_channel": recommended_any,
        "single_motor_plan": single_motor_plan,
        "three_motor_plan": three_motor_plan,
    }


def format_analysis(analysis):
    lines = [
        f"File: {analysis['path'].name}",
        f"Length: {analysis['length']:.2f} seconds",
        f"Tracks: {analysis['tracks']}",
        f"MIDI type: {analysis['type']}",
        f"Ticks per beat: {analysis['ticks_per_beat']}",
        "",
        "Note-on counts by MIDI channel:",
    ]

    if analysis["note_counts"]:
        for channel, count in analysis["note_counts"].items():
            lines.append(f"  Channel {channel}: {count}")
    else:
        lines.append("  No note-on events found.")

    if analysis["recommended_channel"] is not None:
        lines.extend(
            [
                "",
                f"Recommended source channel: {analysis['recommended_channel']}",
            ]
        )
        if analysis["busiest_channel"] == 10 and analysis["recommended_channel"] != 10:
            lines.append("Note: channel 10 has the most notes, but it is usually percussion.")

    single_plan = analysis["single_motor_plan"]
    lines.extend(["", "Recommended 1-motor simplifier:"])
    if single_plan["mode"] == "channel":
        lines.append(f"  MIDI channel {single_plan['source_channel']} -> motor 0")
    else:
        lines.append("  Not enough melodic note data found.")

    plan = analysis["three_motor_plan"]
    lines.extend(["", "Recommended 3-motor arrangement:"])
    if plan["mode"] == "channels":
        for channel, motor in plan["channel_to_motor"].items():
            lines.append(f"  MIDI channel {channel} -> motor {motor}")
    elif plan["mode"] == "pitch_bands":
        low_threshold, high_threshold = plan["pitch_thresholds"]
        lines.append(f"  Low notes <= {low_threshold} -> motor 0")
        lines.append(f"  Mid notes {low_threshold + 1}-{high_threshold} -> motor 1")
        lines.append(f"  High notes > {high_threshold} -> motor 2")
    else:
        lines.append("  Not enough melodic note data found.")

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show MIDI file channel usage.")
    parser.add_argument("midi_file", help="Path to a .mid file")
    args = parser.parse_args(argv)

    analysis = analyze_midi_file(args.midi_file)
    print(format_analysis(analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
