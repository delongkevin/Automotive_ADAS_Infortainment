import serial
import sys
# from datetime import datetime
# import logging
import serial.tools.list_ports

def connectSerial(description = "Silicon Labs"):
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if description in port.description:
            with open('port.txt', 'w') as f:
                f.write(str(port.device[3:]))
            return
    with open('port.txt', 'w') as f:
        f.write(str(999))
        #logger.error("Power Supply Not Found")


#logging.basicConfig(filename="logs/Check_Port_" + datetime.now().strftime("%m%d") + ".log", level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(message)s')
#logger=logging.getLogger(__name__)

try:
    connectSerial()
except Exception as e:
    print(e)
    #logger.error(e)
    sys.exit(-2)