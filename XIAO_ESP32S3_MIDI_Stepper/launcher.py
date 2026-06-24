import argparse
import subprocess
import sys

def install_requirements():
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])


def main():
    parser = argparse.ArgumentParser(description='Launch MIDI -> Stepper bridge')
    parser.add_argument('comport', nargs='?', help='XIAO COM port (e.g. COM3)')
    parser.add_argument('--pitch', action='store_true', help='Enable pitch bending')
    parser.add_argument('--install', action='store_true', help='Install Python requirements before running')
    args = parser.parse_args()

    if args.install:
        print('Installing requirements...')
        try:
            install_requirements()
        except subprocess.CalledProcessError:
            print('Failed to install requirements. Exiting.')
            sys.exit(1)

    if not args.comport:
        args.comport = input('Enter XIAO COM port (e.g. COM3): ').strip()
        if not args.comport:
            print('No COM port provided, exiting.')
            sys.exit(1)

    # Import here so packaging picks up the module
    try:
        import midi_interface
    except Exception as e:
        print('Failed to import midi_interface:', e)
        print('Make sure this script is run from the project folder or that the package is built correctly.')
        sys.exit(1)

    argv = [args.comport]
    if args.pitch:
        argv.append('pitch_bending')

    # Call the main function from midi_interface
    ret = midi_interface.main(argv)
    sys.exit(ret)

if __name__ == '__main__':
    main()
