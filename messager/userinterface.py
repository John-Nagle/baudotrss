#
#	userinterface.py  --  keyboard-based user interface for Baudot teletype.
#
#	Python 2.6 or later.
#
#	Main program for news and weather display on Teletype
#
#	License: GPL.
#
#	John Nagle
#	February, 2009
#
import serial								# PySerial
import baudot								# baudot charset info
import threading
import baudottty
import weatherreport						# weather report
import newsfeed
import smssend
import time
import re
import Queue
import optparse
import sys
assert(sys.version_info >= (2,6))				# Requires Python 2.6 or later.
#
#	Globals
#
reutersfeedurl = "http://feeds.reuters.com/reuters/topNews?format=xml"	# news feed as XML
wpostfeedurl = "http://feeds.washingtonpost.com/wp-dyn/rss/business/index_xml"
defaultfeedurls = [reutersfeedurl]								# default feeds to use


#
#	testnews
#
def testnews(ui, feed, repeat = False) :
	waiting = False
	tty = ui.tty								# the teletype to print to
	while repeat :								# read repeatedly - one story per iteration
		item = feed.getitem()					# get a new news item
		if item :								# if something to print
			(title,s) = item					# break into sections
			title = title.encode('ascii','replace')
			s = s.encode('ascii','replace')		# force to ASCII for the Teletype
			if waiting :						# if was waiting
				tty.doprint("\n\a")				# wake up, ring bell
				waiting = False					# we have a story to print
			#	Print title if it changed
			if title != feed.getlasttitleprinted() :
				title = baudottty.convertnonbaudot(title)	# convert special chars to plausible equivalents
				title = baudottty.wordwrap(title)			# word wrap
				feed.setlasttitleprinted(title)	# save new title
				if ui.verbose :
					print("Source: " + title)
				tty.doprint(title + '\n')		# print title
			s = baudottty.convertnonbaudot(s)	# convert special chars to plausible equivalents
			s = baudottty.wordwrap(s)			# word wrap
			if ui.verbose :
				print("Printing news story: %s..." % (s[:40],))	# print a bit of the new story
			tty.doprint(s)
			if not title.startswith("ERROR") :	# if no error, get next story immediately
				continue						# try to get next story
		if repeat :								# poll for new news if requested
			if not waiting :
				tty.doprint("WAITING FOR NEWS...")	# indicate wait
				time.sleep(4)					# ***TEMP*** allow time for final output
				tty.motor(False)				# turn motor off
				waiting = True					# waiting with motor off
				feed.setlasttitleprinted(None)	# forget last title printed; print new title on wakeup
				if ui.verbose :
					print("No new news, waiting...")
			for i in range(30) :				# wait for keyboard interrupt
				if tty.kybdinterrupt :			# if interrupted by BREAK
					tty.doprint("\n??? BREAK ???\n")	# wake up and print
					return						# done
				time.sleep(1)					# wait 1 sec

#
#	testweather
#
def testweather(ui) :
	s = weatherreport.getweatherreport("ca","san_francisco")
	s = baudottty.convertnonbaudot(s)	# convert special chars to plausible equivalents
	s = baudottty.wordwrap(s)			# word wrap
	ui.tty.doprint(s)
	ui.tty.doprint("\n\a")	
#
#	testsend  -- test sending
#
re1 = re.compile(r'\D')					# recognize non-digits
#
def testsend(ui) :
	tty = ui.tty
	apikey = ui.ohdontforgetkey						# API key for sending
	if apikey is None :
		tty.doprint("\a" + "NO MESSAGING ACCOUNT, CANNOT SEND." + '\n')		# print reply
		return										# can't do that
	numchars = ['0','1','2','3','4','5','6','7','8','9','0','.','-']	# acceptable in phone number
	sendto = ui.prompt("To No.: ",numchars,25)
	if sendto is None :								# if no message
		return										# ignore
	sendto = re1.sub('',sendto)						# remove any non-digit chars
	if len(sendto) < 7 :							# if too short
		return										# ignore
	sendtext = None									# no text yet
	while True :									# accumulate text
		s = ui.prompt(": ",None,70)					# get text line
		if s is None :								# if no message
			return
		if s == '' :								# if blank line
			break									# done
		if sendtext is None  :						# if first line
			sendtext = s							# now we have a string
		else :
			sendtext += '\n' + s						# accum lines
	if sendtext is None :							# if nothing to send
		return
	if ui.verbose :									# if printing
		print("Sending to %s: %s" % (sendto, sendtext))	# ***TEMP***
	sender = smssend.SMSsendOhDontForget(apikey)	# only way to send for now
	sendfrom = "Aetheric Message Machine"			# Temp dummy reply address
	reply = sender.send(sendtext,sendto,sendtext)	# send message via SMS
	tty.doprint("\n" + unicode(reply) + '\n')		# print reply	


