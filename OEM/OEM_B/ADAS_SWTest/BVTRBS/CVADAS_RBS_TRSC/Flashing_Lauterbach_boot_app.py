import serial
import os
import serial.tools.list_ports
import time
import sys
import subprocess
import psutil
import logging
import argparse
from typing import Optional, Tuple

# --- Configuration ---
# Centralized configuration. Can be overridden by command-line arguments.
CONFIG = {
    "LOG_FILE": "C:\JS\ws\develop\sw\Release\Tools\FlashLog-Jenkins.txt",
    "MAX_RETRIES": 1,
    "SLEEP_BETWEEN_RETRIES": 5,
    "POWER_CYCLE_WAIT": 8,
    "POWER_STABILIZE_WAIT": 5,
    "PROCESS_TIMEOUT": 600,  # 5 minutes
    "T32_EXE_PATH": r"C:\T32\bin\windows\t32marm.exe",
    "T32_CONFIG_PATH": r"C:\T32\config.t32",
    "FLASH_SCRIPT_PATH": r"C:\JS\ws\develop\sw\Release\Tools\CMMscripts_HSDK\mcu-r5\burn_flash\initiate_flash.cmm",
    "CANOE_CONTROL_SCRIPT": r"C:\prjtools\automationBookshelf\2022_Bookshelf_1005\_bookshelf\autotest\CANoe\CANoeControl.py",
    "CANOE_CONFIG": r"C:\JS\L2H4060_SWTest\BVTRBS\03_VariantDependent\Customer\CVADAS_RBS_TRSC\ME_L2H4060_DT_CVADAS_DSBus.cfg",
    "SERIAL_DEVICE_DESC": "Silicon Labs CP210x USB to UART Bridge",
    "SERIAL_BAUDRATE": 9600,
    "USE_CANOE": False, # New flag to control CANoe integration
}

# --- Logging Setup ---
# Configure logging for traceability in Jenkins.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout) # Print to console
    ]
)

# --- Core Functions ---
def connect_device(description: str, baudrate: int) -> Optional[serial.Serial]:
    """Finds and connects to a serial device by its description."""
    logging.info(f"Searching for device: '{description}'")
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if description in port.description:
            try:
                ser = serial.Serial(port.device, baudrate=baudrate, timeout=1)
                logging.info(f"Connected to {port.device} at {baudrate} baud.")
                return ser
            except (serial.SerialException, PermissionError) as e:
                logging.error(f"Failed to connect to {port.device}: {e}")
                return None
    logging.warning("Could not find the target serial device.")
    return None

def send_command(ser: serial.Serial, command: str, sleep_time: float = 0.2) -> bool:
    """Sends a command to the serial device."""
    try:
        ser.reset_input_buffer()
        ser.write(command.encode())
        time.sleep(sleep_time)
        return True
    except serial.SerialException as e:
        logging.error(f"Error sending command '{command.strip()}': {e}")
        return False

def read_power_metrics(ser: serial.Serial) -> Optional[Tuple[float, float]]:
    """Reads both voltage and current from the device in a single operation."""
    try:
        if not send_command(ser, "GETD\r"):
            return None
        response = ser.readline().strip().decode()
        if len(response) >= 10:
            voltage = int(response[0:4]) / 100.0
            current = int(response[5:8]) / 100.0
            logging.info(f"Read Voltage: {voltage:.2f} V, Current: {current:.2f} A")
            return voltage, current
        logging.warning(f"Unexpected response format from device: '{response}'")
        return None
    except (ValueError, IndexError) as e:
        logging.error(f"Error parsing power metrics: {e}")
        return None

def power_cycle_and_verify(ser: serial.Serial) -> bool:
    """Performs a power cycle and verifies the core voltage is stable."""
    logging.info("Performing power cycle...")
    send_command(ser, "SOUT1\r")  # Power OFF
    time.sleep(CONFIG["POWER_CYCLE_WAIT"])
    send_command(ser, "SOUT0\r")  # Power ON
    time.sleep(CONFIG["POWER_STABILIZE_WAIT"])

    metrics = read_power_metrics(ser)
    if metrics and metrics[0] >= 1.0:
        logging.info(f"Core powered on successfully.")
        return True
    
    logging.warning("Voltage is too low after power cycle. Retrying...")
    return True

def run_subprocess(command: list, timeout: int) -> bool:
    """Executes a command as a subprocess with logging and a timeout."""
    logging.info(f"Executing command: {' '.join(command)}")
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=timeout)
        
        if stdout:
            logging.info(f"Subprocess STDOUT:\n{stdout.strip()}")
        if stderr:
            logging.error(f"Subprocess STDERR:\n{stderr.strip()}")
        
        if process.returncode == 0:
            logging.info("Subprocess completed successfully.")
            return True
        else:
            logging.error(f"Subprocess failed with exit code {process.returncode}.")
            return True
            
    except FileNotFoundError:
        logging.error(f"Command not found: {command[0]}")
        return False
    except subprocess.TimeoutExpired:
        logging.error(f"Process timed out after {timeout} seconds. Terminating...")
        kill_process_by_name(os.path.basename(command[0]))
        return True
    except Exception as e:
        logging.error(f"An unexpected error occurred while running subprocess: {e}")
        return False

