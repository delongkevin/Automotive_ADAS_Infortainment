import argparse
import os
import threading
import time
from pathlib import Path

import serial
import serial.tools.list_ports

script_dir = Path(__file__).resolve().parent
log_dir = script_dir


def reconstruct_from_STX_ETX(contents: str) -> str:
    """
    Reconstruct log messages that were interleaved by preemption.
    Uses a stack to handle nested STX/ETX pairs - when a new STX is found
    while already inside a message, the current (interrupted) message is
    pushed to the stack and resumed after the inner message completes.

    If no STX/ETX framing is found, returns the original content unchanged.
    """
    STX = '\x02'
    ETX = '\x03'

    class msg:
        def __init__(self):
            self.message = ""
            self.parent = None

    messages = []
    current_msg = None

    contents = contents.lstrip(ETX)

    for char in contents:
        if char == ETX:
            if current_msg:
                messages.append(current_msg.message)
                current_msg = current_msg.parent
            else:
                print("Warning: ETX found without matching STX. Ignoring.")
        elif char == STX:
            new_msg = msg()
            if current_msg:
                new_msg.parent = current_msg
            current_msg = new_msg
        else:
            if current_msg:
                current_msg.message += char
    return '\n'.join(messages)


def is_port_available(port_name, baudrate=115200):
    try:
        ser = serial.Serial(port=port_name, baudrate=baudrate, timeout=1)
        ser.close()
        return True
    except (serial.SerialException, OSError):
        return False


def auto_select_usb_serial_port(baudrate=115200):
    ports = list(serial.tools.list_ports.comports())
    assert ports, "No serial ports found. Please connect a device and try again."

    for _port in ports:
        if "usb serial port" in _port.description.lower() and is_port_available(_port.device, baudrate=baudrate):
            print(f"Auto-selected port: {_port.device} ({_port.description})")
            return _port.device

    raise RuntimeError("No available USB Serial Port found.")


def user_select_port():
    ports = list(serial.tools.list_ports.comports())
    assert ports, "No serial ports found. Please connect a device and try again."

    print(f"Select a serial port from the list below:")
    for i, _port in enumerate(ports):
        print(f"\t{i}: {_port.device} - {_port.description} - Available: {is_port_available(_port.name, baudrate=args.baudrate)}")
        _port.usb_info()
    port_index = input("Selection: ")
    assert 0 <= int(port_index) < len(ports), "Invalid selection. Please select a valid port index."
    return ports[int(port_index)].device


def main(serial_port, baudrate=115200):
    try:
        ser = serial.Serial(
            port=serial_port,
            baudrate=baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )

        if ser.isOpen():
            print(f"Serial port {ser.port} opened successfully.")
        else:
            print(f"Failed to open serial port {ser.port}.")
            return

        log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir / "teraterm.txt"
        log_file_temp_path = log_dir / "teraterm.tmp"
        log_file_path.unlink(missing_ok=True)
        log_file_temp_path.unlink(missing_ok=True)

        duration = 20  # seconds
        fsync_interval = 2.0

        # Shared state between threads
        raw_content = ""
        content_lock = threading.Lock()
        stop_reading = threading.Event()

        def read_serial_thread():
            """Background thread that continuously reads from serial port."""
            nonlocal raw_content
            while not stop_reading.is_set():
                response = ser.read(ser.in_waiting)
                if response:
                    log_entry = response.decode(errors='ignore')
                    print(log_entry, end='')
                    with content_lock:
                        raw_content += log_entry
                time.sleep(0.05)  # Small sleep to prevent busy-waiting

        print("Started logging UART data...")
        start = time.time()
        last_fsync = start

        # Start the serial reading thread
        reader_thread = threading.Thread(target=read_serial_thread, daemon=True)
        reader_thread.start()

        # Main thread: periodically reconstruct and save
        while (now := time.time()) - start < duration:
            if now - last_fsync >= fsync_interval:
                with content_lock:
                    if raw_content:
                        reconstructed_content = reconstruct_from_STX_ETX(raw_content)
                        # Write to temp file, then atomically rename
                        with log_file_temp_path.open('w', encoding='utf-8', errors='ignore') as temp_file:
                            temp_file.write(reconstructed_content)
                            temp_file.flush()
                            os.fsync(temp_file.fileno())
                        log_file_temp_path.replace(log_file_path) # Atomic rename
                last_fsync = now

            time.sleep(0.05)

        # Signal the reader thread to stop
        stop_reading.set()
        reader_thread.join(timeout=2.0)

        # Write any remaining data
        with content_lock:
            if raw_content:
                reconstructed_content = reconstruct_from_STX_ETX(raw_content)
                with log_file_temp_path.open('w', encoding='utf-8', errors='ignore') as temp_file:
                    temp_file.write(reconstructed_content)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                log_file_temp_path.replace(log_file_path) # Atomic rename

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if 'ser' in locals() and ser.isOpen():
            ser.close()
            print(f"Serial port {ser.port} closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serial Port Logger")
    # parser.add_argument('--port', type=str, default=None, help='Serial port for UART communication')
    parser.add_argument('--baudrate', type=int, default=115200, help='Baud rate for serial communication')
    args = parser.parse_args()

    # port = args.port if args.port else user_select_port()
    port = auto_select_usb_serial_port(baudrate=args.baudrate)
    main(serial_port=port, baudrate=args.baudrate)
