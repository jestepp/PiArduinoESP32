import re
import sys
import time


A4_KEY = 69
A4_FREQ = 440


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

    baud_rate = 115200
    motor_channels = 0

    if len(argv) > 0:
        arduino_port = argv[0]
    else:
        print("Please specify the port that the Arduino is connected to.")
        print("For example:\npython midi_interface.py COM3")
        return 1

    pitch_bending = False
    if len(argv) > 1 and argv[1] == "pitch_bending":
        pitch_bending = True
        print("Pitch bending enabled.")

    try:
        ser = serial.Serial(arduino_port, baud_rate, timeout=1)
    except serial.SerialException as exc:
        print("Serial connection failed. Please check your port and try again.")
        print(f"Serial error: {exc}")
        return 1

    time.sleep(3)
    start_time = time.time()
    while motor_channels == 0 and time.time() - start_time < 5:
        try:
            channels_str = str(ser.readline().decode(errors="ignore"))
            channel_match = re.search(r"motors: (\d+)", channels_str)
            if channel_match is not None:
                motor_channels = int(channel_match.group(1))
                ser.write(b"ack\n")
                print(f"Script connected to Arduino with {motor_channels} motors.")
        except Exception:
            pass

    if motor_channels == 0:
        print("Failed to connect to Arduino. Please check your port and try again.")
        return 1

    midi_ports = mido.get_input_names()
    if not midi_ports:
        print("No MIDI input ports were found.")
        print("Start loopMIDI and create a virtual MIDI port, or connect a MIDI input device, then retry.")
        ser.close()
        return 1

    print("Available MIDI input ports:")
    for index, port_name in enumerate(midi_ports, start=1):
        print(f"  {index}. {port_name}")

    selected_port = None
    while selected_port is None:
        choice = input(f"Choose MIDI port [1-{len(midi_ports)}], or press Enter to cancel: ").strip()
        if choice == "":
            print("No MIDI port selected.")
            ser.close()
            return 1
        try:
            selected_index = int(choice)
        except ValueError:
            print("Please enter a number from the list.")
            continue
        if 1 <= selected_index <= len(midi_ports):
            selected_port = midi_ports[selected_index - 1]
        else:
            print("That MIDI port number is out of range.")

    try:
        inport = mido.open_input(name=selected_port)
    except Exception as exc:
        print(f"Failed to open MIDI input port '{selected_port}': {exc}")
        ser.close()
        return 1
    last_midi_activity_time = time.time()
    channel_outputting = [False] * motor_channels
    motors_enabled = True

    def note_to_frequency(note):
        return A4_FREQ * 2 ** ((note - A4_KEY) / 12)

    def send_buffer_to_arduino(msg_buffer):
        nonlocal channel_outputting, motors_enabled, last_midi_activity_time
        serial_data = b""
        for msg in msg_buffer:
            if msg["channel"] > motor_channels - 1:
                continue
            if channel_outputting[msg["channel"]] and msg["type"] == "note_on":
                serial_data += f'e,{msg["channel"]}\n'.encode()
                serial_data += f's,{msg["channel"]},{msg["freq"]}\n'.encode()
            else:
                if msg["type"] == "note_on":
                    if not motors_enabled:
                        motors_enabled = True
                    channel_outputting[msg["channel"]] = True
                    serial_data += f's,{msg["channel"]},{msg["freq"]}\n'.encode()
                elif msg["type"] == "note_off":
                    channel_outputting[msg["channel"]] = False
                    serial_data += f'e,{msg["channel"]}\n'.encode()
        try:
            last_midi_activity_time = time.time()
            ser.write(serial_data)
        except Exception:
            print("Serial Write Failure. Was the device unplugged?")
            return 1

    def disable_motors():
        nonlocal motors_enabled, channel_outputting
        if not motors_enabled:
            return
        if any(channel_outputting):
            return
        print("5 second input timeout. Temporarily disabling motors.")
        motors_enabled = False
        try:
            ser.write(b"d\n")
        except Exception:
            print("Serial Write Failure. Was the device unplugged?")
            return 1

    try:
        print("Listening for MIDI input...")
        while True:
            msg_buffer = []
            for msg in inport.iter_pending():
                motor_index = msg.channel
                if motor_index > motor_channels - 1:
                    continue
                if msg.type == "note_on":
                    frequency = note_to_frequency(msg.note)
                    msg_buffer.append({"type": "note_on", "freq": frequency, "channel": motor_index})
                elif msg.type == "note_off":
                    msg_buffer.append({"type": "note_off", "channel": motor_index})
            if msg_buffer:
                send_buffer_to_arduino(msg_buffer)
            if time.time() - last_midi_activity_time > 5:
                disable_motors()
            time.sleep(0.001)
    finally:
        inport.close()
        ser.close()
        print("Ports closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
