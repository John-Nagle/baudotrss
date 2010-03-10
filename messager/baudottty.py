#
#	baudotty --  Support for Baudot TTY, Model 15, etc.
#
#	Requires PySerial 2.5 or later for 5-bit serial support.
#
#	License: LGPL.
#
#	John Nagle
#	February, 2009
#
#
import serial								# PySerial
import baudot								# baudot charset info
import re
import threading
import time
assert(serial.VERSION.split('.') >= ['2','4'])	# ***TEMP*** should be 2.5, but PySerial has wrong version string.
#
#	Constants
#
#	See "http://www.aetherltd.com/connectingusb.html" for the USB to serial converter electronics used.
#
kspeedsafetymargin = (1.0 + 0.03)					# allow for 3% speed error in print estimation
kactualbaud = {600 : 45 }							# remapping of baud rates by special USB devices.

#
#	Regular expressions
#
re1a = re.compile(r'\r')							# for removing CR
re1b = re.compile(r'\n')							# for changing newline to CR
#
#	BaudotKeyboardInterrupt  -- distinguish between an interrupt from the Baudot keyboard and the computer console
#
class BaudotKeyboardInterrupt(Exception) :
	pass
#
#	class BaudotTTY  --  support for one Baudot TTY
#
class BaudotTTY(object) :
	def __init__(self) :
		self.ser = None								# no serial port yet
		self.conv = None							# no conversion table yet
		self.motoron = False						# motor not running
		self.outputcolmax = 72						# carriage width
		self.motorstartdelay = 2.0					# seconds to wait for motor start
		self.charsecs = 0.25						# time to print one char, default
		self.lock = threading.Lock()				# lock object
		self.clear()								# reset to start state
		self.eolsettings()							# set EOL settings

	def clear(self) :								# reset to start state
		self.outputcol = None						# output column position unknown
		self.outputshift = None						# shift state unknown
		self.kybdinterrupt = False					# not handling a keyboard interrupt
		self.printend = time.time()					# est. printing completion time

	def eolsettings(self, eolextralf=False, eolextraltrs = 2) : # extra chars at end of line.
		self.eolextraltrs = eolextraltrs			# send this many extra LTRS end of line (for CR delay)
		self.eolextralf = eolextralf				# send LF on CR (if machine doesn't do that in hardware)



	#
	#	open  --  open a serial port for 45.45 baud, 5N1.5
	#
	def open(self, port, baud=45.45, timeout=None) :
		if self.ser :
			self.close()							# close old port instance
		self.ser = serial.Serial(port, baudrate=baud, timeout=timeout, 
				bytesize=serial.FIVEBITS, 
				parity=serial.PARITY_NONE, 
				stopbits=serial.STOPBITS_ONE_POINT_FIVE)
		actualbaud = float(baud)					# actual baud rate
		if int(baud) in kactualbaud :				# if using specially configured USB device
			actualbaud = kactualbaud[actualbaud]	# remap 600 baud request to 45 baud actual, etc.
		self.charsecs = kspeedsafetymargin * (1 + 5 + 1.5) / actualbaud	# time to send one char, seconds
		self.clear()								# reset to start state
		self.conv = baudot.Baudot()					# get Baudot conversion object
		self.ser.setDTR(1)							# DTR to 1, so we can use DTR as a +12 supply 
		self.ser.setRTS(0)							# motor is initially off

	#
	#	close  --  close port
	#
	def close(self) :
		with self.lock :							# lock
			if self.ser :							# output
				self.ser.setRTS(0)					# stop motor
				self.ser.setDTR(0)					# turn off DTR, for no good reason
				self.motoron = False				# motor is off
				self.ser.close()					# close port
				ser = None							# release serial port


	#	
	#	motor  --  turn motor on/off
	#
	#	The assumption here is that the RTS signal is connected to something
	#	that turns the Teletype's motor on and off.  A solid-state relay
	#	is suggested.  This does NOT support classical Teletype motor control
	#	via a character sequence to turn off and a break to turn on.
	#
	def motor(self, newstate) :
		if self.motoron == newstate :					# if in correct state
			return
		if newstate :									# if turning on
			self.ser.setRTS(1)							# turn on motor
			time.sleep(self.motorstartdelay)			# wait for motor to come up to speed
		else :
			self.ser.setRTS(0)							# turn off motor
		self.motoron = newstate							# record new state
	#
	#	motorison -- true if motor is on
	#
	def motorison(self) :
		return(self.motoron)							# true if motor is on
	#
	#	flushOutput  --  discard queued output.
	#
	def flushOutput(self) :
		with self.lock :
			self.kybdinterrupt = True					# set keyboard interrupt
			self.ser.flushOutput()						# flush output
			#	Temporarily shift to high baud rate to flush on platforms that don't do flushOutput properly.
			#	This is a hack for USB to serial devices with big buffers.
			oldbaud = self.ser.getBaudrate()			# get baud rate
			self.ser.setBaudrate(115200)				# set huge baud rate, 200x Teletype rate
			###print("Flushing using %d baud rate." % (self.ser.getBaudrate(), ))	# ***TEMP***
			time.sleep(1.0)								# wait 500ms
			self.ser.setBaudrate(oldbaud)				# back to old baud rate
			self.outputshift = None						# shift state unknown
			self.outputcol = None						# column position unknown
			self.printend = time.time()					# est. printing completion time is now
	#
	#	_writeser  -- write bytes to device
	#
	#	Internal use only, must be locked first
	def _writeser(self, s) :
		self.ser.write(s)								# write
		now = time.time()								# calc time left to finish printing
		if now > (self.printend + 1.0) :				# if printing should have finished by now
			self.printend = now							# restart printing timer
		self.printend +=  len(s) * self.charsecs		# add to est. printing completion time

	#
	#	_writeeol  --  write end of line sequence
	#
	#	Internal use only; must be locked first.
	#
	def _writeeol(self) :
		sout = bytearray()
		if self.outputcol == 0 :
			sout.append(baudot.Baudot.LF)				# Newline at start of line, just send LF
		else :											# not at beginning of line
			sout.append(baudot.Baudot.CR)				# need CR
			#	Add LF after CR if so configured.
			if self.eolextralf :						# if machine needs LF on CR
				sout.append(baudot.Baudot.LF)			# send an LF before CR
			#	Add extra LTRS at end of line, to allow for physical carriage movement.
			if self.eolextraltrs > 0  :					# if carriage return delay needed
				for i in range(self.eolextraltrs) :		# send extra LTRS
					sout.append(baudot.Baudot.LTRS)		# to allow time for CR to occur
				self.outputshift = baudot.Baudot.LTRS	# now in LTRS shift
		if sout != '':
			self._writeser(str(sout))					# write EOL sequence
		self.outputcol = 0								# now at beginning of line
		
	#
	#	outwaitingtime -- time left to print
	#
	#	Used to decide when to turn motor off.
	#	The USB to serial converter has a huge buffer, and we can't tell when it is empty.
	#	So we have to estimate by counting output chars and timing.
	#		
	def outwaitingtime(self) :
		return(max(0.0, self.printend - time.time()	+ 1.0))	# est. time left to end of printing
	#
	#	outwaiting -- number of chars remaining to print
	#
	#	Used to decide when to turn motor off.
	#	The USB to serial converter has a huge buffer, and we can't tell when it is empty.
	#	So we have to estimate by counting output chars and timing.
	#		
	def outwaiting(self) :
		charsleft = int(max(0, self.outwaitingtime() / self.charsecs))	# chars left to print
		return(charsleft)
			
	#
	#	writebaudotch  --  write chars in Baudot.  All output must go through here.
	#
	def writebaudotch(self,ch, shift) :
		with self.lock :
			if ch is None :								# if no char, just querying for shift state
				finalshift = self.outputshift			# return current shift state
				return(finalshift)
			ch = bytes(ch)								# force to type bytes
			self.motor(True)							# turn on motor if needed
			if self.outputcol is None :					# if position unknown
				self._writeeol()						# force a CR
			#	Do shift if needed
			if shift != None :							# if shift matters
				if shift != self.outputshift :			# if shift needed
					self._writeser(shift)				# do shift
					self.outputshift = shift			# update shift state
			#	Update shift state after sending char
			if ch == baudot.Baudot.LTRS :				# if LTRS
				self.outputshift = baudot.Baudot.LTRS	# now in LTRS
			elif ch == baudot.Baudot.FIGS :				# if FIGS
				self.outputshift = baudot.Baudot.FIGS	# now in FIGS
			elif ch == baudot.Baudot.SPACE and self.outputshift == baudot.Baudot.FIGS : # if possible unshift on space
				self.outputshift = None					# now unknown
			#	Handle line position update	
			if ch == baudot.Baudot.CR  :				# if CR was requested
				self._writeeol()						# do end of line processing
			else :
				self._writeser(ch)						# write requested Baudot character to device
				if self.conv.printableBaudot(ch,self.outputshift) :	# spacing char
					self.outputcol += 1	
				if self.outputcol >= self.outputcolmax:	# if CR processing needed
					self._writeeol()					# force a CR
			####print("%s  Col.%3d  Shift: %s" % (repr(ch),self.outputcol,repr(self.outputshift)))			# ***TEMP***
			finalshift = self.outputshift				# get final shift state	
		return(finalshift)								# return final shift state, unlocking

	#
	#	readbaudot  --  read chars in Baudot.  Blocking, no echo.
	#
	def readbaudot(self) :							# read from tty
		return(self.ser.read())						# return Baudot string read

	#
	#	doprint --  print string to serial port, with appropriate conversions
	#
	def doprint(self, s) :
		s = s.encode('ascii','replace')				# text might contain Unicode, get clean ASCII
		s = re1a.sub('',s)							# remove all CR
		s = re1b.sub('\r',s)						# change newline to CR
		for ch in s :								# for all chars
			if self.kybdinterrupt :					# if interrupted
				break								# stop typing
			(b, shift) = self.conv.chToBaudot(ch)	# convert char to Baudot and shift
			####print("Doprint: %s -> %2d %s" % (repr(ch), ord(b), repr(shift)))	# ***TEMP***
			self.writebaudotch(b,shift)				# write char, updating state
		with self.lock :							# critical section for kybd check
			if self.kybdinterrupt :					# if keyboard interrupt
				self.kybdinterrupt = False			# clear keyboard interrupt
				raise BaudotKeyboardInterrupt("Typing aborted")	# abort output
