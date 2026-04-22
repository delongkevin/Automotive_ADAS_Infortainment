import serial
import serial.tools.list_ports
import time
import sys
import subprocess
import ctypes
from ctypes import wintypes

# -----------------------------
# Configuration
# -----------------------------
# Use a broader match since the COM number can change and the description can vary slightly.
DEFAULT_DESCRIPTION = "CP210"  # e.g. matches "Silicon Labs CP210x USB to UART Bridge"

# Your timing requirement
MUTEX_WAIT_MS = 15000
CONNECT_DEADLINE_SECONDS = 15.0

# Known conflicting apps you are OK killing (add/remove as needed)
KILL_PROCESS_NAMES = [
    "CANoe.exe",
    "CANoe64.exe",
]

# After how many seconds of failed connects do we start killing?
KILL_AFTER_SECONDS = 3.0

# -----------------------------
# Single instance (Windows mutex)
# -----------------------------
MUTEX_NAME = r"Global\PowerSupply_Lauterbach_COM_LOCK"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
CreateMutexW = kernel32.CreateMutexW
CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
CreateMutexW.restype = wintypes.HANDLE
WaitForSingleObject = kernel32.WaitForSingleObject
WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
WaitForSingleObject.restype = wintypes.DWORD
ReleaseMutex = kernel32.ReleaseMutex
ReleaseMutex.argtypes = (wintypes.HANDLE,)
ReleaseMutex.restype = wintypes.BOOL
CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = (wintypes.HANDLE,)
CloseHandle.restype = wintypes.BOOL

WAIT_OBJECT_0 = 0x00000000

def acquire_mutex(timeout_ms: int):
    h = CreateMutexW(None, False, MUTEX_NAME)
    if not h:
        raise RuntimeError("Failed to create mutex")
    rc = WaitForSingleObject(h, timeout_ms)
    if rc == WAIT_OBJECT_0:
        return h
    CloseHandle(h)
    return None

def release_mutex(h):
    try:
        ReleaseMutex(h)
    finally:
        CloseHandle(h)

# -----------------------------
# Kill helpers
# -----------------------------
def kill_processes_by_name(names):
    """
    Best-effort kill by image name using taskkill.
    """
    for name in names:
        try:
            result = subprocess.run(
                ["taskkill", "/IM", name, "/T", "/F"],
                capture_output=True,
                text=True
            )
            out = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            if out:
                print(out)
            if err and "not found" not in err.lower():
                print(err)
        except Exception as e:
            print(f"Failed to taskkill {name}: {e}")

# -----------------------------
# Serial helpers
# -----------------------------
def _list_ports_and_candidates(description: str):
    ports = list(serial.tools.list_ports.comports())
    candidates = [p for p in ports if description in (p.description or "")]
    return ports, candidates

def _try_open_port(device: str) -> serial.Serial:
    ser = serial.Serial(
        port=device,
        baudrate=9600,
        timeout=0.5,
        write_timeout=0.5,
    )
    time.sleep(0.1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser

def _query_getd(ser: serial.Serial):
    ser.reset_input_buffer()
    ser.write(b"GETD\r")
    ser.flush()
    time.sleep(0.15)
    return ser.readline()

def connectSerial(description=DEFAULT_DESCRIPTION):
    """
    Connect with a wall-clock deadline. If connect repeatedly fails, try to kill known
    conflicting apps (e.g., CANoe) once, then keep retrying until deadline.
    """
    start = time.time()
    kill_attempted = False

    while True:
        elapsed = time.time() - start
        if elapsed > CONNECT_DEADLINE_SECONDS:
            print("Failed to connect before deadline.")
            return -1

        ports, candidates = _list_ports_and_candidates(description)

        if not candidates:
            # Debug help for changing enumerations
            print("No matching power supply USB-UART found. Ports seen:")
            for p in ports:
                print(f"  {p.device}: {p.description}")
            time.sleep(0.25)
            continue

        for p in candidates:
            device = p.device
            try:
                ser = _try_open_port(device)

                # sanity: ensure it responds
                resp = _query_getd(ser)
                if not resp:
                    ser.close()
                    raise RuntimeError("No response to GETD")

                print("Found power supply at " + device)
                return ser

            except Exception as e:
                print(f"Connect failed on {device}: {e}")

        # If we've been failing a little while, attempt kill of known offenders once
        elapsed = time.time() - start
        if (not kill_attempted) and elapsed >= KILL_AFTER_SECONDS and KILL_PROCESS_NAMES:
            print("Connect keeps failing; attempting to close conflicting applications...")
            kill_processes_by_name(KILL_PROCESS_NAMES)
            kill_attempted = True
            # Give Windows time to release COM handles
            time.sleep(1.0)
        else:
            time.sleep(0.25)

# -----------------------------
# Power supply commands
# -----------------------------
def readVoltage(ser):
    resp = _query_getd(ser)
    s = resp.decode(errors="ignore").strip()
    val = int(s[2:6]) / 100.0
    print(val)
    return val

def readCurrent(ser):
    resp = _query_getd(ser)
    s = resp.decode(errors="ignore").strip()
    val = int(s[6:10]) / 100.0
    print(val)
    return val

def on(ser):
    string = "SOUT0\r"
    ser.write(string.encode())#ON
    time.sleep(0.1) 
    print(ser.readline())
    # print(string)
    time.sleep(1)

def off(ser):
    string = "SOUT1\r"
    ser.write(string.encode())#OFF
    time.sleep(0.1) 
    print(ser.readline())
    time.sleep(1)


def setVolt(ser, volt):
    sendString = f"VOLT{volt}\r".encode()
    ser.write(sendString)
    ser.flush()
    time.sleep(0.1)
    print(ser.readline())
    time.sleep(0.2)

def powerCycle(ser):
    off(ser)
    time.sleep(7)
    on(ser)
    time.sleep(7)
    readVoltage(ser)
    readCurrent(ser)

# -----------------------------
# Main
# -----------------------------
mutex = None
ser = None

try:
    mutex = acquire_mutex(MUTEX_WAIT_MS)
    if mutex is None:
        print("Another instance is running; timeout waiting for mutex.")
        sys.exit(3)

    if len(sys.argv) < 2:
        print("No command provided.")
        sys.exit(4)

    ser = connectSerial()
    if ser == -1:
        sys.exit(2)

    command = sys.argv[1]
    print(sys.argv[1:])

    if "on" in command or command == "0":
        on(ser)
    elif "off" in command or command == "1":
        off(ser)
    elif "readVoltage" in command or command == "2":
        readVoltage(ser)
    elif "readCurrent" in command or command == "3":
        readCurrent(ser)
    elif "setVoltage" in command or command == "4":
        subcommand = input("Enter a voltage between 0 to 15 \n(ex. enter 120 for 12v or 024 for 2.4v): ")
        setVolt(ser, str(subcommand))
    elif "powerCycle" in command or command == "5":
        powerCycle(ser)
    else:
        print("command unknown")
        sys.exit(5)

except Exception as e:
    print(e)
    sys.exit(1)
finally:
    try:
        if ser:
            ser.close()
    except Exception:
        pass
    try:
        if mutex:
            release_mutex(mutex)
    except Exception:
        pass