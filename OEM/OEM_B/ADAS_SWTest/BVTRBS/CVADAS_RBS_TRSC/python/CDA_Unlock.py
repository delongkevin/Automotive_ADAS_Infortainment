import os
import sys
import subprocess
import pyautogui #pip install pyautogui
import keyboard #pip install keyboard
import time as t
from datetime import datetime
from pathlib import Path

global path, iterations, ser

#UPDATE YOUR USER NAME AND CREDENTIALS BELOW FOR THE CDA TOOL YOU HAVE ON YOUR PC!####
username = "T9232KD"
password = "Kevman#19901446"

###DO NOT MODIFY ANY CODE BELOW THIS POINT###################################

def save_DID_Response():
    pyautogui.click(886,476,2) #Response window select in PID
    t.sleep(0.5)
    pyautogui.click(button='right')
    t.sleep(1)
    pyautogui.click(947,584)#select all
    t.sleep(1)
    pyautogui.moveTo(886,476) #Response window select in PID
    t.sleep(0.5)
    pyautogui.click(button='right')
    t.sleep(1)
    pyautogui.click(947,522) #copy
    t.sleep(1)
    s = pyperclip.paste()
    t.sleep(1)
    with open(".\\DID_Response.txt","a") as DID:
        DID.write("Response: "+str(s)+"\n\n")
        print(str(s)+" - Data written to file!")
    DID.close()
    

def PartNumber_PID():
    send_DID("22 29 5f") #DCL and Certstore Header info
    send_DID("22 29 5E") #DCL Header UUID
    send_DID("22 29 5C") #HTA Header UUID
    send_DID("22 29 5B") #HTA Header Info
    send_DID("22 29 5A") #Hosted app/firmware cal/config data header
    send_DID("22 29 5B") #Hosted app/firmware header UUID
    send_DID("22 29 57") #Hosted app/Firmware Header info
    send_DID("22 20 30") #Authenicated Diagnostics - previous access
    send_DID("22 10 02") #Vehicle Speed
    send_DID("22 19 21") #Operational Mode Status
    send_DID("22 29 54") #Policy Type
    send_DID("22 20 1F") #Boot Failure Reason
    send_DID("22 55 00") #Trailer sense and drive function data
    send_DID("22 52 01") #Plant Mode Status
    send_DID("22 F1 09") #Rear USS health status
    send_DID("22 51 07") #Front USS Health status
    send_DID("22 51 04") # FD-CAN 14 Tx Signals
    send_DID("22 51 03") #FD-CAN2 RX Signals
    send_DID("22 51 02") #FD-CAN14 Rx Signals
    send_DID("22 20 13") #VIN LOck state
    send_DID("22 FD 01") #Previous camera calibration Data-4 cam
    send_DID("22 FD 02") #CHMSL Current camera calibration - 5th cam
    send_DID("22 29 45") #Flow Control Test
    send_DID("22 29 39") #FD-CAN2 Bus Network Wake up reason
    send_DID("22 29 2E") #Proxi write counter
    send_DID("22 20 32") #Secure Log
    send_DID("22 20 26") #CAN Overrun Counters
    send_DID("22 20 24") #Read ECU Proxi Data
    send_DID("22 20 1B") #Application Data Software programming attempt counter
    send_DID("22 20 1A") #Application Software Programming Attempt counter
    send_DID("22 20 10") #Programming status
    send_DID("22 20 0D") #Odometer last clear data Trouble Code (DTC)
    send_DID("22 20 0C") #Time since ign on of first dtc detection
    send_DID("22 20 0B") #time first dtc detection
    send_DID("22 20 0A") #ign on counter
    send_DID("22 20 08") #ECU life time (Not voltatile mode)
    send_DID("22 20 03") #Boot software programming attempt counter
    send_DID("22 20 02") #odometer at last flash programming
    send_DID("22 20 01") #Odometer
    send_DID("22 19 1D") #Time of power latch
    send_DID("22 10 2A") #Check EOL Configuration Data
    send_DID("22 10 0B") #Diagnostic Tool and session status
    send_DID("22 10 09") #ECU time since ign on
    send_DID("22 10 08") # ECU Life Time
    send_DID("22 10 04")  #Battery Voltage
    send_DID("22 01 07") #RoE Activation State
    send_DID("22 FD 00") #Plant Camera Calibration Data
    send_DID("22 10 0C") #ECU Security Status
    send_DID("22 01 08") #Authenticated diagnostics Active Role
    send_DID("22 29 51") #Certificate STore UUID
    send_DID("22 29 59") #Hosted app/firmware cal/config data header
    send_DID("22 51 05") #FD-CAN2 Tx Signals
    send_DID("22 20 31") #Authenicated Diagnostics - Disavowed cert list
    send_DID("22 01 03") # VIN Lock Status
    send_DID("22 F1 B5") #Application Data software finger print info
    send_DID("22 F1 B4") #Application Software Fingerprint reading
    send_DID("22 F1 B3") #Boot software fingerprint reading information
    send_DID("22 F1 B0") #VIN Current
    send_DID("22 F1 A6") #Message matrix
    send_DID("22 F1 A2") # Vector Delivery ID
    send_DID("22 F1 A1") # EOL Configuration Code
    send_DID("22 F1 A0") #System Identification Data
    send_DID("22 F1 95") #Supplier Manufacturer ECU Software version number
    send_DID("22 F1 94") #Supplier Manufactur part number
    send_DID("22 F1 93") #Supplier Manufacture ECU Hardware verion
    send_DID("22 F1 92") #Supplier Manufactture ECU hardware part number
    send_DID("22 F1 91") #FCA ESLM ECU Hardware Number
    send_DID("22 F1 90") #VIN Original number
    send_DID("22 F1 8C") #ECU Serial Number
    send_DID("22 F1 8B") #FCA ESLM ECU Softwware Application Number
    send_DID("22 F1 8A") #FCA ESLM ECU Software Calibration Number
    send_DID("22 F1 88") #FCA ESLM ECU Software Number
    send_DID("22 F1 87") #CODEP ECU Part Number
    send_DID("22 F1 86") #Active Diagnostic Session
    send_DID("22 F1 81") #Application Software identification
    send_DID("22 F1 82") #Application Data Identification
    send_DID("22 F1 80") #Boot software version information
    send_DID("22 F1 0B") #ECU Qualification
    send_DID("22 F1 55") #Software Supplier Identification
    send_DID("22 F1 54") #Hardware Supplier Identification
    send_DID("22 F1 34") #CODEP Assembly Part Number
    send_DID("22 F1 33") #EBOM Assembly Part Number
    send_DID("22 F1 32") #EBOM ECU Part Number
    send_DID("22 F1 12") #ECU Identification - Hardware Part number
    send_DID("22 F1 10") #ECU Dianostic Identification
    send_DID("22 F1 0D") #Diagnostic Specification Information
    send_DID("22 F1 11") # Public certificates - Regional Support
    send_DID("22 F1 0B") #ECU Qualification

