import subprocess
import os
import time

# Modify the path to match your TRACE32 installation
TRACE32_PATH = r"C:\T32\bin\windows64\t32marm.exe"

# Path to the CMM script (Ensure there's no trailing space in the string)
CMM_SCRIPT = r"_J721S2_r5_mcu2_0_CpuLoad.cmm"

# Number of iterations
NUM_ITERATIONS = 1

for i in range(NUM_ITERATIONS):
    print(f"Iteration {i+1}/{NUM_ITERATIONS}: Starting TRACE32...")

    # Start TRACE32 process
    trace32_process = subprocess.Popen([TRACE32_PATH, "-s", CMM_SCRIPT], shell=True)

    # Wait for 55 seconds; if process does not exit, terminate it
    try:
        trace32_process.wait(timeout=90)  # Waits for process to exit within 55 seconds
        print(f"Iteration {i+1}: TRACE32 exited successfully.")
    except subprocess.TimeoutExpired:
        print(f"Iteration {i+1}: Timeout reached! Killing TRACE32 process...")
        trace32_process.terminate()  # Soft stop
        time.sleep(2)  # Give some time to terminate gracefully
        trace32_process.kill()  # Force kill if still running
        os.system("taskkill /IM t32marm.exe /F")  # Ensures process is killed

    print(f"Iteration {i+1}: TRACE32 process closed. Waiting before next iteration...\n")
    time.sleep(10)  # Small delay to avoid potential conflicts before restarting

print("All iterations completed successfully.")