#
#	Very simple user interface for testing.
#
#
#	uireadtask -- task to read from serial port
#
class uireadtask(threading.Thread) :

	instate = (PRINTING, FLUSHING, READING)	= range(3)		# input state
	inidlesecs = 0.3										# 500ms of idle means flushing is done

	def __init__(self, owner) :
		threading.Thread.__init__(self)						# initialize base class
		self.owner = owner									# BaudotTTY object to use
		self.instate = self.PRINTING						# initially in PRINTING state
		self.statelock = threading.Lock()					# lock on read state
		self.lastread = time.clock()						# time last char read

	#
	#	Read thread.  Stops anything else going on, echoes input.
	#
	#	Nulls are not echoed, because two nulls will trip the "Send/Receive" lever to "Receive",
	#	and we use NULL for a backspace key.
	#
	def run(self) :											# the thread
		tty = self.owner.tty								# the TTY object
		verbose = self.owner.verbose						# verbosity
		halfduplex = self.owner.halfduplex					# true if half duplex
		if halfduplex :										# in half duplex
			shift = tty.outputshift							# get shift from output side to start.
		while True :
			s = tty.readbaudot()							# get some input
			for b in s :
				istate = self.flushcheck()					# do flushing check
				if istate != self.READING :					# if not reading
					if b == '\0' :							# if received a NULL when not reading
						if verbose :
							print("BREAK detected")			# treat as a break
						tty.flushOutput()					# Flush whatever was printing
						break								# ignore remaining input
					else :									# non-break while printing
						continue							# usually means half-duplex echoing back
				if b == '\0' :								# if null
					shift = tty.outputshift					# don't echo, use old shift state
				else :										# otherwise echo
					if halfduplex :
						#	Update shift in half duplex.  This needs to be synched better between input and output.
						if b == baudot.Baudot.LTRS :		# if LTRS
							shift = baudot.Baudot.LTRS		# now in LTRS
						elif b == baudot.Baudot.FIGS :		# if FIGS
							shift = baudot.Baudot.FIGS		# now in FIGS
					else :
						shift = tty.writebaudotch(b, None)	# write to tty
				ch = tty.conv.chToASCII(b, shift)			# convert to ASCII
				if verbose :
					print("Read %s" % (repr(ch),))			# ***TEMP***
				if not (b in [baudot.Baudot.LTRS, baudot.Baudot.FIGS]) : # don't send shifts in ASCII
					self.owner.inqueue.put(ch)				# send character to input

	def acceptinginput(self, ifreading) :					# is somebody paying attention to the input?
		with self.statelock :								# lock
			if ifreading :									# if switching to reading
				if self.instate == self.PRINTING :			# if in PRINTING state
					self.instate = self.FLUSHING			# go to FLUSHING state
					if self.owner.verbose :
						print("Start flushing input.")		# Input now being ignored, to allow half duplex.
			else :											# if switching to writing
				self.instate = self.PRINTING				# back to PRINTING state

	def flushcheck(self) :									# for half duplex, note when output has flushed
		now = time.clock()									# time we read this character
		with self.statelock :
			if self.instate == self.FLUSHING :				# if in FLUSHING state
				if now - self.lastread > self.inidlesecs :	# if no input for quiet period
					self.instate = self.READING 			# go to READING state
					if self.owner.verbose :
						print("Stop flushing input.")		# will start paying attention to input again.
			self.lastread = now								# update timestamp
		return(self.instate)								# return input state

