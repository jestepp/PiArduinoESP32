import argparse
import re
import sys
import time
from pathlib import Path

from midi_analyzer import build_single_motor_plan, build_three_motor_plan


A4_KEY = 69
A4_FREQ = 440
BAUD_RATE = 115200


def note_to_frequency(note):
    note = max(0, min(127, note))
    return A4_FREQ * 2 ** ((note - A4_KEY) / 12)


def connect_serial(serial_module, arduino_port):
    try:
        ser = serial_module.Serial(arduino_port, BAUD_RATE, timeout=1)
    except serial_module.SerialException as exc:
        print("Serial connection failed. Please check your port and try again.")
        print(f"Serial error: {exc}")
        return None, 0

    motor_channels = 0
    time.sleep(3)
    start_time = time.time()
    while motor_channels == 0 and time.time() - start_time < 5:
        try:
            line = ser.readline().decode(errors="ignore")
            channel_match = re.search(r"motors: (\d+)", line)
            if channel_match is not None:
                motor_channels = int(channel_match.group(1))
                ser.write(b"ack\n")
                print(f"Script connected to Arduino with {motor_channels} motors.")
        except Exception:
            pass

    if motor_channels == 0:
        print("Failed to connect to Arduino. Please check your port and try again.")
        ser.close()
        return None, 0

    return ser, motor_channels