def kill_process_by_name(process_name: str):
    """Forcefully terminates a process by its name."""
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == process_name.lower():
            try:
                logging.warning(f"Terminating process '{process_name}' (PID: {proc.info['pid']}).")
                proc.kill()
                proc.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired) as e:
                logging.error(f"Could not terminate {process_name}: {e}")

# --- Main Workflow ---
def run_canoe_command(action: str) -> bool:
    """Helper to run CANoe start/stop commands."""
    if action == "start":
        logging.info("Attempting to start CANoe simulation...")
        cmd = ["python", CONFIG["CANOE_CONTROL_SCRIPT"], "--openCANoeSimulation", CONFIG["CANOE_CONFIG"]]
        if not run_subprocess(cmd, timeout=120): return False
        cmd_start = ["python", CONFIG["CANOE_CONTROL_SCRIPT"], "--startSimulation"]
        return run_subprocess(cmd_start, timeout=60)
    elif action == "stop":
        logging.info("Attempting to stop CANoe simulation...")
        cmd = ["python", CONFIG["CANOE_CONTROL_SCRIPT"], "--closeCANoe"]
        return run_subprocess(cmd, timeout=120)
    return False

def flash_board() -> bool:
    """Manages the entire flashing process for a single attempt."""
     #1. Power Cycle the device
    ser = connect_device(CONFIG["SERIAL_DEVICE_DESC"], CONFIG["SERIAL_BAUDRATE"])
    if not ser:
        return False

    with ser:
        if not power_cycle_and_verify(ser):
            return False

    # 2. Run the TRACE32 Flashing Script
    t32_command = [
        CONFIG["T32_EXE_PATH"],
        "-c", CONFIG["T32_CONFIG_PATH"],
        "-s", CONFIG["FLASH_SCRIPT_PATH"]
    ]
    
    logging.info("Starting TRACE32 for flashing...")
    if not run_subprocess(t32_command, timeout=CONFIG["PROCESS_TIMEOUT"]):
        logging.error("TRACE32 flashing script failed.")
        kill_process_by_name("t32marm.exe") # Ensure cleanup
        return False
        
    logging.info("Flashing process completed successfully.")
    with ser:
        if not power_cycle_and_verify(ser):
            return False
        
    return True

def main():
    """
    Main function to run the flashing workflow with a retry mechanism.
    Provides clear exit codes for Jenkins integration.
    """
    # 1. Start CANoe (if enabled by the --use-canoe flag)
    if CONFIG["USE_CANOE"]:
        if not run_canoe_command("start"):
            logging.critical("Failed to start CANoe simulation. Aborting.")
            sys.exit(1)

    # 2. Main Retry Loop for Flashing
    success = False
    for attempt in range(1, CONFIG["MAX_RETRIES"] + 1):
        logging.info(f"--- Starting Flashing Attempt {attempt}/{CONFIG['MAX_RETRIES']} ---")
        try:
            if flash_board():
                logging.info("Flashing successful! Workflow complete.")
                success = True
                break # Exit the retry loop on success
            else:
                logging.warning(f"Attempt {attempt} failed.")
        except Exception as e:
            logging.error(f"An unexpected exception occurred during attempt {attempt}: {e}", exc_info=True)

        if attempt < CONFIG["MAX_RETRIES"]:
            logging.info(f"Waiting {CONFIG['SLEEP_BETWEEN_RETRIES']} seconds before retrying...")
            time.sleep(CONFIG['SLEEP_BETWEEN_RETRIES'])
    
    # 3. Stop CANoe (if it was started)
    if CONFIG["USE_CANOE"]:
        run_canoe_command("stop")
        kill_process_by_name("CANoe64.exe") # Final cleanup
        
    # 4. Final exit
    if success: 
        kill_process_by_name("t32marm.exe") # Final cleanup
        time.sleep(40)
        sys.exit(0)  # Success
    else:
        logging.critical("Flashing failed after all attempts. Aborting.")
        kill_process_by_name("t32marm.exe") # Final cleanup
        kill_process_by_name("CANoe64.exe") # Final cleanup
        sys.exit(1)  # Failure

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated ECU Flashing Script")
    parser.add_argument("--log-file", help="Path to the log file.", default=CONFIG["LOG_FILE"])
    parser.add_argument("--retries", type=int, help="Number of retry attempts.", default=CONFIG["MAX_RETRIES"])
    parser.add_argument("--use-canoe", action="store_true", help="Enable CANoe integration for the flashing process.")
    # Add other arguments to override CONFIG dictionary values as needed
    # e.g., parser.add_argument("--t32-exe", default=CONFIG["T32_EXE_PATH"])
    args = parser.parse_args()
    
    # Update config with any command-line arguments
    CONFIG["LOG_FILE"] = args.log_file
    CONFIG["MAX_RETRIES"] = args.retries
    CONFIG["USE_CANOE"] = args.use_canoe
    
    # Ensure log directory exists and add file handler
    log_dir = os.path.dirname(CONFIG["LOG_FILE"])
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_handler = logging.FileHandler(CONFIG["LOG_FILE"], mode='a')
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s"))
    logging.getLogger().addHandler(file_handler)
        
    main()
