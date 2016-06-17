#
#   dummyteletype --  fake Baudot Teletype emulator
#
#   Talks to computer console window.  For debug usage.
#
#   License: LGPL.
#
#   John Nagle
#   June, 2015
#
import logging
from six.moves import input
import baudot
#
#   Constants
#
ESC = 0x1B                                         # ESC char, ASCII/UNICODE
        
#
#   Dummyteletype  -- dummy serial object
#
class Dummyteletype(object) :                       # really should inherit from raw I/O device

    def __init__(self, port, timeout, baudrate) :
        """
        Constructor
        """
        self.baudot = baudot.Baudot("USTTY")        # our dummy Teletype speaks USTTY, not ITA2
        self.port = port                            # name of port, for messages
        self.timeout = timeout                      # set port properties
        self.baudrate = baudrate
        self.dtr = False
        self.rts = False
        logging.basicConfig()                       # configure logging system
        self.logger = logging.getLogger(port)       # main logger for this port
        self.logger.setLevel(logging.INFO)          # always log if using dummy teletype
        self.inshift = None                         # input side shift state
        self.outshift = None                        # output side shift state
        self.outline = ''                           # line to output
        
    def flushOutput(self) :                         # flush queued output
        if len(self.outline) > 0 :                  # if anything queued
            self.logger.info(self.outline)          # log it
            self.outline = ''                       # clear line
        
    def write(self, s) :                                  
        """
        Write to dummy teletype. Input is Baudot as type bytes
        """
        for bb in s :                               # for Baudot bytes
            if bb == baudot.Baudot.FIGS :           # if FIGS shift
                self.outshift = bb
                continue
            if bb == baudot.Baudot.LTRS :           # if LTRS shift
                self.outshift = bb
                continue
            ch = self.baudot.chToASCII(bb, self.outshift) # convert to ASCII            
            if not ch is None :                 
                if ch in ['\n','\r'] :
                    self.flushOutput()              # display if anything available
                else :
                    self.outline = self.outline + ch # add to output line
        self.inshift = self.outshift                # keep both sides in sync
            
        
    def read(self) :
        """
        Read from dummy Teletype.  Returns Baudot as type bytes. Blocking.
        
        Assumes ASCII keyboard.
        
        ESC sends a break. 
        
        ***NEEDS WORK*** - hard to send plain CR.       
        """
        intext = input()                            # Baudot input as string without trailing null
        self.flushOutput()                          # flush any pending output
        baudotread = bytearray()                    # assemble bytes
        intexta = intext.encode("ASCII","replace")  # convert to bytes
        self.logger.info('Input typed: "%s" -> "%s"' % (intext, repr(intexta)))  # ***TEMP***  
        for inbyte in intexta :                     # for all input chars
            if inbyte == ESC :                      # if ESC character, simulate BREAK
                (bb, shift) = (0,None)              # BREAK
            else :
                 (bb,shift) = self.baudot.chToBaudot(inbyte)  # convert ASCII char to Baudot
            if (not (shift is None)) and shift != self.inshift : # if shifting implied
                baudotread.append(shift)            # put LTRS or FIGS in output
                self.inshift = shift
            baudotread.append(bb)                   # add baudot char
        if len(baudotread) != 1 :                    # if not a single char, 
            baudotread.append(baudot.Baudot.CR)     # add an ending CR in Baudot
        return(baudotread)                            
        
    def close() :
        pass                                        # nothing to do
        
#
#   Serial -- create a dummy serial object connected to a dummy teletype
#
def Serial(port, baudrate, timeout, bytesize, parity, stopbits) :
    """
    Create a dummy serial object
    """
    return(Dummyteletype(port, timeout, baudrate))      # return a dummy serial object
          

