import serial
from ..config import logger, RELAY_PORT

class RelayControl:
    ON, OFF = 1, 0

    def __init__(self):
        self.serial = serial.Serial(
            port=RELAY_PORT, baudrate=9600, bytesize=8,
            parity=serial.PARITY_NONE, stopbits=1)

    def select_port_power(self, state, port):
        logger.debug(f"Powering port {port} {'On' if state else 'Off'}")
        if state not in (0, 1):
            raise ValueError('State must be 0 for off; or 1 for on.')
        self.serial.write(f'$A3 {port} {state}\r\n'.encode('utf-8'))

    def close(self):
        if hasattr(self, 'serial') and self.serial.is_open:
            self.serial.close()

    def __del__(self):
        self.close()
