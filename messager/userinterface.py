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
import sys
assert(sys.version_info >= (2,6))			# Requires Python 2.6 or later.
sys.path.append("./googlevoice")			# for SMS access
import serial								# PySerial
import baudot								# baudot charset info
import threading
import baudottty
import weatherreport						# weather report
import newsfeed
import smsfeed
import feedmanager
import time
import re
import Queue
import optparse
import traceback

#
#	Globals
#
reutersfeedurl = "http://feeds.reuters.com/reuters/topNews?format=xml"	# news feed as XML
wpostfeedurl = "http://feeds.washingtonpost.com/wp-dyn/rss/business/index_xml"
defaultfeedurls = [reutersfeedurl]								# default feeds to use

klongprompt =	"\nType N for news, W for weather, S to send, O for off, CR to wait: "
kshortprompt =	"\nN, W, S, O, or CR: "
kerrbells = "\a \a \a"								# ring 3 slow bells on error
kreadtimeout = 1.0									# read timeout - makes read abort (control-C) work on Linux.


#
#	printweather
#
def printweather(ui) :
	s = weatherreport.getweatherreport("ca","san_francisco")
	s = baudottty.convertnonbaudot(s)	# convert special chars to plausible equivalents
	s = baudottty.wordwrap(s)			# word wrap
	ui.tty.doprint(s)
	ui.tty.doprint("\n\n\n")
#
#	formatforsms  -- format text with SMS conventions.
#
#	Upper case first letter, and first letter after each period or question mark
#
def formatforsms(s) :
	uc = True							# Upper case if on
	out = ""							# accum output string here
	for ch in s :						# for all chars
		if ch in [".", "!", "?"] :		# These characters force upper case.
			uc = True
		elif uc and not ch.isspace() :	# if upper case mode and not space
			ch = ch.upper()				# make upper case
			uc = False					# once only
		else :
			ch = ch.lower()				# otherwise lower case
		out += ch
	return(out)
#
#	sendviasms  -- test sending
#
re1 = re.compile(r'\D')					# recognize non-digits
#
def sendviasms(ui) :
	tty = ui.tty
	if ui.smsmsgfeed is None :
		tty.doprint("\a" + "NO MESSAGING ACCOUNT, CANNOT SEND." + '\n')		# print reply
		return										# can't do that
	numchars = ['0','1','2','3','4','5','6','7','8','9','0','.','-']	# acceptable in phone number
	sendto = ui.prompt("To No.: ",numchars,25)
	if sendto is None :								# if no message
		return										# ignore
	#	Check for reply to number from previous message
	if len(sendto) == 1 and sendto[0] in ['.','-'] : 
		if ui.smsmsgfeed.msgfrom : 
			sendto = ui.smsmsgfeed.msgfrom			# use previous number
			tty.doprint("To No.: " + sendto + "\n")	# show number being sent to
		else :
			tty.doprint("\aThere is no message to which to reply.\n")
			return
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
	sendtext = formatforsms(sendtext)				# apply upper/lower case SMS conventions
	if ui.verbose :									# if printing
		print("Sending to %s: %s" % (sendto, sendtext))	# ***TEMP***
	reply = ui.smsmsgfeed.sendSMS(sendto, sendtext)
	if reply is None :								# if no error
		reply = "DONE"								# although Google Voice says OK even when number not validated
	tty.doprint("\n" + unicode(reply) + '\n')		# print reply	


