import subprocess

# Modify the path to match your TRACE32 installation
TRACE32_PATH = r"C:\T32\bin\windows64\t32marm.exe"

# Path to the CMM script (Ensure there's no trailing space in the string)
CMM_SCRIPT = r"..\CMM\J721S2_secure_getuid_new.cmm"

# Execute TRACE32 and run the script using the correct syntax
subprocess.run([TRACE32_PATH, "-s", CMM_SCRIPT], shell=True)

print("Get UID from ECU Script executed successfully.")