#
#	Non-class utility functions
#
#
#	wordwrap  --  basic word wrap for strings
#
#	The default width is 64, just before a Model 15 teletype rings the margin bell.
#	"maxword" is the maximum word length which will never be split.
#
def wordwrap(s, maxline=64, maxword=15) :
	s = re1a.sub('',s)						# remove all CR, to avoid position counting problems
	lines = s.split('\n')					# split into individual lines
	outlines = []							# output lines
	for line in lines :						# for each line
		sline = ''
		while len(line) > maxline :			# while line too long
			ix = line.rfind(' ',maxline-maxword,maxline)	# find space at which to break
			if ix < 1 :						# if no reasonable break point
				sline += line[0:maxline] + '\n'	# take part of line before break
				line = line[maxline:]		# part of line after break
			else: 
				sline += line[0:ix] + '\n'	# take part of line before space
				line = line[ix+1:]			# part of line after space
		sline += line						# accum remainder of line
		outlines.append(sline)				# next line
	return('\n'.join(outlines))				# rejoin lines
#
#	convertnonbaudot  --  convert characters not printable in Baudot to reasonable equivalents.
#
re2 = re.compile(r'[\[\{\<]')				# convert all left bracket types to (
re3 = re.compile(r'[\]\}\>]')				# convert all right bracket types to )
re4 = re.compile(r'%')						# convert all % to " pct."
re5 = re.compile(r'[|_]')					# convert '| and "_' to "-"

#	The Baudot table converts unknown characters to "?".  This is more generous.
#
def convertnonbaudot(s) :
	s = re2.sub('(',s)						# convert all left bracket types to (
	s = re3.sub(')',s)						# convert all right bracket types to )
	s = re4.sub(' pct.',s)					# spell out % abbrev, not in Baudot
	s = re5.sub('-',s)						# underscore and vertical bar to hyphen
	return(s)



			
			
		
