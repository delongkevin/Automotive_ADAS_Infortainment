# -*- coding: utf-8 -*-
#  Copyright (c) 2020. MAGNA Electronics - S T R I C T L Y  C O N F I D E N T I A L
#  This document in its entirety is STRICTLY CONFIDENTIAL and may not be
#  disclosed, disseminated or distributed to parties outside MAGNA
#  Electronics without written permission from MAGNA Electronics.
#
"""Code for controlling the Relays Conrad
"""

from time import sleep

# import serial module
import serial.tools.list_ports

# Set path to the Conrad library
from libs import PyCP210xAccess, PyCP210x

class ControlRelaisConrad4(object):  # pylint: disable=unused-variable
    """ This class provides functionality to control Conrad card with 4 relais.

    Parameters
    ----------
    delay_time: Float value for relais delay time

    """
    relais_delay_time = None

    def __init__(self, delay_time=0.01):
        self.port = self.check_comport()
        if not self.port:
            raise RuntimeError('Could not communicate with Conrad Relay card (4 x relais)')

        if not isinstance(delay_time, float):
            raise RuntimeError('for delay_time a float is required')

        self.set_delay(delay_time)
        PyCP210xAccess.init()

    def set_delay(self, delay_time):
        """Get the relais delay time

        :param delay_time: float value
        :return: True/False
        """
        if not isinstance(delay_time, float):
            return False

        if delay_time < 0.01:
            return False

        self.relais_delay_time = delay_time
        return True

    def get_delay(self):
        """ Get the relais delay time

        :return: relais delay time
        """
        return self.relais_delay_time

    def check_comport(self):
        """ Get the windows COM port which is connected to PC

        :return: Com Port
        """
        com_port_name = ""
        check_comports = list(serial.tools.list_ports.comports())

        if len(check_comports) != 0:
            comPorts = list(serial.tools.list_ports.comports())
            for portnumber in range(len(comPorts)):
                vid = comPorts[portnumber].vid
                pid = comPorts[portnumber].pid
                #serial_nbr = comPorts[portnumber].serial_number
                if vid == 4292 and pid == 60000:
                    com_port_name = comPorts[portnumber].device

        if com_port_name == "":
            return False

        return com_port_name

    def check_relais_number(self, relaisnum):
        """ Set the relais to off  state.

        :param relaisnum:
        :return:
        """
        relais = False
        if relaisnum <= 4 and relaisnum >= 1 and isinstance(relaisnum, int):
            if relaisnum == 1:
                relais = 0x01
            else:
                relais = 0x01 << relaisnum - 1
        else:
            return relais

        return relais

    def turn_on(self, relaisnum):
        """ Set the relais to off  state.

        :param relaisnum:
        :return:
        """
        relais = self.check_relais_number(relaisnum)
        if not relais:
            return False

        port = self.check_comport()
        if not port:
            raise RuntimeError('No hardware detected')

        PyCP210x.writelatch(port, relais, 0)  # pylint: disable=c-extension-no-member
        sleep(self.relais_delay_time)
        return True

    def turn_off(self, relaisnum):
        """ Set the relais to off  state.

        :param relaisnum:
        :return:
        """
        relais = self.check_relais_number(relaisnum)
        if not relais:
            return False

        port = self.check_comport()
        if not port:
            raise RuntimeError('No hardware detected')

        PyCP210x.writelatch(port, relais, 255)  # pylint: disable=c-extension-no-member
        sleep(self.relais_delay_time)
        return True

    def toggle(self, relaisnum):
        """ Toggle relais status.

        :param relaisnum:
        :return:
        """
        raise NotImplementedError("toggle relais is not implemented yet")

    def status(self, relaisnum):
        """ Get relais status.

        :param relaisnum:
        :return:
        """
        raise NotImplementedError("get relais status is not implemented yet")
