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

    General::

        >>> gen = T564() # Set up the generator
        >>> gen.a.delay = "500u" # Change the settings on a channel
        >>> gen.write("USEC", "FIRE") # Write one or more commands over the serial interface
        ["415238", "OK"]

    Frames::

        >>> gen.a.delay = "500u" # Change settings
        >>> gen.a.width = "1m"
        >>> gen.frame_save() # Save first frame
        >>> gen.a.width = "2m" # Change settings
        >>> gen.frame_save() # Save next frame
        >>> gen.a.width = "3m"
        >>> gen.frame_save(0) # Edit saved frame
        >>> gen.frame_loops = 3 # Go through frames 3 times (set to 0 to loop forever)
        >>> gen.frame_start()

    Notes
    -----

        - T564 serial commands are written in ALL CAPS in
          documentation

        - All times are converted to nanoseconds
    """

    # Set FC to this number to loop indefinitely (until FRAME OFF).
    FRAME_FOREVER = 65535

    # Maximum value of FC (the number of times FRAME GO will cycle
    # through the frames after the first run through).
    FRAME_MAX = 65534

    def __init__(self, address="/dev/ttyUSB0"):
        """
        Initialize the T564.

        Requires the serial port the T564 is attached to (default
        /dev/ttyUSB0).
        """

        self.device = serial.Serial(address,baudrate=38400,timeout=1) #,stopbits=1,parity='N',timeout=1)

        self._freq = int(self.write("SY")[0]) # Frequency of the synthesizer, in hertz

        ## Channel interfaces
        self.a = Channel(self, "A")
        self.b = Channel(self, "B")
        self.c = Channel(self, "C")
        self.d = Channel(self, "D")

        ## Frames
        # A dict mapping frame numbers to dicts mapping channel names
        # to channel statuses (which are also dicts, see
        # Channel.status for how they are formatted).
        self.frames = {}
        self._frame_first = int(self.write("FA")[0])
        self._frame_last = int(self.write("FB")[0])

        # This variable tracks the value of FC. However, FC has some
        # quirks: FRAME GO will run through the frames FC+1 times, so
        # that FC 0 will result in one loop, FC 1 will result in two
        # loops, and so on; and an infinite loop is designated by
        # setting the value to 65535 (T564.FRAME_FOREVER). A more
        # user-friendly counter is exposed through the frame_loops
        # property. If frame_loops is set to 4, then FC is set to 3
        # and FRAME GO will loop four times. If frame_loops is set to
        # 0, FC is set to T564.FRAME_FOREVER and FRAME GO will loop
        # indefinitely (until FRAME OFF).
        self._frame_loops = int(self.write("FC")[0])

    def write(self, *commands):
        """
        Write one or more commands over the serial interface.
        Multiple commands will be joined into one long string to be
        sent; a response will only be received once all commands have
        been executed.  As such, this method will block the execution
        of the program if a long command (e.g. WAIT) is executed.

        Returns the responses in a list of strings, one per command.
        """
        self.device.write(";".join(commands)+"\r") # '\r' (carriage return) terminates commands

        response = self.device.readlines() # Read raw response
        response = "\n".join(response) # Join into one long string
        response = response.split(";") # Split again by command

        return response

    def status(self):
        statstring = self.write("STATUS")[0]
        print(statstring)

    def save(self):
        """
        Save the current settings to nonvolatile memory.  Use the
        T564.recall() method to load saved settings.
        """
        return self.write("SA")

    def recall(self):
        """Load the settings saved in nonvolatile memory."""
        return self.write("RE")

    def trigger_software(self):
        """Turn on software triggers."""
        return self.write("TR RE")
    def trigger_fire(self):
        """Fire a software trigger."""
        return self.write("FI")

    @property
    def autoinstall(self):
        """Check the autoinstall settings of the T564."""

        val = int(self.write("AU")[0])
        if val == 0:
            return "off"
        elif val == 1:
            return "install"
        elif val == 2:
            return "queue"
    @autoinstall.setter
    def autoinstall(self, val):
        """
        Change the autoinstall settings of the T564.

        If val is 0, "off", turn off autoinstall.  If val is 1 or
        "install", use INSTALL (normal) mode.  If val is 2 or "queue",
        use QUEUE mode.  See the manual section 4.7.2 for more
        information about the various modes.
        """

        if val == 0 or val == "off":
            return self.write("AU 0")
        elif val == 1 or val == "install":
            return self.write("AU 1")
        elif val == 2 or val == "queue":
            return self.write("AU 2")
        else:
            raise ValueError("Autoinstall setting must be 0/off, 1/install, or 2/queue.")

    @property
    def frequency(self):
        """The frequency of the timing cycle in hertz."""
        return self._freq
    @frequency.setter
    def frequency(self, val):
        """Set the frequency of the timing cycle.

        val: converted to a string.  If not given a unit, assumed to
        be in hertz.  Acceptable units are "m" (megahertz), "k"
        (kilohertz), and "h" (hertz).
        """
        val = str(val)
        try:
            self._freq = float(val) # Already in hz
        except ValueError:
            unit = val[-1]
            number = val[:-1]
            if unit == "m":
                self._freq = float(number) * 1e6
            elif unit == "k":
                self._freq = float(number) * 1e3
            elif unit == "h":
                self._freq = float(number)
            else:
                raise ValueError("Invalid unit: {}".format(unit))

        return self.write("SY {:f}".format(val))
    @property
    def period(self):
        """The period of the timing cycle (time between triggers) in nanoseconds."""
        return 1/self._freq
    @period.setter
    def period(self, val):
        """Set the period of the timing cycle (time between triggers).

        val: converted to a string.  If not given a unit, assumed to
        be in nanoseconds.  Acceptable units are "p" (picoseconds),
        "n" (nanoseconds), "u" (microseconds), "m" (milliseconds), and
        "s" (seconds).
        """
        period = T564.norm_time(val) / 1e9 # Convert to seconds
        self.frequency = 1 / period

    def set_trigger_level(self,trigger_level):
        return self.write("TLEVEL " + str(trigger_level))

    @property
    def frame_first(self):
        """The first frame in the loop."""
        return self._frame_first
    @frame_first.setter
    def frame_first(self, f):
        """Set the first frame in the loop."""
        f = int(f)
        return self.write("FA {:d}".format(f))
    @property
    def frame_last(self):
        """The last frame in the loop."""
        return self._frame_last
    @frame_last.setter
    def frame_last(self, f):
        """Set the last frame in the loop."""
        f = int(f)
        if f <= self.frame_first:
            raise ValueError("Last frame must come after first frame.")
        else:
            return self.write("FB {:d}".format(f))
    @property
    def frame_loops(self):
        """
        The number of times the T564 will loop through the frames when
        T564.frame_start() is called.  If this value is 0, then the
        frames will loop forever.

        FRAME GO runs once, then repeats FC times.  This value is
        therefore one larger than what is returned by FC.
        """
        if self._frame_loops == T564.FRAME_FOREVER:
            return 0
        else:
            return self._frame_loops + 1
    @frame_loops.setter
    def frame_loops(self, num):
        """
        The number of times the T564 will loop through the frames when
        T564.frame_start() is called.  If this value is 0, then the
        frames will loop forever.
        """
        if num < 0:
            raise ValueError("The number of loops must be non-negative.")
        elif num == 0:
            self._frame_loops = T564.FRAME_FOREVER
            return self.write("FC {:d}".format(self._frame_loops))
        elif num <= T564.FRAME_MAX+1:
            self._frame_loops = num - 1 # FRAME GO runs through
            self._frame_loops("FC {:d}".format(self._frame_loops))
        else:
            raise ValueError("The T564 can loop at most {:d} times.".format(T564.FRAME_MAX+1))

    def frame_save(self, frame_num=None):
        """
        Save the current channel settings.  If frame_num is not
        specified, a new frame is used.
        """

        if frame_num is None:
            frame_num = len(self.frames) - 1
            self.frame_last = frame_num
        elif 0 <= frame_num <= 8191:
            raise ValueError("Frame number out of range.")

        self.frames[frame_num] = {
            "A": self.a.status, "B": self.b.status,
            "C": self.c.status, "D": self.d.status
        }

        return self.write("FR {:d}".format(frame_num))

    def frame_start(self):
        """
        Loop through the saved frames.  Note that regular triggers
        won't restart after looping finishes, T564.frame_stop needs to
        run first.
        """
        return self.write("FR GO")

    def frame_stop(self):
        """Stop looping."""
        return self.write("FR OF")

    def frame_looping(self):
        """Check if the T564 is currently running through frames."""
        return self.write("FR")[0] not in ["OFF\r\n", "DONE\r\n"]

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
        """
        Enable or disable the channel.

        val: a truthy value enables the channel and a falsy value
        disables it.
        """

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
        """
        Set the polarity of the channel (active-high or active-low).

        val: if a string, "po"/"pos" for active-high or "ne"/"neg" for
        active-low.  Otherwise, a truthy value sets active-high and a
        falsy value sets active-low.
        """

        if isinstance(val, str):
            val = val.lower()
            if val == "po" or val == "pos":
                active_high = True
            elif val == "ne" or val == "neg":
                active_high = False
            else:
                raise ValueError("Invalid polarity: {}".format(val))
        else:
            active_high = bool(val)

        if active_high:
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
        """
        Set the time between the trigger firing and the rising edge of
        the pulse.

        val: converted to a string.  If not given a unit, assumed to
        be in nanoseconds.  Acceptable units are "p" (picoseconds),
        "n" (nanoseconds), "u" (microseconds), "m" (milliseconds), and
        "s" (seconds).
        """

        val = T564.norm_time(val)
        self._status["delay"] = val
        self.device.write("{chan}D {arg:f}".format(chan=self.name, arg=val))

    @property
    def width(self):
        """Length of a pulse in nanoseconds"""
        return self._status["width"]
    @width.setter
    def width(self, val):
        """
        Set the duration of the pulse.

        val: converted to a string.  If not given a unit, assumed to
        be in nanoseconds.  Acceptable units are "p" (picoseconds),
        "n" (nanoseconds), "u" (microseconds), "m" (milliseconds), and
        "s" (seconds).
        """

        val = T564.norm_time(val)
        self._status["width"] = val
        self.device.write("{chan}W {arg:f}".format(chan=self.name, arg=val))
