#
#	Patches to PySerial for Baudot operation at 45.45 baud on Win32
#
#	This is Windows-only.  Stock POSIX will not support 45.45 baud, because
#	that wasn't an option on the PDP-11. 
#
#	Subclasses serial.Serial to override _reconfigurePort. 
#
#	Should be unnecessary when a version of "pyserial" with a date of 2009 or
#	later is released.  This fix is in the "pyserial" SVN repository, but
#	not in the downloadable version.
#
#	License; LGPL. 
#
#	John Nagle
#	February, 2009
#
import win32file  # The base COM port and file IO functions.
import win32con   # constants.
import serial
from serial.serialutil import *

#	Patches to definitions
STOPBITS_ONE5 = serial.STOPBITS_ONE5 = serial.serialutil.STOPBITS_ONE5 = 3 # add support for 1.5 stop bits
serial.serialutil.SerialBase.STOPBITS  = (STOPBITS_ONE, STOPBITS_TWO, STOPBITS_ONE5)
#### print(serial.serialutil.SerialBase.STOPBITS)
#
#	BaudotSerial - version of Win32 _reconfigurePort modified to handle 1.5 stop bits
#
class BaudotSerial(serial.Serial) :
    def _reconfigurePort(self):
        """Set communication parameters on opened port."""
        ####print("Using patched reconfigurePort")			### ***TEMP***
        if not self.hComPort:
            raise SerialException("Can only operate on a valid port handle")

        # Set Windows timeout values
        # timeouts is a tuple with the following items:
        # (ReadIntervalTimeout,ReadTotalTimeoutMultiplier,
        #  ReadTotalTimeoutConstant,WriteTotalTimeoutMultiplier,
        #  WriteTotalTimeoutConstant)
        if self._timeout is None:
            timeouts = (0, 0, 0, 0, 0)
        elif self._timeout == 0:
            timeouts = (win32con.MAXDWORD, 0, 0, 0, 0)
        else:
            timeouts = (0, 0, int(self._timeout*1000), 0, 0)
        if self._timeout != 0 and self._interCharTimeout is not None:
            timeouts = (int(self._interCharTimeout * 1000),) + timeouts[1:]

        if self._writeTimeout is None:
            pass
        elif self._writeTimeout == 0:
            timeouts = timeouts[:-2] + (0, win32con.MAXDWORD)
        else:
            timeouts = timeouts[:-2] + (0, int(self._writeTimeout*1000))
        win32file.SetCommTimeouts(self.hComPort, timeouts)

        win32file.SetCommMask(self.hComPort, win32file.EV_ERR)

        # Setup the connection info.
        # Get state and modify it:
        comDCB = win32file.GetCommState(self.hComPort)
        comDCB.BaudRate = self._baudrate

        if self._bytesize == FIVEBITS:
            comDCB.ByteSize     = 5
        elif self._bytesize == SIXBITS:
            comDCB.ByteSize     = 6
        elif self._bytesize == SEVENBITS:
            comDCB.ByteSize     = 7
        elif self._bytesize == EIGHTBITS:
            comDCB.ByteSize     = 8
        else:
            raise ValueError("Unsupported number of data bits: %r" % self._bytesize)

        if self._parity == PARITY_NONE:
            comDCB.Parity       = win32file.NOPARITY
            comDCB.fParity      = 0 # Dis/Enable Parity Check
        elif self._parity == PARITY_EVEN:
            comDCB.Parity       = win32file.EVENPARITY
            comDCB.fParity      = 1 # Dis/Enable Parity Check
        elif self._parity == PARITY_ODD:
            comDCB.Parity       = win32file.ODDPARITY
            comDCB.fParity      = 1 # Dis/Enable Parity Check
        elif self._parity == PARITY_MARK:
            comDCB.Parity       = win32file.MARKPARITY
            comDCB.fParity      = 1 # Dis/Enable Parity Check
        elif self._parity == PARITY_SPACE:
            comDCB.Parity       = win32file.SPACEPARITY
            comDCB.fParity      = 1 # Dis/Enable Parity Check
        else:
            raise ValueError("Unsupported parity mode: %r" % self._parity)

        if self._stopbits == STOPBITS_ONE:
            comDCB.StopBits     = win32file.ONESTOPBIT
        elif self._stopbits == STOPBITS_TWO:
            comDCB.StopBits     = win32file.TWOSTOPBITS
        elif self._stopbits == STOPBITS_ONE5:
            comDCB.StopBits		= win32file.ONE5STOPBITS   	# Add support for 1.5 stop bits 
        else:
            raise ValueError("Unsupported number of stop bits: %r" % self._stopbits)

        comDCB.fBinary          = 1 # Enable Binary Transmission
        # Char. w/ Parity-Err are replaced with 0xff (if fErrorChar is set to TRUE)
        if self._rtscts:
            comDCB.fRtsControl  = win32file.RTS_CONTROL_HANDSHAKE
        else:
            comDCB.fRtsControl  = self._rtsState
        if self._dsrdtr:
            comDCB.fDtrControl  = win32file.DTR_CONTROL_HANDSHAKE
        else:
            comDCB.fDtrControl  = self._dtrState
        comDCB.fOutxCtsFlow     = self._rtscts
        comDCB.fOutxDsrFlow     = self._dsrdtr
        comDCB.fOutX            = self._xonxoff
        comDCB.fInX             = self._xonxoff
        comDCB.fNull            = 0
        comDCB.fErrorChar       = 0
        comDCB.fAbortOnError    = 0
        comDCB.XonChar          = XON
        comDCB.XoffChar         = XOFF

        try:
            win32file.SetCommState(self.hComPort, comDCB)
        except win32file.error, e:
            raise ValueError("Cannot configure port, some setting was wrong. Original message: %s" % e)

