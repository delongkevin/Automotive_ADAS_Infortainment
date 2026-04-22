import serial
import time
import os
import re

# Define COM Port and Baud Rate
COM_PORT = "COM7"  # Change this to match your setup
BAUD_RATE = 115200   # Adjust according to your device
OUTPUT_FILE = "A72_CPU_Load.txt"  # File to save response
RUN_TIME = 13  # Time in seconds to capture data per command
CLEAR_LOG = False  # Set to True if you want to clear the log on each run
NUM_ITERATIONS = 1

# List of commands to send
COMMANDS = [
    "top -z 40 -t 10",
]


# Regex pattern to match ANSI escape sequences
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

for i in range (NUM_ITERATIONS):
    print(f"Iteration {i+1}/{NUM_ITERATIONS}")
    
    try:
        # Open Serial Port
        with serial.Serial(COM_PORT, BAUD_RATE, timeout=1) as ser:
            print(f"Connected to {COM_PORT} at {BAUD_RATE} baud")

            # Give some time for initialization
            time.sleep(2)

            # Clear previous output file if enabled
            if CLEAR_LOG and os.path.exists(OUTPUT_FILE):
                open(OUTPUT_FILE, "w").close()
                print(f"Cleared log file: {OUTPUT_FILE}")

            # Open log file for writing
            with open(OUTPUT_FILE, "a") as file:
                for command in COMMANDS:
                    print(f"\nSending command: {command.strip()}")

                    # Clear the input buffer before sending a new command
                    ser.reset_input_buffer()
                    time.sleep(0.5)  # Short delay to ensure buffer is cleared

                    # Send command
                    ser.write((command + "\n").encode())

                    # Write header to log file
                    file.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Executing: {command.strip()}\n")
                    file.write("=" * 50 + "\n")

                    # Start time tracking
                    start_time = time.time()

                    while (time.time() - start_time) < RUN_TIME:
                        data = ser.readline().decode(errors="ignore").strip()
                        if data:
                            clean_data = ansi_escape.sub('', data)  # Remove ANSI escape codes
                            print(clean_data)  # Display on console
                            file.write(clean_data + "\n")  # Save to log file
                            file.flush()  # Ensure immediate writing

                    print(f"Completed reading response for: {command.strip()}\n")
                    ser.send_break(duration=0.5)

    except serial.SerialException as e:
        print(f"Error: {e}")

    finally:
        print(f"Data saved to {OUTPUT_FILE}")