#
#	Class simpleui  -- simple user interface for news, weather, etc.
#
class simpleui(object) :

	kidletimeout = 30										# seconds to wait before powerdown
	kextraltrs = 2											# send two LTRS at end of line.

	def __init__(self, newsfeeds, port, baud, lf, keyboard, halfduplex, ohdontforgetkey = None, verbose = False) :
		self.verbose = verbose								# set verbose mode
		self.tty = baudottty.BaudotTTY()					# get a TTY object
		self.uilock = threading.Lock()						# lock object
		self.inqueue = Queue.Queue()						# input queue
		self.readtask = uireadtask(self)					# input task
		self.port = port									# set port ID
		self.baud = baud									# set baud rate
		self.lf = lf										# line feeds to send
		self.keyboard = keyboard							# true if keyboard present
		self.halfduplex = halfduplex						# true if half-duplex (don't echo)
		self.ohdontforgetkey = ohdontforgetkey				# key for OhDontForget SMS sending
		self.newsfeeds = newsfeeds							# URL list from which to obtain news via RSS
		self.feed = newsfeed.Newsfeeds(self.newsfeeds, self.verbose)	# create a news feed object 


	def draininput(self) :									# consume any queued input
		try: 
			while True :
				ch = self.inqueue.get_nowait()				# get input, if any
		except Queue.Empty:									# if empty
			return											# done

	def waitforbreak(self) :								# wait for a BREAK, with motor off
		self.tty.doprint("\nOFF.\n")						# indicate turn off
		self.readtask.acceptinginput(True)					# accepting input, so we get BREAK chars
		time.sleep(3)										# finish printing.
		self.tty.motor(0)									# turn motor off
		self.draininput()									# drain input
		ch = self.inqueue.get()								# wait for input, any input
		self.tty.motor(1)									# turn motor on
		self.tty.doprint("\n")								# send CR to wake up

	def prompt(self, s, acceptset , maxchars = 1, timeout = None) :			# prompt and read reply
		shift = baudot.Baudot.LTRS							# assume LTRS shift
		if acceptset and len(acceptset) > 0 and acceptset[0].isdigit() :	# if input demands numbers
			shift = baudot.Baudot.FIGS						# put machine in FIGS shift for prompt
		instr = ''											# input string
		while True: 
			try: 
				self.tty.doprint(s)							# output prompt
				self.tty.writebaudotch(shift,None)			# get into appropriate shift
				self.draininput()							# drain any input
				self.readtask.acceptinginput(True)			# now accepting input
				while True :								# accumulate input
					if len(instr) >= maxchars :				# if accumulated enough
						break								# return string
					ch = self.inqueue.get(True, timeout)	# get incoming char (ASCII)
					if ch == '\r' :							# if end of line
						break								# done, return input string
					elif ch == '\0' :						# if the "delete char" (the blank key)
						if len(instr) > 0 :					# if have some chars
							lastch = instr[-1]				# last char to be deleted
							instr = instr[:-1]				# delete last char
							self.tty.doprint("/" + lastch)	# show deletion as "/x"
						else :								# del to beginning of line
							instr = None					# no string, done
							break							# quit reading
					elif acceptset and not (ch in acceptset) :	# if unacceptable
						self.tty.doprint("/" + ch + "\a")	# show deletion, ring bell
						self.tty.writebaudotch(shift,None)	# get back into appropriate shift
					else :									# normal case
						instr += ch							# add to string
					continue								# try again
				self.readtask.acceptinginput(False)			# no longer accepting input
				return(instr)								# return string

			except Queue.Empty:								# if timeout
				self.readtask.acceptinginput(False)			# no longer accepting input
				raise										# reraise Empty

			except KeyboardInterrupt as message :			# if aborted by BREAK
				print("Exception: " + str(message))
				self.tty.doprint("\n...BREAK...\n\n")		# show BREAK
				self.readtask.acceptinginput(False)			# no longer accepting input
				return(None)								# prompt failed


	def endabort(self) :									# end any output abort
		try :
			self.tty.doprint('')							# print nothing to absorb abort event
		except KeyboardInterrupt as message :				# if aborted
			pass											# ignore

		
	def runui(self, initialcmd = None) :
		self.tty.open(self.port, self.baud)					# initialize a TTY on indicated port
		self.tty.eolsettings(self.lf, self.kextraltrs)		# set end of line defaults
		if self.keyboard :									# if keyboard present
			self.readtask.start()							# start reading from it
		else :												# if no keyboard
			if initialcmd is None :							# if no initial command
				initialcmd = "N"							# read news, forever.
		if self.verbose :									# if debug output desired
			print("Serial port: " + repr(self.tty.ser))		# print serial port settings
		while True :
			try: 
				self.endabort()								# end abort if necessary
				self.draininput()							# use up any queued input
				try :
					if initialcmd :							# initial command avilable
						cmd = initialcmd					# use as first command
						initialcmd = None					# use it up
					else :									# otherwise prompt.
						cmd = self.prompt("\nType N for news, U for news updates, W for weather, S to send: ",['N','W','S','U'],
							1,simpleui.kidletimeout)
				except Queue.Empty :						# if no-input timeout
					self.waitforbreak()						# shut down and wait for a BREAK
					continue								# and prompt again
					
				if self.verbose :
					print("Command: %s" % (repr(cmd,)))		# done
				if cmd == 'N' :
					self.tty.doprint('\n\n')
					testnews(self, self.feed, True)			# type news
				elif cmd == 'W' :
					self.tty.doprint('\n\n')
					testweather(self)						# type weather
				elif cmd == 'S' :
					self.tty.doprint('\n')
					testsend(self)							# send something
				elif cmd == 'U' :							# News updates, without old news
					self.markallasread()					# mark all stories as read
					self.tty.doprint('\nAll old news was discarded.\n')
					testnews(self, self.feed, True)			# type news
				else:
					continue								# ask again

			except KeyboardInterrupt as message :			# if aborted
				if self.verbose :
					print("Exception: " + str(message))
				self.tty.doprint("\n*** BREAK ***\n\n")		# show BREAK
				continue									# ask again

	def markallasread(self) :								# mark all sources as read, only show new updates
		self.feed.markallasread()							# mark all stories as read
										