def main(argv=None):
    try:
        import mido
        import serial
    except ImportError:
        print("Please install the required libraries using pip:")
        print("python -m pip install -r requirements.txt")
        return 1

    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Play a MIDI file through the XIAO stepper firmware.")
    parser.add_argument("comport", help="XIAO COM port, for example COM3")
    parser.add_argument("midi_file", help="Path to a .mid file")
    parser.add_argument("--motor", type=int, help="Force all playable notes onto one motor index, for example 0")
    parser.add_argument("--source-channel", type=int, help="Only play one MIDI channel, using 1-16 numbering")
    parser.add_argument("--transpose", type=int, default=0, help="Transpose playback by this many semitones")
    parser.add_argument(
        "--loudness-motors",
        type=int,
        default=1,
        help="Duplicate each played note across this many motors for more volume",
    )
    parser.add_argument(
        "--auto-three-motor",
        action="store_true",
        help="Auto-arrange melodic MIDI content across motors 0-2",
    )
    parser.add_argument(
        "--auto-single-motor",
        action="store_true",
        help="Auto-simplify melodic MIDI content to motor 0",
    )
    args = parser.parse_args(argv)

    arduino_port = args.comport
    midi_path = Path(args.midi_file).expanduser()
    if not midi_path.is_file():
        print(f"MIDI file not found: {midi_path}")
        return 1

    try:
        midi_file = mido.MidiFile(midi_path)
    except Exception as exc:
        print(f"Failed to load MIDI file: {exc}")
        return 1

    ser, motor_channels = connect_serial(serial, arduino_port)
    if ser is None:
        return 1

    if args.motor is not None and (args.motor < 0 or args.motor >= motor_channels):
        print(f"Motor index {args.motor} is out of range. This firmware reports motors 0-{motor_channels - 1}.")
        ser.close()
        return 1

    if args.source_channel is not None and (args.source_channel < 1 or args.source_channel > 16):
        print("Source MIDI channel must be 1-16.")
        ser.close()
        return 1

    if args.loudness_motors < 1 or args.loudness_motors > motor_channels:
        print(f"Loudness motor count must be 1-{motor_channels}.")
        ser.close()
        return 1

    source_channel_index = None
    if args.source_channel is not None and not args.auto_three_motor and not args.auto_single_motor:
        source_channel_index = args.source_channel - 1

    if args.auto_single_motor:
        target_motors = [0]
        single_motor_plan = build_single_motor_plan(midi_path)
        three_motor_plan = None
    elif args.auto_three_motor:
        target_motors = None
        single_motor_plan = None
        three_motor_plan = build_three_motor_plan(midi_path, min(3, motor_channels))
    elif args.motor is not None:
        target_motors = [args.motor]
        single_motor_plan = None
        three_motor_plan = None
    elif args.loudness_motors > 1:
        target_motors = list(range(args.loudness_motors))
        single_motor_plan = None
        three_motor_plan = None
    else:
        target_motors = None
        single_motor_plan = None
        three_motor_plan = None

    active_notes = [None] * motor_channels
    motors_enabled = False

    def disable_if_idle():
        nonlocal motors_enabled
        if motors_enabled and all(note is None for note in active_notes):
            ser.write(b"d\n")
            motors_enabled = False

    try:
        print(f"Playing: {midi_path.name}")
        if args.motor is not None:
            print(f"Single-stepper mode: sending MIDI to motor {args.motor}.")
        if args.source_channel is not None:
            print(f"Channel filter: only playing MIDI channel {args.source_channel}.")
        if args.transpose:
            print(f"Pitch transpose: {args.transpose:+d} semitones.")
        if target_motors is not None and len(target_motors) > 1:
            motor_list = ", ".join(str(motor) for motor in target_motors)
            print(f"Loudness mode: duplicating notes on motors {motor_list}.")
        if single_motor_plan is not None:
            if single_motor_plan["mode"] == "channel":
                print(
                    "Auto 1-motor simplifier: "
                    f"channel {single_motor_plan['source_channel']}->motor 0."
                )
            else:
                print("Auto 1-motor simplifier found no playable melodic note data.")
        if three_motor_plan is not None:
            if three_motor_plan["mode"] == "channels":
                mapping = ", ".join(
                    f"channel {channel}->motor {motor}"
                    for channel, motor in three_motor_plan["channel_to_motor"].items()
                )
                print(f"Auto 3-motor arrangement: {mapping}.")
            elif three_motor_plan["mode"] == "pitch_bands":
                low_threshold, high_threshold = three_motor_plan["pitch_thresholds"]
                print(
                    "Auto 3-motor arrangement: "
                    f"low <= {low_threshold}, mid <= {high_threshold}, high above."
                )
            else:
                print("Auto 3-motor arrangement found no playable melodic note data.")
        print("Press Ctrl+C to stop playback.")
        for msg in midi_file.play():
            if not hasattr(msg, "channel"):
                continue
            if source_channel_index is not None and msg.channel != source_channel_index:
                continue

            if single_motor_plan is not None:
                if single_motor_plan["mode"] != "channel":
                    continue
                if msg.channel + 1 != single_motor_plan["source_channel"]:
                    continue
                motors_for_message = [0]
            elif three_motor_plan is not None:
                channel = msg.channel + 1
                if channel == 10:
                    continue
                if three_motor_plan["mode"] == "channels":
                    if channel not in three_motor_plan["channel_to_motor"]:
                        continue
                    motors_for_message = [three_motor_plan["channel_to_motor"][channel]]
                elif three_motor_plan["mode"] == "pitch_bands":
                    low_threshold, high_threshold = three_motor_plan["pitch_thresholds"]
                    if msg.note <= low_threshold:
                        motors_for_message = [0]
                    elif msg.note <= high_threshold:
                        motors_for_message = [1]
                    else:
                        motors_for_message = [2]
                    motors_for_message = [motor for motor in motors_for_message if motor < motor_channels]
                    if not motors_for_message:
                        continue
                else:
                    continue
            elif target_motors is not None:
                motors_for_message = target_motors
            elif msg.channel < motor_channels:
                motors_for_message = [msg.channel]
            else:
                continue

            if msg.type == "note_on" and msg.velocity > 0:
                frequency = note_to_frequency(msg.note + args.transpose)
                for motor_index in motors_for_message:
                    if active_notes[motor_index] is not None:
                        ser.write(f"e,{motor_index}\n".encode())
                    ser.write(f"s,{motor_index},{frequency}\n".encode())
                    active_notes[motor_index] = (msg.channel, msg.note)
                motors_enabled = True
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                for motor_index in motors_for_message:
                    if active_notes[motor_index] == (msg.channel, msg.note):
                        ser.write(f"e,{motor_index}\n".encode())
                        active_notes[motor_index] = None
                disable_if_idle()
        print("Playback finished.")
    except KeyboardInterrupt:
        print("\nPlayback stopped.")
    except Exception as exc:
        print(f"Playback failed: {exc}")
        return 1
    finally:
        try:
            ser.write(b"d\n")
        except Exception:
            pass
        ser.close()
        print("Serial port closed.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
