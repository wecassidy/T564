# Interface for Highland T564 4-channel pulse generator
# Jan 2018, Amar Vutha & Mohit Verma

from __future__ import division,print_function
import serial
import numpy as np
import time

class DelayGenerator_T564:
    def __init__(self,address='/dev/ttyUSB0'):
        self.device = serial.Serial(address,baudrate=38400,timeout=1) #,stopbits=1,parity='N',timeout=1)

    def write(self, command):
        self.device.write(command+"\r")     # terminate commands with '\r', which is a Carriage Return
        return self.device.readlines()

    def status(self):
        statstring = self.write("STATUS")
        for li in statstring: print(li)

    def set_trigger_level(self,trigger_level):
        return self.write("TLEVEL " + str(trigger_level))

    def send_command_sequence(self,command_list):
        return self.write( ';'.join(command_list) )

    @staticmethod
    def norm_channel(channel):
        """Normalize integer/lowercase/uppercase channels to A, B, C, or D."""

        # Lookup table for different representations of the channel
        chanDict =  {
            "A": "A", "a": "A", 0: "A",
            "B": "B", "b": "B", 1: "B",
            "C": "C", "c": "C", 2: "C",
            "D": "D", "d": "D", 3: "D",
            "Q": "Q", "q": "Q" # All four channels
        }

        if channel not in chanDict:
            raise ValueError("{} is not a valid channel.".format(chan))
        else:
            return chanDict[channel]

    def pulse(self, channel, duration):
        """Send a single pulse on a channel."""

        chan = DelayGenerator_T564.norm_channel(channel)

        # To send a single pulse: set the duration on the channel, ensure the trigger
        # is in remote mode, install the settings, fire the trigger
        cmd = ("{}W {}".format(chan, duration), "TR RE", "IN", "FI")

        return self.send_command_sequence(cmd)

gen = DelayGenerator_T564()
gen.status()
gen.pulse("A", "1s");
