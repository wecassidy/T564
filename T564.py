"""
Control class for the T564 pulse generator

Written by: Wesley Cassidy
March, 2018
"""

from __future__ import division, print_function
import itertools
import serial # Communication with T564
from pint import UnitRegistry # Units for physical quantities
ureg = UnitRegistry()

class T564(object):
    """
    A Python interface to the serial programming interface of the
    Highland Technology T564 4-channel compact advanced digital delay
    and pulse train generator.

    Simple usage
    ------------

    General::

        >>> import T564
        >>> from T564 import ureg # Import the unit registry -- not necessary, but makes working with units much easier
        >>> gen = T564.T564() # Set up the generator
        >>> gen.a.delay = 500 * ureg.us # Change the settings on a channel
        >>> gen.write("USEC", "FIRE") # Write one or more commands over the serial interface
        ["415238", "OK"]

    Frames::

        gen.frame_clear() # Clear old frames
        gen.a.delay = 500 * ureg.us # Change settings
        gen.a.width = 1 * ureg.ms
        gen.frame_save() # Save first frame
        gen.a.width = 5 * ureg.ms # Change settings
        gen.frame_save() # Save next frame
        gen.a.width = 20 * ureg.ms
        gen.frame_save() # Edit saved frame
        gen.frame_loops = 3 # Go through frames 3 times (set to 0 to loop forever)
        gen.frame_start()
        
    Pulse trains::
        
        >>> gen.a.width = 500 * ureg.us
        >>> gen.a.delay = 20 * ureg.ns
        >>> gen.train_count = 5
        >>> gen.train_spacing = 1 * ureg.ms
        
    Train mode
    ----------
    
    The T564 can generate a pulse train after each trigger using train
    mode. Set the number of pulses in the train (up to 2^32) using the
    T564.train_count property. To disable pulse trains, set
    T564.train_count to 1.
    
    The spacing between pulses is set by the T564.train_spacing
    property and rounded to the nearest 20 ns. The spacing must be at
    least 80ns greater than the time from the first rising edge on any
    channel to the last falling edge on any channel. Any attempts to
    set the spacing lower than this will result in pulse spacing equal
    to the minimum. The maximum pulse spacing is 10 s.
    
    There must be a delay of at least 20 ns on any channel that is to
    be repeated in the pulse train. This means that if you wish to
    disable the train on any single channel, you can do this by
    setting its delay to any number below that value. The pulse
    spacing calculation does not take into account channels which
    aren't included in the train.
    
    Pulse train settings are included in frames. This means that it is
    possible to have a frame that includes a pulse train followed by
    one without.

    Units
    -----

    T564 handles physical quantities through the Pint package. Use
    is extremely simple: just multiply a scalar by any of the units
    in the unit registry object, ureg. For more information, see
    Pint's documentation at http://pint.readthedocs.io/en/latest/.

    If units aren't specified, the code assumes nanoseconds for
    times and hertz for frequencies.

    Properties
    ----------

    This code makes extensive use of Python's properties feature.
    Properties are a way of assigning getter and setter methods to
    object attributes without changing the user-facing interface.
    Here's a brief example::

        class A(object):
            ...
            @property
            def x(self):
                return self._x
            @x.setter
            def x(self, val):
                if val > 0:
                    self._x = val

    Then, x can be used like any normal attribute, except that it's
    value must be positive::

        >>> a = A()
        >>> a.x = 3
        >>> a.x
        3
        >>> a.x = -1
        >>> a.x
        3

    In this snippet, the @property decorator designates the first A.x
    method as x's getter and @x.setter designates the second A.x
    method as the setter. This means that anytime code accesses A.x,
    the first method will be called and anytime code sets A.x, the
    second will be called. Note that the two methods must have the
    same name. A docstring on the getter method acts as the docstring
    for the property.

    For more information on properties and how to use them, see 
    https://docs.python.org/2/library/functions.html#property.

    Notes
    -----

        - T564 serial commands are written in ALL CAPS in
          documentation
    """

    # Set FC to this number to loop indefinitely (until FRAME OFF).
    FRAME_FOREVER = 65535

    # Maximum value of FC (the number of times FRAME GO will cycle
    # through the frames after the first run through).
    FRAME_MAX_LOOPS = 65534
    
    # Maximum number of frames
    FRAME_MAX_NUM = 8191
    
    
    # Maximum number of pulses per trigger when train mode is on
    TRAIN_MAX_PULSES = 2**32
    
    # Largest spacing between pulses in train mode
    TRAIN_MAX_SPACING = 10 * ureg.s


    # Error messages for each possible error (copied straight from the
    # T564 manual). If bit n of the T564 error number is up,
    # T564.ERROR_MESSAGES[n] is relevant. The last message is for when
    # an error occurred (indicated by a response of "??\r\n"), but
    # none of the error bits are up (e.g. invalid command).
    ERROR_MESSAGES = [
        "VCXO trim value lost",
        "saved setup recall failed",
        "calibration table lost; default cals are used",
        "internal logic error",
        "VCXO failed to lock to external source",
        "powerup DPLL calibration error",
        "DPLL stability error",
        "other error (likely something wrong with the command)"
    ]
    

    def __init__(self, address="/dev/ttyUSB1"):
        """
        Initialize the T564.

        Requires the serial port the T564 is attached to (default
        /dev/ttyUSB0).
        """

        # Open the serial port in nonblocking mode (timeout = 0)
        self.device = serial.Serial(port=address, baudrate=38400, timeout=0) #,stopbits=1,parity='N',timeout=1)
    
        # Default settings
        self.write("VE 0") # Turn off verbose mode
        self.autoinstall = "install" # Automatically install channel settings immediatelys

        self.frequency = 16 * ureg.MHz  # Set the frequency synthesizer to 16 MHz. Code is set up to trigger off internal synthesizer.

        # Channel interfaces
        self.a = Channel(self, "A")
        self.b = Channel(self, "B")
        self.c = Channel(self, "C")
        self.d = Channel(self, "D")
        self.channels = (self.a, self.b, self.c, self.d)
        
        # Disable all channels by default
        for chan in self.channels:
            chan.enabled = False

        # Frames
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

        # Reset all frame variables
        self.frame_clear()
        
        # Train mode
        self._train_count = int(self.write("TC")[0])
        self._train_space = int(self.write("TS")[0]) * 20 * ureg.ns
    
    def self_test(self):
        self.frame_clear()
        self.a.delay = 500 * ureg.us 
        self.a.width = 1 * ureg.ms
        self.frame_save() 
        self.a.width = 3 * ureg.ms  
        self.frame_save() 
        #self.a.width = 5 * ureg.ms
        #self.frame_save() 
        self.frame_loops = 3 # (set to 0 to loop forever)
        self.frame_stop()
        print("! Starting self test !")
        print("A output should output 1,3,5, ms pulses and repeat 300 times")
        print("Running through frames ...")
        self.frame_start()
        while self.frame_looping(): pass
        print("done")
        return

    def write(self, *commands):
        """
        Write one or more commands over the serial interface.
        Multiple commands will be joined into one long string to be
        sent; a response will only be received once all commands have
        been executed.  As such, this method will block the execution
        of the program if a long command (e.g. WAIT) is executed.

        Returns the responses in a list of strings, one per command.
        """

        # By terminating the command with a semicolon, we guarantee
        # the response will contain len(commands) semicolons,
        # followed by \r\n. This means that reading the response can
        # be done more efficiently than "wait one second and see
        # what's in the input buffer".
        self.device.write(";".join(commands)+";\r") # '\r' (carriage return) terminates commands

        responses = [] # All responses to the set of commands, guaranteed one response per command
        resp = "" # The response currently being read
        while len(responses) < len(commands): # Continue until we get all the responses
            byte = self.device.read() # Read a byte, if available
            if byte != ";":
                resp += byte
            else: # Semicolon closes a response
                responses.append(resp)
                resp = ""

        # Consume the extraneous \r\n
        extra = ""
        while extra != "\r\n":
            extra += self.device.read()
            
        return responses

    def status(self):
        statstring = self.write("STATUS")[0]
        print(statstring)

    def save(self):
        """
        Save the current settings to nonvolatile memory.  Use the
        T564.recall() method to load saved settings.
        """
        return self.write("SA")

    def clock_out(self):
        '''
        Outputs 10 MHz clock signal
        '''
        return self.write("CL OU")

    def clock_in(self):
        '''
        Finds and accept an external clock signal to the CLOCK input
        '''
        return self.write("CL IN")

    def clock_status(self):
        return self.write("CL")

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
        """
        The frequency of the timing cycle. If not given a unit,
        assumed to be in hertz. Maximum value: 16 MHz
        """
        return self._freq
    @frequency.setter
    @ureg.wraps(None, (None, ureg.Hz), strict=False)
    def frequency(self, val):
        """Setter method for the frequency property."""
        self._freq = val
        return self.write("SY {:f}".format(self._freq), "TR SY")

    @property
    def period(self):
        """
        The period of the timing cycle (time between triggers). If
        not given a unit, assumed to be in nanoseconds. Minimum
        value: 62.5 ns
        """
        return 1/self._freq
    @period.setter
    @ureg.wraps(None, (None, ureg.ns), strict=False)
    def period(self, val):
        """Setter method for the period property."""
        self.frequency = 1 / val

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
        if f <= self.frame_first and len(self.frames) > 1: # The second check deals with the special case of saving the first frame
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
        elif num <= T564.FRAME_MAX_LOOPS+1:
            self._frame_loops = num - 1 # FRAME GO runs through
            self.write("FC {:d}".format(self._frame_loops))
        else:
            raise ValueError("The T564 can loop at most {:d} times.".format(T564.FRAME_MAX_LOOPS+1))

    def frame_clear(self):
        """
        Clear any saved frames, resetting the frame memory.
        """

        self.frames = {}
        return self.write("RZ")

    def frame_save(self, frame_num=None):
        """
        Save the current channel settings.  If frame_num is not
        specified, a new frame is used.
        """

        if frame_num is None:
            frame_num = self.frame_first + len(self.frames)
            self.frame_last = frame_num
        elif (frame_num >= T564.FRAME_MAX_NUM) or (frame_num < 0):
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
        return self.write("FR")[0].strip() not in ["OFF", "DONE"]
        
    @property
    def train_count(self):
        """The number of pulses in the pulse train. Set to 1 to disable."""
        return self._train_count + 1
    @train_count.setter
    def train_count(self, num):
        """Setter method for the train_count property."""
        
        # Sanity check the argument
        if num < 1:
            raise ValueError("Train count must be positive.")
        elif num > T564.TRAIN_MAX_PULSES:
            raise ValueError("Maximum number of pulses is 2^32.")
        
        self._train_count = num - 1
        self.write("TC {}".format(self._train_count))
        
    @property
    def train_spacing(self):
        """
        Time between sets of pulses in the train. See "Train mode" in
        the class docstring for more information about its limits.
        """
        return self._train_space * 20
    @train_spacing.setter
    @ureg.wraps(None, ureg.ns, strict=False)
    def train_spacing(self, val):
        """Set the train spacing."""
        
        # Get the width between the first rising edge and last falling edge
        rise_times = []
        fall_times = []
        for chan in self.channels:
            if chan.delay >= 20 * ureg.ns and chan.enabled:
                rise_times.append(chan.delay)
                fall_times.append(chan.delay + chan.width)
                
        min_spacing = max(fall_times) - min(rise_times) + 80 * ureg.ns
        
        self._train_space = max(val, min_spacing).to(ureg.ns) / 20
        
        self.write("TS {}".format(self._train_space.magnitude))

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
                "delay": float(terms[5].replace(",", "")) * ureg.s,
                "width": float(terms[7].replace(",", "")) * ureg.s
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

        Truthy values are anything that evaulates to True when
        converted to a boolean, and a falsey value is anything that
        evaluates to False.
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
        """
        The time between the trigger firing and the rising edge of
        the pulse (or falling edge, in negative mode).
        """
        return self._status["delay"]
    @delay.setter
    @ureg.wraps(None, (None, ureg.ns), strict=False)
    def delay(self, val):
        """
        Set the time between the trigger firing and the rising edge of
        the pulse.
        """
        self._status["delay"] = val
        self.device.write("{chan}D {arg:f}".format(chan=self.name, arg=val))

    @property
    def width(self):
        """Length of a pulse."""
        return self._status["width"]
    @width.setter
    @ureg.wraps(None, (None, ureg.ns), strict=False)
    def width(self, val):
        """Set the duration of the pulse."""

        self._status["width"] = val
        self.device.write("{chan}W {arg:f}".format(chan=self.name, arg=val))
