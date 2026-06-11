import argparse
import json
import logging
import os
import subprocess
import sys
import shutil
import re

class PowerSupply:
    """Class used to setup, turn on and off a power supply
    """

    ERROR_CODE = 1
    SUCCESS_CODE = 0

    relais = False
    power = False

    args = ()
    root = 0

    TENMA = "TENMA"
    MANSON = "MANSON"
    RELAY = "RELAY"
    NOTSWITCHABLE = "NOTSWITCHABLE"

    # TENMA is the default powersupply set with env variable "POWERSUPPLY_ENV_VAR"
    env_powersupply = TENMA

    # relay number 1 is the default relay set with env variable "RELAYNUMBER_ENV_VAR"
    relay_number = 1

    # to be moved to config
    default_voltage = 12.5
    default_current = 4.0

    def __init__(self, logging_level=None):
        """Initialize logger and logging level\n
        ----------

        :param logging_level: Level of logging to be used, default: WARNING
        """
        FORMAT = '[%(levelname)-8s %(name)-10s %(asctime)-15s] %(message)s'
        logging.basicConfig(format=FORMAT)
        self.log_it = logging.getLogger(__name__)
        self.log_it.setLevel(logging.WARNING)
        if logging_level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL):
            self.log_it.setLevel(logging_level)

        available, env_powersupply = self.get_env_var_val("POWERSUPPLY_ENV_VAR")
        if available == True:
            self.env_powersupply = env_powersupply

        if self.env_powersupply == self.RELAY:
            available, relay_number = self.get_env_var_val("RELAYNUMBER_ENV_VAR")
            if available == True:
                self.relay_number = int(relay_number)

    def parser(self, args):
        """Parse arguments passed to the script\n
        ----------

        :param list args: command line arguments
        :return: True, if no errors occur, else False
        :raises: ArgumentError
        """

        if not isinstance(args, list):
            self.log_it.error("provided parameter is not a list")
            return False
        # Check if there is no arguments given (script name is always the first argument)
        if args.__len__() <= 1:
            self.log_it.critical("Please provide proper parameters: %s -h", __file__)
            args.append("-h")
        # The first argument in the argument list is always the name of the script, so we do remove it
        args.pop(0)

        for arg in args:
            if not isinstance(arg, (str)):
                self.log_it.critical("provided parameter in list is not a string")
                return False

        parser = argparse.ArgumentParser()
        parser.add_argument("-v", "--verbose", action="count", dest="verbose", default=0, help="enable Verbose mode")
        parser.add_argument("-c", "--config", action="store", dest="configfile", required=False, type=str,
                            help="configuration file for interface parameters")
        parser.add_argument("-ps", "--powersupply", action="store", dest="powersupply", required=False, type=str,
                            help="")
        parser.add_argument("-on", "--turnOn", action="store_true", dest="turnOn", required=False, default=False,
                            help='TurnOn Powersupply')
        parser.add_argument("-off", "--turnOff", action="store_true", dest="turnOff", required=False, default=False,
                            help='TurnOff Powersupply')

        self.args = parser.parse_args(args)

        if self.args.verbose >= 1:
            self.log_it.setLevel(logging.INFO)
        if self.args.verbose >= 2:
            self.log_it.setLevel(logging.DEBUG)

        if self.args.powersupply == "" and not self.args.powersupply in [self.TENMA, self.RELAY, self.MANSON]:
            self.log_it.critical("PowerSupply: %s is incorrect. Please select a valid option (TENMA,RELAY,MANSON)", self.args.powersupply)
            return False

        #self.args.configfile = os.path.expandvars(self.args.configfile)
        #if not os.path.isfile(self.args.configfile):
        #    self.log_it.error("Config file %s does not exist", self.args.configfile)
        #    return False
        return True


    def get_env_var_val(self, env_var):
        """check if environment variable is available and returns it

        :return: availability, val of the env var
        """
        env_var_val = "hallo"
        available = True
        try:
            env_var_val = os.environ[env_var]
        except KeyError:
            self.log_it.warning("Environement Var \"%s\" is not set!", env_var)
            available = False

        self.log_it.info("Environement Var \"%s\" is set to \"%s\"!", env_var, env_var_val)

        return available, env_var_val


    def check_TenmaPower(self):
        from tenmapowersupply import TenmaPowerSupply
        try:
            self.power = TenmaPowerSupply(max_voltage=13,max_current=5.0)
        except KeyError:
            self.log_it.error("ERROR: Can not find a TENMA, please check!")
            return False

        if not self.power.connect():
            self.log_it.error("ERROR: Can not connect to the TenmaPowerSupply")
            return False
            
        self.log_it.info("Connect to the TenmaPowerSupply")
        self.power.set_voltage(self.default_voltage)
        self.power.set_current(self.default_current)

        self.log_it.info("Voltage  = %s ", self.power.get_actual_output_voltage())
        return True


    def check_MansonPower(self):
        return False


    def check_RelayCard(self):
        from ControlRelaisConrad4 import ControlRelaisConrad4
        try:
            self.power = ControlRelaisConrad4()
        except KeyError:
            self.log_it.error("ERROR: Can not find a Conrad Relay Card, please check!")
            return False

        self.log_it.info("RelayCard is connected to COMPort: %s ", self.power.check_comport())

        return True


    def get_powersupply(self):
        
        if self.env_powersupply == self.NOTSWITCHABLE:
            self.log_it.info("Setup is not switchable! Make sure posersupply is on/off!")
            return True
			
        elif self.env_powersupply == self.TENMA:
            if self.check_TenmaPower():
                self.log_it.info("TenmaPowerSupply found!")
                return True

        elif self.env_powersupply == self.MANSON:
            if self.check_MansonPower():
                self.log_it.info("MansonPowerSupply found!")
                return True

        elif self.env_powersupply == self.RELAY:
            if self.check_RelayCard():
                self.log_it.info("RelayCard found!")
                return True

        self.log_it.error("No PowerSupply or relay card found, please check!")
        return False


    def execute_request(self):

        if self.env_powersupply != self.NOTSWITCHABLE:
            if self.args.turnOn:
                if self.env_powersupply == self.TENMA:
                    self.power.output_on()
                    self.power.disconnect()
                elif self.env_powersupply == self.MANSON:
                    # not yet implemented                
                    return False
                elif self.env_powersupply == self.RELAY:
                    self.power.turn_on(self.relay_number)
                else:
                    self.log_it.error("No PowerSupply or relay card was selected!")
                    return False

            elif self.args.turnOff:
                if self.env_powersupply == self.TENMA:
                    self.power.output_off()
                    self.power.disconnect()
                elif self.env_powersupply == self.MANSON:
                    # not yet implemented
                    return False
                elif self.env_powersupply == self.RELAY:
                    self.power.turn_off(self.relay_number)
                else:
                    self.log_it.error("No PowerSupply or relay card was selected!")
                    return False

        return True


    def main(self, argv=()):
        """Main routine of the Powersupply index

        :param list argv: list of command line arguments
        :return: True if Powersupply was executed correctly
        """
        if not self.parser(argv):
            self.log_it.error("While parsing cli arguments")
            return self.ERROR_CODE

        if not self.get_powersupply():
            self.log_it.error("While checking for Powersupply")
            return self.ERROR_CODE

        if not self.execute_request():
            self.log_it.error("While executing request")
            return self.ERROR_CODE


if __name__ == '__main__':
    POWER_SUPPLY = PowerSupply()
    sys.exit(POWER_SUPPLY.main(sys.argv))


