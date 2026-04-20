import os
import shutil
import platform
import time

DEVICE_ID = "USB\VID_0897&PID_0005"  # Replace with actual Device Instance ID

def restart_trace32_driver():
    print("Disabling TRACE32 USB device via PowerShell...")
    os.system(f'powershell Disable-PnpDevice -InstanceId "{DEVICE_ID}" -Confirm:$false')
    time.sleep(3)

    print("Enabling TRACE32 USB device via PowerShell...")
    os.system(f'powershell Enable-PnpDevice -InstanceId "{DEVICE_ID}" -Confirm:$false')

    print("Driver restart completed.")


def clear_trace32_cache():
    # Get OS type
    os_type = platform.system()

    # Define possible TRACE32 cache locations
    if os_type == "Windows":
        temp_dir = os.getenv("temp")  # Windows temp folder
        trace32_temp = os.path.join(temp_dir, "trace32")
        trace32_config = os.path.expanduser(r"~\AppData\Local\T32")
        trace32_install = r"C:\T32"  # Change if your TRACE32 is installed elsewhere

        paths_to_delete = [trace32_temp, trace32_config]

    elif os_type == "Linux":
        trace32_temp = "/tmp/trace32"
        trace32_home_config = os.path.expanduser("~/.trace32")

        paths_to_delete = [trace32_temp, trace32_home_config]

    else:
        print(f"Unsupported OS: {os_type}")
        return

    # Delete cache folders
    for path in paths_to_delete:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)  # Delete folder and contents
                print(f"Deleted: {path}")
            except Exception as e:
                print(f"Failed to delete {path}: {e}")
        else:
            print(f"Path not found: {path}")

    print("TRACE32 cache cleared successfully.")

if __name__ == "__main__":
    clear_trace32_cache()
    restart_trace32_driver()
