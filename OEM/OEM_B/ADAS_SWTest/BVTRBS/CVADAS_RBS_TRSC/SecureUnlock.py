import subprocess
import time
import os

# Path to TRACE32 executable
TRACE32_PATH = r"C:\T32\bin\windows64\t32marm.exe"

# Start TRACE32 as a subprocess
trace32_process = subprocess.Popen([TRACE32_PATH, "-s", "J721S2_secure_unlock.cmm"])

# Wait for 60 seconds; if process does not exit, terminate it
try:
    trace32_process.wait(timeout=60)  # Waits for process to exit within 60 seconds
    print("TRACE32 exited successfully.")
except subprocess.TimeoutExpired:
    print("Timeout reached! Killing TRACE32 process...")
    trace32_process.terminate()  # Soft stop
    time.sleep(2)  # Give some time to terminate gracefully
    trace32_process.kill()  # Force kill if still running
    os.system("taskkill /IM t32marm.exe /F")  # Ensures process is killed

print("Script execution completed.")
