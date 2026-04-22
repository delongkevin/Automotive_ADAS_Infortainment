import os
import sys
import subprocess
import pyautogui #pip install pyautogui
import keyboard #pip install keyboard
import time as t
from datetime import datetime, date, time, timezone
from pathlib import Path

def getPosition():
    print(pyautogui.position())

def getEFDPath(path):
    print ("Get EFD Path..")
    os.chdir(path)
    print ("Path to EFD: "+str(path))

try:
    print("Press a key to select a menu:\np - Get X-Y mouse coordinates\nx to quit\n")
    while True:
        if keyboard.is_pressed("p"):
            getPosition()
        t.sleep(0.1)

        
except Exception as e:
    print(e)