def CheckPartNumbers_Quick():
    pyautogui.click(1519,230)
    t.sleep(0.1)
    pyautogui.click(661,366) #read/write data soft key press
    t.sleep(5)
    pyautogui.click(823,546) #FD-CAN2 TX signals
    t.sleep(5)
    for i in range (0,89):
        pyautogui.click(1489,564) #right box page slider
        t.sleep(1)
        pyautogui.press("pagedown")
        t.sleep(1)   
        Evidence = pyautogui.screenshot("./"+str(t.time())+".png")
        t.sleep(1)
        pyautogui.click(991,509) #left box page slider 
        t.sleep(0.2)
        pyautogui.press("down")
        t.sleep(0.2)
        pyautogui.press("enter")
        t.sleep(1)
        Evidence = pyautogui.screenshot("./"+str(t.time())+".png")
        t.sleep(0.2)


def saveLog():
    os.getcwd();

def getScreenSize():
    print(pyautogui.size())

def getPosition():
    print(pyautogui.position())

def moveTo(x,y,duration=1):
    pyautogui.moveTo(int(x), int(y), int(duration))

def checkPreconditions():
    pyautogui.moveTo(1059,368) #PID Editor button
    pyautogui.click(1059,368)
    t.sleep(2)
    pyautogui.click(706, 489) #Request space
    t.sleep(2)
    pyautogui.click(662,478,2)
    for i in range(0,20):
        pyautogui.press("delete")
    pyautogui.write("31 01 D0 02")
    t.sleep(2)
    pyautogui.click(668,854)
    t.sleep(2)
    

def interruptCDA():
    os.system("taskkill /IM CDA.exe")
    t.sleep(10)

def openCDA():
    os.popen("C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\CDA 6\\CDA 6.lnk")
    t.sleep(10) #open CDA tool
    print("CDA is launched!\n")
    loginCDA()
    deviceConnection()
    

def getCredentials():
    global username, password
    if username or password in globals():
        return username, password
    else: 
        username = pyautogui.prompt("Enter your CDA user name credentials: ")
        password = pyautogui.prompt("Enter your CDA password: ")
    return username, password

def loginCDA():
    getCredentials()    
    #pyautogui.click(848,512,2)
    for i in range (0,3):
        pyautogui.press('tab')
        t.sleep(0.5)
    for i in range (0,10):
        pyautogui.press('backspace');
        t.sleep(0.5)
    pyautogui.write(str(username))
    t.sleep(5)
    pyautogui.press("tab")
    t.sleep(2)
    pyautogui.write(str(password))
    t.sleep(5)
    pyautogui.press("enter")


def deviceConnection():
    t.sleep(10)
    pyautogui.click(1378,538) #Benchtop mode
    t.sleep(2)
    pyautogui.click(1411,871) #continue
    t.sleep(2)
    pyautogui.click(532,366) # enter cvadas
    t.sleep(2)
    pyautogui.write("cvadas")
    t.sleep(2)
    pyautogui.press("enter")
    t.sleep(2)
    pyautogui.click(957,638,2) #OK button for diag notice
    t.sleep(2)

def unlockECU():
    openCDA()
    print("Unlocking ECU..Please wait...")
    t.sleep(10)
    pyautogui.click(1197,374,2 ) #ecu unlock
    t.sleep(5)          
    pyautogui.click(661,635) #unlock button
    t.sleep(15)                         
    print("Unlock complete..")

datetime.now()        
try:
    unlockECU()
    interruptCDA()
    sys.exit(1)
        
except Exception as e:
    print(e)
