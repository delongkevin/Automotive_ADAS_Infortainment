import sys
import serial
import serial.tools.list_ports
import time
import traceback

def connectSerial(description = "Silicon Labs CP210x USB to UART Bridge"):
    ports = serial.tools.list_ports.comports()
    for port in ports:
        try:
            if description in port.description:
                global ser
                ser = serial.Serial(port.device, '9600', timeout=0)
                break
            else:
                continue
        except Exception as e:
            print(e)
    if 'ser' in globals():
        return ser
    print("no target power supply found")
    return -1

def readVoltage(ser):
    string = "GETD\r"
    ser.write(string.encode())
    time.sleep(0.1) 
    s = str(ser.readline().strip())[2:6]
    val = int(s) / 100.0
    print(val)
    return val

def readCurrent(ser):
    string = "GETD\r"
    ser.write(string.encode())
    time.sleep(0.1) 
    s = str(ser.readline().strip())[6:10]
    val = int(s) / 100.0
    print(val)
    return val

def on(ser):
    string = "SOUT0\r"
    ser.write(string.encode())#ON
    time.sleep(0.1) 
    ser.readline()
    # print(string)
    time.sleep(1)

def off(ser):
    string = "SOUT1\r"
    ser.write(string.encode())#OFF
    time.sleep(0.1) 
    ser.readline()
    # print(string)
    time.sleep(1)

def setVolt(ser,volt):
    sendString = "VOLT"+str(volt)+"\r"
    ser.write(sendString.encode())
    time.sleep(0.1) 
    ser.readline()
    # print(sendString)
    time.sleep(0.5)

def powercycle(ser):
    off(ser)
    time.sleep(5)
    on(ser)
    readVoltage(ser)

def main(argv):
    calledFunction = argv[0]
    val = 0
    #initalize serial port
    ser = connectSerial()
    try:
        # Call function base on input
        if calledFunction == "readVoltage":
            val = readVoltage(ser)
        if calledFunction == "readCurrent":
            val = readCurrent(ser)
        if calledFunction == "setVoltage":
            val = setVolt(ser, argv[1]);
        # Write response in "PSC.txt"    
        with open('PSC.txt', 'a') as f:
            f.write(str(val))
    except Exception as err:
        # logger.error(err)
        traceback.print_exc()
        sys.exit(-1)

if __name__ == "__main__":
   main(sys.argv[1:])


    