#
#	Main program
#
def main() :
	#	Handle command line options
	opts = optparse.OptionParser()							# get option parse
	opts.add_option('-v','--verbose', help="Verbose mode", action="store_true", default=False, dest="verbose")
	####opts.add_option('-n','--notty', help="Run without Teletype hardware", action="store_false", default=False, dest="notty")
	opts.add_option('-k','--keyboard', help="Keyboard present", action="store_true", default=False, dest="keyboard")
	opts.add_option('-x','--halfduplex', help="Half-duplex (\"loop\")", action="store_true", default=False, dest="halfduplex")
	opts.add_option('-c','--cmd', help="Initial command",dest="cmd",metavar="COMMAND")
	opts.add_option('-m','--markread', help="Mark all stories as read", action="store_true", default=False, dest="markread")
	opts.add_option('-b','--baud', help="Baud rate", dest="baud", default=45.45, metavar="BAUD")
	opts.add_option('-p','--port', help="Port number (0=COM1)", dest="port", default=0, metavar="PORT")
	opts.add_option('-l','--lf', help="Send LF at end of line", action="store_true", dest="lf", default=False)
	opts.add_option('-a','--ohdontforgetkey', help="API key for OhDontForget messaging", dest="ohdontforgetkey", default=None, metavar="OHDONTFORGETKEY")
	(options, args) = opts.parse_args()						# get options
	verbose = options.verbose								# verbose unless turned off
	keyboard = options.keyboard								# true if no keyboard present
	baud = options.baud										# baud rate
	port = options.port										# port number (0=COM1)
	lf = options.lf											# line feeds to send
	if len(args) > 0 :										# if given list of feeds
		feedurls = args										# use feed list	
	else :													# if nothing specified
		feedurls = defaultfeedurls							# use default feed URLs					
	if verbose :
		print("Verbose mode.\nOptions: " + repr(options))
		print("Args: " + repr(args))						# ***TEMP***
		print("News feeds: %s" % (repr(feedurls),))			# list of news feeds
		print("Using port %d at %s baud." % (port, str(baud)))	# port and speed info
		if keyboard :
			print("Accepting commands from Teletype keyboard")
		else :
			print("No keyboard present; will print latest news.")
	ui = simpleui(feedurls, port, baud, lf, keyboard, options.halfduplex, options.ohdontforgetkey, verbose)
	if options.markread :
		ui.markallasread()									# if requested, mark all news as read
	ui.runui(options.cmd)									# run the test

main()