#
#	Very simple user interface for testing.
#
#
#	uireadtask -- task to read from serial port
#
class uireadtask(threading.Thread) :

	instate = (PRINTING, FLUSHING, READING) = range(3)		# input state
	inidlesecs = 0.3										# 500ms of idle means flushing is done
	#
	#	Called from outside the thread
	#

	def __init__(self, owner) :
		threading.Thread.__init__(self)						# initialize base class
		self.owner = owner									# BaudotTTY object to use
		self.instate = self.PRINTING						# initially in PRINTING state
		self.aborting = False								# external request to terminate
		self.statelock = threading.Lock()					# lock on read state
		self.lastread = time.time()							# time last char read

	def abort(self) :										# terminate this task
		if not self.is_alive() :							# if not started
			return											# no problem.
		self.aborting = True								# abort this task at next read timeout
		self.join(10.0)										# wait for thread to finish
		if self.is_alive() :
			raise RuntimeError("INTERNAL ERROR: read thread will not terminate.  Kill program.")

	#
	#	Called from within the thread.
	#

	#
	#	Read thread.  Stops anything else going on, echoes input.
	#
	#	Nulls are not echoed, because two nulls will trip the "Send/Receive" lever to "Receive",
	#	and we use NULL for a backspace key.
	#
	def run(self) :
		try :
			self.dorun()									# do run thread
		except Exception as message :						# trouble
			print("Internal error in read thread: " + str(message))
			traceback.print_exc()							# traceback
			sys.exit()										# fails ***TEMP*** need to abort main thread

	def dorun(self) :										# the thread
		tty = self.owner.tty								# the TTY object
		verbose = self.owner.verbose						# verbosity
		halfduplex = self.owner.halfduplex					# true if half duplex
		if halfduplex :										# in half duplex
			shift = tty.outputshift							# get shift from output side to start.
		while not self.aborting :							# until told to stop
			s = tty.readbaudot()							# get some input
			if len(s) == 0 :								# timeout
				continue									# do nothing
			for b in s :
				istate = self.flushcheck()					# do flushing check
				if istate != self.READING :					# if not reading
					if b == '\0' :							# if received a NULL when not reading
						if verbose :
							print("BREAK detected")			# treat as a break
						tty.flushOutput()					# Flush whatever was printing
						break								# ignore remaining input
					else :									# non-break while printing
						if verbose :						# note ignoring
							print("Ignoring input.")
						continue							# usually means half-duplex echoing back
				shift = tty.writebaudotch(None, None)		# get current shift state
				if shift is None :							# if none
					shift = baudot.Baudot.LTRS				# assume LTRS
				if not (b in ['\0',baudot.Baudot.LF]) :		# if not (null or LF), echo char.
					if halfduplex :
						#	Update shift in half duplex.  This needs to be synched better between input and output.
						if b == baudot.Baudot.LTRS :		# if LTRS
							shift = baudot.Baudot.LTRS		# now in LTRS
						elif b == baudot.Baudot.FIGS :		# if FIGS
							shift = baudot.Baudot.FIGS		# now in FIGS
					else :
						shift = tty.writebaudotch(b, shift)	# write to tty in indicated shift state
				ch = tty.conv.chToASCII(b, shift)			# convert to ASCII
				if verbose :
					print("Read %s" % (repr(ch),))			# ***TEMP***
				if not (b in [baudot.Baudot.LTRS, baudot.Baudot.FIGS]) : # don't send shifts in ASCII
					self.owner.inqueue.put(ch)				# send character to input
		#	Terminated
		self.aborting = False								# done, reset termination

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
		now = time.time()									# time we read this character
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

	def __init__(self, newsfeeds, port, baud, lf, keyboard, halfduplex, guser, gpass, workdir = ".", verbose = False) :
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
		self.guser = guser									# Google Voice user name
		self.gpass = gpass									# Google Voice password
		self.newsfeeds = newsfeeds							# URL list from which to obtain news via RSS
		self.workdir = workdir								# store persistent state here 
		self.smsmsgfeed = None								# no SMS msg feed yet
		self.itemprinting = None							# ID of what's currently being printed
		self.feeds = feedmanager.Feeds(self.verbose)		# create a news feed object 
		for url in newsfeeds :								# for URLs listed
			self.feeds.addfeed(newsfeed.Newsfeed(url, self.verbose))
		if guser :											# if have Google Voice account
			self.smsmsgfeed = smsfeed.SMSfeed(guser, gpass, self.workdir, self.verbose)	# get a SMS feed object
			self.feeds.addfeed(self.smsmsgfeed)				# make this feed active

	def draininput(self) :									# consume any queued input
		try: 
			while True :
				ch = self.inqueue.get_nowait()				# get input, if any
		except Queue.Empty:									# if empty
			return											# done

	def waitforbreak(self) :								# wait for a BREAK, with motor off
		self.tty.doprint("\nOFF.\n")						# indicate turn off
		self.readtask.acceptinginput(True)					# accepting input, so we get BREAK chars
		while self.tty.outwaiting() > 0 :					# wait for printing to finish
			time.sleep(1.0)									# finish printing.
		self.tty.motor(False)								# turn motor off
		self.draininput()									# drain input
		ch = self.inqueue.get()								# wait for input, any input
		self.tty.doprint("\n")								# send CR to turn on motor and wake up

	#
	#	waitfortraffic  -- normal loop, waiting for something to come in.
	#
	def waitfortraffic(self, feed) :
		waiting = False
		feed.setlasttitleprinted(None)						# forget last title printed; print new title on wakeup
		tty = self.tty										# the teletype to print to
		while True :										# read repeatedly - one story per iteration
			if not self.itemprinting :						# if no unprinted item pending
				self.itemprinting = feed.getitem()			# get a new news item
			if self.itemprinting :							# if something to print
				title = self.itemprinting.gettitle()		# get title
				s = self.itemprinting.formattext()			# item text
				errmsg = self.itemprinting.errmsg			# error message if any
				title = title.encode('ascii','replace')
				s = s.encode('ascii','replace')				# force to ASCII for the Teletype
				if waiting :								# if was waiting
					tty.doprint("\n\a")						# wake up, ring bell
					waiting = False							# we have a story to print
					powerdownstart = None					# not waiting for motor power off
				#	Print title if it changed
				if title != feed.getlasttitleprinted() :
					feed.setlasttitleprinted(title)	# save new title so we can tell if it changed
					title = baudottty.convertnonbaudot(title)	# convert special chars to plausible equivalents
					title = baudottty.wordwrap(title)		# word wrap
					if self.verbose :
						print("Source: " + title)
					tty.doprint(title )						# print title
					if errmsg :
						tty.doprint(kerrbells)				# ring bells here
					tty.doprint('\n')						# end title line
				s = baudottty.convertnonbaudot(s)			# convert special chars to plausible equivalents
				s = baudottty.wordwrap(s)					# word wrap
				if s[-1] != '\n' :							# end with NL
					s += '\n'
				if self.verbose :
					ssum = re.sub("\s+"," ", self.itemprinting.summarytext()).lstrip()[:80]	# summarize story/msg by truncation
					print("Printing: %s..." % (ssum,))		# print a bit of the new story
				tty.doprint(s)								# print item
				self.itemprinting.itemdone()				# mark item as done
				self.itemprinting = None					# item has been used up
				if errmsg is None :							# if no error, get next story immediately
					continue								# try to get next story
			#	No traffic, wait for more to come in
			if not waiting :
				tty.doprint("WAITING...")					# indicate wait
				waiting = True								# waiting with motor off
				feed.setlasttitleprinted(None)				# forget last title printed; print new title on wakeup
				if self.verbose :
					print("No traffic, waiting...")
			if tty.kybdinterrupt :							# if interrupted by BREAK, but not printing
				if self.verbose :
					print("Keyboard interrupt")
				return										# done
			#	Turn off motor after allowing enough time for all queued output.
			#	The USB serial devices have a huge queue.  We have to wait for it to empty.
			if tty.motorison() :							# if motor running
				charsleft = tty.outwaiting()				# get chars left to print
				####print("Queued: %d" % (charsleft,))		# ***TEMP***
				if charsleft <= 0 :							# if done printing
					tty.motor(False)						# turn off Teletype motor
					if self.verbose :							# if enough time has elapsed for worst-case queued printing
						print("Motor turned off.")
			time.sleep(1)									# wait 1 sec for next cycle


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
					if timeout :
						timeout = timeout + self.tty.outwaitingtime()	# add extra time for printing in progress
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

			except baudottty.BaudotKeyboardInterrupt as message :	# if aborted by BREAK
				print("Break: " + str(message))
				self.tty.doprint("\n...CANCELLED...\n\n")	# input cancelled
				self.readtask.acceptinginput(False)			# no longer accepting input
				return(None)								# prompt failed


	def endabort(self, msg="") :							# end any output abort
		try :
			self.tty.doprint(msg)							# print nothing to absorb abort event
		except baudottty.BaudotKeyboardInterrupt as message :	# if aborted
			pass											# ignore

		
	def uiloop(self, initialcmd = None) :
		useshortprompt = False								# use long prompt the first time
		while True :
			try: 
				self.endabort()								# end abort if necessary
				self.draininput()							# use up any queued input
				try :
					if initialcmd :							# initial command avilable
						cmd = initialcmd					# use as first command
						initialcmd = None					# use it up
					else :									# otherwise prompt.
						promptmsg = kshortprompt			# short prompt is abbreviated
						if not useshortprompt :				# use it unless there was an error
							promptmsg = klongprompt			# print the long prompt this time
							useshortprompt = True			# and the short prompt next time.
						cmd = self.prompt(promptmsg ,		# prompt for input
							['N','W','S','O'],
							1,simpleui.kidletimeout)
				except Queue.Empty :						# if no-input timeout
					self.tty.doprint('\n')
					self.waitfortraffic(self.feeds)			# wait for traffic				
					continue								# and prompt again
				#	Read a one-letter command.  Handle it.	
				if self.verbose :
					print("Command: %s" % (repr(cmd,)))		# done
				if cmd == 'N' :
					self.tty.doprint('\n\n')
					self.feeds.unmarkallasread("NEWS")		# unmark all news, forcing a new display
					self.waitfortraffic(self.feeds)			# type news
				elif cmd == 'W' :
					self.tty.doprint('\n\n')
					printweather(self)						# type weather
				elif cmd == 'S' :
					self.tty.doprint('\n')
					sendviasms(self)						# send something
				elif cmd == 'O' :							# Turn off
					self.feeds.markallasread("NEWS")		# mark all stories as read
					self.waitforbreak()
					continue
				elif cmd == '' :							# plain return
					self.waitfortraffic(self.feeds)		# wait for traffic				
				else:										# bogus entry
					useshortprompt = False					# print the long prompt
					continue								# ask again

			except baudottty.BaudotKeyboardInterrupt as message :	# if aborted
				if self.verbose :
					print("Break: " + str(message))
				self.endabort("\n\n")						# show BREAK, ignoring break within break
				continue									# ask again

	def runui(self, initialcmd = None) :
		try :
			self.tty.open(self.port, self.baud, kreadtimeout)	# initialize a TTY on indicated port
			self.tty.eolsettings(self.lf, self.kextraltrs)		# set end of line defaults
			if self.keyboard :									# if keyboard present
				self.readtask.start()							# start reading from it
			else :												# if no keyboard
				if initialcmd is None :							# if no initial command
					initialcmd = "N"							# read news, forever.
			if self.verbose :									# if debug output desired
				print("Serial port: " + repr(self.tty.ser))		# print serial port settings
			self.uiloop(initialcmd)								# run main UI loop
		except (KeyboardInterrupt, StandardError) as message :	# if trouble
			print("Internal error, aborting: " + str(message))
			#	Abort feed tasks
			self.feeds.abort()									# abort all feed tasks
			#	Abort read task.
			if self.keyboard :									# if have a read task
				if self.verbose :
					print("Waiting for read task to complete.")
				self.readtask.abort()							# abort reading over at read task
				if self.verbose :
					print("Read task has completed.")
			raise												# re-raise exception with other thread exited.
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
	####opts.add_option('-m','--markread', help="Mark all stories as read", action="store_true", default=False, dest="markread")
	opts.add_option('-b','--baud', help="Baud rate", dest="baud", default=45.45, metavar="BAUD")
	opts.add_option('-p','--port', help="Port number (0=COM1)", dest="port", default="0", metavar="PORT")
	opts.add_option('-l','--lf', help="Send LF at end of line", action="store_true", dest="lf", default=False)
	opts.add_option('-u','--username', help="Google Voice user name", dest="guser", default=None, metavar="GUSER")
	opts.add_option('-w','--password', help="Google Voice password", dest="gpass", default=None, metavar="GPASS")
	opts.add_option('-d','--workdir', help="Directory for persistent state", dest="workdir", default='.', metavar="WORKDIR")
	####opts.add_option('-a','--ohdontforgetkey', help="API key for OhDontForget messaging", dest="ohdontforgetkey", default=None, metavar="OHDONTFORGETKEY")
	(options, args) = opts.parse_args()						# get options
	verbose = options.verbose								# verbose unless turned off
	keyboard = options.keyboard								# true if no keyboard present
	baud = options.baud										# baud rate
	if options.port.isdigit() :
		port = int(options.port)							# is port number (0=COM1)
	else:
		port = options.port									# is device name, "/dev/something"
	lf = options.lf											# line feeds to send
	if len(args) > 0 :										# if given list of feeds
		feedurls = args										# use feed list	
	else :													# if nothing specified
		feedurls = defaultfeedurls							# use default feed URLs					
	if verbose :
		print("Verbose mode.\nOptions: " + repr(options))
		print("Args: " + repr(args))						# ***TEMP***
		print("News feeds: %s" % (repr(feedurls),))			# list of news feeds
		print("Using port %s at %s baud." % (port, str(baud)))	# port and speed info
		if keyboard :
			print("Accepting commands from Teletype keyboard")
		else :
			print("No keyboard present; will print latest news.")
	ui = simpleui(feedurls, port, baud, lf, keyboard, options.halfduplex, 
		options.guser, options.gpass, options.workdir, verbose)
	ui.feeds.markallasread("NEWS")							# mark all news as read
	ui.runui(options.cmd)									# run the test

main()

