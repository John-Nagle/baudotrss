#
#	baudotty --  Support for Baudot TTY, Model 15, etc.
#
#	Python 2.6 or later.
#
#	License: LGPL.
#
#	John Nagle
#	February, 2009
#
#
import serial								# PySerial
import pyserialpatches						# Patch to allow 1.5 stop bits.
import baudot								# baudot charset info
import re
import threading
import time
#
#	Constants
#
#
#	Regular expressions
#
re1a = re.compile(r'\r')					# for removing CR
re1b = re.compile(r'\n')					# for changing newline to CR
#
#	class BaudotTTY  --  support for one Baudot TTY
#
class BaudotTTY(object) :
	def __init__(self) :
		self.ser = None						# no serial port yet
		self.conv = None					# no conversion table yet
		self.motoron = False				# motor not running
		self.outputcolmax = 72				# carriage width
		self.motorstartdelay = 2.0			# seconds to wait for motor start
		self.lock = threading.Lock()		# lock object
		self.clear()						# reset to start state
		self.eolsettings()					# set EOL settings

	def clear(self) :						# reset to start state
		self.outputcol = None				# output column position unknown
		self.outputshift = None				# shift state unknown
		self.kybdinterrupt = False			# not handling a keyboard interrupt

	def eolsettings(self, eolextralf=False, eolextraltrs = 2) : # extra chars at end of line.
		self.eolextraltrs = eolextraltrs			# send this many extra LTRS end of line (for CR delay)
		self.eolextralf = eolextralf				# send LF on CR (if machine doesn't do that in hardware)



	#
	#	open  --  open a serial port for 45.45 baud, 5N2
	#
	def open(self, port, baud=45.45) :
		if self.ser :
			self.close()							# close old port instance
		self.ser = pyserialpatches.BaudotSerial(port, baudrate=baud, 
				bytesize=serial.FIVEBITS, 
				parity=serial.PARITY_NONE, 
				stopbits=serial.STOPBITS_ONE5)
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
	#	flushOutput  --  discard queued output.
	#
	def flushOutput(self) :
		with self.lock :
			self.kybdinterrupt = True					# set keyboard interrupt
			self.ser.flushOutput()						# flush output
			self.outputshift = None						# shift state unknown
			self.outputcol = None						# column position unknown

	#
	#	_writeeol  --  write end of line sequence
	#
	#	Internal use only; must be locked first.
	#
	def _writeeol(self,needcr) :
		sout = bytearray()
		if needcr :
			sout.append(baudot.Baudot.CR)				# if need CR
		#	Add LF before CR if so configured.
		#	Add extra LTRS at end of line, to allow for physical carriage movement.
		if self.eolextralf :							# if machine needs LF on CR
			sout.append(baudot.Baudot.LF)				# send an LF before CR
		if self.eolextraltrs > 0:						# if carriage return
			for i in range(self.eolextraltrs) :			# send extra LTRS
				sout.append(baudot.Baudot.LTRS)			# to allow time for CR to occur
			self.outputshift = baudot.Baudot.LTRS		# now in LTRS shift
		if sout != '':
			self.ser.write(str(sout))					# write EOL sequence
		self.outputcol = 0								# now at beginning of line		
		
	#
	#	writebaudotch  --  write chars in Baudot.  All output must go through here.
	#
	def writebaudotch(self,ch, shift) :
		ch = bytes(ch)									# force to type bytes
		with self.lock :
			self.motor(True)							# turn on motor if needed
			if self.outputcol is None :					# if position unknown
				self._writeeol(True)					# force a CR
			#	Do shift if needed
			if shift != None :							# if shift matters
				if shift != self.outputshift :			# if shift needed
					self.ser.write(shift)				# do shift
					self.outputshift = shift			# update shift state
			self.ser.write(ch)							# write binary to tty
			#	Update state after sending char
			if ch == baudot.Baudot.LTRS :				# if LTRS
				self.outputshift = baudot.Baudot.LTRS	# now in LTRS
			elif ch == baudot.Baudot.FIGS :				# if FIGS
				self.outputshift = baudot.Baudot.FIGS	# now in FIGS
			elif ch == baudot.Baudot.SPACE and self.outputshift == baudot.Baudot.FIGS : # if possible unshift on space
				self.outputshift = None					# now unknown
			#	Handle line position update	
			if ch == baudot.Baudot.CR  :				# if CR processing needed
				self._writeeol(False)					# do end of line processing, without another CR
			elif self.conv.printableBaudot(ch,self.outputshift) :	# spacing char
				self.outputcol += 1	
			if self.outputcol >= self.outputcolmax:		# if CR processing needed
				self._writeeol(True)					# force a CR
		####print("%s  Col.%3d  Shift: %s" % (repr(ch),self.outputcol,repr(self.outputshift)))			# ***TEMP***	
		return(self.outputshift)						# return final shift state

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
				raise KeyboardInterrupt("Typing aborted")	# abort output
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



			
			
		
