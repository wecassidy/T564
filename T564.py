"""
Control class for the T564 pulse generator
"""

from __future__ import division, print_function
import serial

class T564(object):
    """
    A Python interface to the serial programming interface of the
    Highland Technology T564 4-channel compact advanced digital delay
    and pulse train generator.

    Simple usage
    ------------

        >>> gen = T564() # Set up the generator
        >>> gen.a.delay = "500u" # Change the settings on a channel
        >>> gen.write("USEC", "FIRE") # Write one or more commands over the serial interface
        ["415238", "OK"]
    """

    def __init__(self, address="/dev/ttyUSB0"):
        """Read the status of the T564."""

        self.device = serial.Serial(address,baudrate=38400,timeout=1) #,stopbits=1,parity='N',timeout=1)

        # Channel interfaces
        self.a = Channel(self, "A")
        self.b = Channel(self, "B")
        self.c = Channel(self, "C")
        self.d = Channel(self, "D")

    def write(self, *commands):
        """
        Write one or more commands over the serial interface.
        Multiple commands will be joined into one long string to be
        sent; a response will only be received once all commands have
        been executed.  As such, this method will block the execution
        of the program if a long command (e.g. WAIT) is executed.

        Returns the responses in a list of strings, one per line of
        response.
        """
        self.device.write(";".join(commands)+"\r") # '\r' (carriage return) terminates commands
        return self.device.readlines()

    def status(self):
        statstring = self.write("STATUS")
        for li in statstring: print(li)

    def save(self):
        """
        Save the current settings to nonvolatile memory.  Use the
        T564.recall() method to load saved settings.
        """
        return self.write("SA")

    def recall(self):
        """Load the settings saved in nonvolatile memory."""
        return self.write("RE")

    def set_trigger_level(self,trigger_level):
        return self.write("TLEVEL " + str(trigger_level))

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
            raise ValueError("{} is not a valid channel.".format(channel))
        else:
            return chanDict[channel]

    @staticmethod
    def norm_time(val):
        """Convert a time number string to a float number of nanoseconds."""

        val = str(val) # Convert to a string if it isn't already one
        try: # Already in nanoseconds
            duration = float(val)
        except ValueError: # Unit included
            unit = val[-1]
            number = val[:-1]
            if unit == "p":
                duration = float(number) * 1e-3
            elif unit == "n":
                duration = float(number)
            elif unit == "u":
                duration = float(number) * 1e3
            elif unit == "m":
                duration = float(number) * 1e6
            elif unit == "s":
                duration = float(number) * 1e9
            else:
                raise ValueError("Invalid unit: {}".format(unit))

        return duration

class Channel(object):
    """A T564 channel"""

    def __init__(self, device, name):
        self.name = T564.norm_channel(name) # The name of the channel (A, B, C, or D)
        self.device = device # The T564 object so that the channel can set its values
        self._status = self.get_status()

    def get_status(self):
        """Get the settings of the channel from the T564."""

        # Communicate with the T564
        command = "{}S".format(self.name)
        response = self.device.write(command)[0]

        # Parse response
        if response != "??":
            terms = response.split()

            # Example response: "Ch A  POS  ON     Dly  00.000,000,000,000  Wid  00.000,002,000,000"
            status = {
                "polarity": terms[2] == "POS",
                "enabled": terms[3] == "ON",

                # When parsing numbers, remove commas that may have been
                # added by verbose mode and convert seconds to nanoseconds
                "delay": float(terms[5].replace(",", "")) * 1e9,
                "width": float(terms[7].replace(",", "")) * 1e9
            }

            return status
        else: # An error occurred
            raise RuntimeError("Error executing command \"{}\".".format(command))

    @property
    def status(self):
        """All the settings of the channel as a dict"""
        return self._status

    @property
    def enabled(self):
        """Is output from the channel on or off?"""
        return self._status["enabled"]
    @enabled.setter
    def enabled(self, val):
        if val:
            self._status["enabled"] = True
            self.device.write("{}S ON".format(self.name))
        else:
            self._status["enabled"] = False
            self.device.write("{}S OF".format(self.name))

    @property
    def polarity(self):
        """True: the channel is active-high, False: the channel is active-low"""
        return self._status["polarity"]
    @polarity.setter
    def polarity(self, val):
        if isinstance(val, str):
            val = val.lower()
            if val == "po" or val == "pos":
                self._status["polarity"] = True
                self.device.write("{}S PO".format(self.name))
            elif val == "ne" or val == "ne":
                self._status["polarity"] = False
                self.device.write("{}S NE".format(self.name))
            else:
                raise ValueError("Invalid polarity: {}".format(val))
        else:
            if val:
                self._status["polarity"] = True
                self.device.write("{}S PO".format(self.name))
            else:
                self._status["polarity"] = False
                self.device.write("{}S NE".format(self.name))

    @property
    def delay(self):
        """Delay between pulses in nanoseconds"""
        return self._status["delay"]
    @delay.setter
    def delay(self, val):
        val = T564.norm_time(val)
        self._status["delay"] = val
        self.device.write("{chan}D {arg:f}".format(chan=self.name, arg=val))

    @property
    def width(self):
        """Length of a pulse in nanoseconds"""
        return self._status["width"]
    @width.setter
    def width(self, val):
        val = T564.norm_time(val)
        self._status["width"] = val
        self.device.write("{chan}W {arg:f}".format(chan=self.name, arg=val))
