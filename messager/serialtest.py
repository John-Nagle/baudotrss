#
#	Python test for Baudot teletype via serial port.
#
#	Python 2.6 or later.
#
#	John Nagle
#	February, 2009
#
import serial								# PySerial
import pyserialpatches
import baudot								# baudot charset info
import threading
import baudottty
import weatherreport						# weather report
import newsfeed
import time
import Queue
	
#
#	readtask -- task to read from serial port
#
class readtask(threading.Thread) :
	def __init__(self, tty) :
		threading.Thread.__init__(self)	# initialize base class
		self.tty = tty					# BaudotTTY object to use

	#
	#	Dummy test thread.  Stops anything else going on, echoes input.
	#
	def run(self) :						# the thread
		aborted = False					# if haven't aborted yet.
		while True :
			s = self.tty.readbaudot()						# get some input
			if not aborted :
				self.tty.flushOutput()						# Flush whatever was printing
				aborted = True
			for b in s :
				shift = self.tty.writebaudotch(b, None)		# write to tty
				ch = self.tty.conv.chToASCII(b, shift)		# convert to ASCII
				print("Read %s" % (repr(ch),))				# ***TEMP***

				
							
#
#	test1  -- basic test
#
def test1() :
	tty = baudottty.BaudotTTY()			# 
	tty.open(0)							# initialize a TTY on COM1
	for n in range(3) :
		tty.doprint("The Quick Brown Fox Jumps Over the Lazy Dogs. (0123456780) @%^&* \n")	# send msg
	tty.doprint("\a")					# ring bell at end
	

#
#	Listen and print hex
#
def startlisten(tty) :
	intask = readtask(tty)				# establish read tast
	intask.start()						# start read task
#
#	testnews
#
def testnews(tty) :
	newsurl = "http://feeds.reuters.com/reuters/topNews?format=xml"	# news feed as XML
	s = newsfeed.getnewsfeed(newsurl)
	s = baudottty.convertnonbaudot(s)	# convert special chars to plausible equivalents
	s = baudottty.wordwrap(s)			# word wrap
	tty.doprint(s)
	tty.doprint("\n\a")
#
#	testweather
#
def testweather(tty) :
	s = weatherreport.getweatherreport("ca","san_francisco")
	s = baudottty.convertnonbaudot(s)	# convert special chars to plausible equivalents
	s = baudottty.wordwrap(s)			# word wrap
	tty.doprint(s)
	tty.doprint("\n\a")	
#
#	testsend  -- test sending
#
def testsend(ui) :
	tty = ui.tty
	numchars = ['0','1','2','3','4','5','6','7','8','9','0','.','-']	# acceptable in phone number
	sendto = ui.prompt("To No.: ",numchars,25)
	if sendto is None :					# if no message
		return
	sendtext = ''						# no text yet
	while True :						# accumulate text
		s = ui.prompt(": ",None,70)		# get text line
		if s is None :					# if no message
			return
		if s == '' :					# if blank line
			break						# done
		sendtext += s + '\n'			# accum lines
	print("Sending to %s: %s" % (sendto, sendtext))	# ***TEMP***
	tty.doprint("...\n\n")				# ***TEMP***	

#
#	testreport  --  print the usual report
#
#	Stops if aborted.
#
def testreport(tty) :
	try :
		testnews(tty)
		testweather(tty)
	except KeyboardInterrupt, message :		# if aborted
		tty.doprint('\n\n' + str(message) + '\n\n\a')		# so note	

#
def testall() :
	tty = baudottty.BaudotTTY()			# 
	tty.open(0)							# initialize a TTY on COM1
	startlisten(tty)						# start up listener
	testreport(tty)

#
#	Very simple user interface for testing.
#
#
#	uireadtask -- task to read from serial port
#
class uireadtask(threading.Thread) :
	def __init__(self, owner) :
		threading.Thread.__init__(self)						# initialize base class
		self.owner = owner									# BaudotTTY object to use

	#
	#	Read thread.  Stops anything else going on, echoes input.
	#
	def run(self) :											# the thread
		aborted = False										# if haven't aborted yet.
		tty = self.owner.tty								# the TTY object

		while True :
			s = tty.readbaudot()							# get some input
			if s == '\0' :									# if break
				print("Flush output")
				tty.flushOutput()							# Flush whatever was printing
				aborted = True
			for b in s :
				shift = tty.writebaudotch(b, None)			# write to tty
				ch = tty.conv.chToASCII(b, shift)			# convert to ASCII
				print("Read %s" % (repr(ch),))				# ***TEMP***
				self.owner.inqueue.put(ch)					# send character to input
				aborted = False								# done with abort

#
#	Class simpleui  -- simple user interface for news, weather, etc.
#
class simpleui(object) :
	def __init__(self) :
		self.tty = baudottty.BaudotTTY()					# get a TTY object
		self.uilock = threading.Lock()						# lock object
		self.inqueue = Queue.Queue()						# input queue
		self.readtask = uireadtask(self)					# input task

	def draininput(self) :									# consume any queued input
		try: 
			while True :
				ch = self.inqueue.get_nowait()				# get input, if any
		except Queue.Empty:									# if empty
			return											# done

	def prompt(self, s, acceptset , maxchars = 1) :			# prompt and read reply
		shift = baudot.Baudot.LTRS							# assume LTRS shift
		if acceptset and len(acceptset) > 0 and acceptset[0].isdigit() :	# if input demands numbers
			shift = baudot.Baudot.FIGS						# put machine in FIGS shift for prompt
		instr = ''											# input string
		while True: 
			try: 
				self.tty.doprint(s)							# output prompt
				self.tty.writebaudotch(shift,None)			# get into appropriate shift
				while True :								# accumulate input
					if len(instr) >= maxchars :				# if accumulated enough
						return(instr)						# return string
					ch = self.inqueue.get()					# get incoming char (ASCII)
					if ch == '\r' :							# if end of line
						return(instr)						# done, return char
					elif ch == '\a' :						# if the "delete char" (BELL for now)
						if len(instr) > 0 :					# if have some chars
							lastch = instr[-1]				# last char to be deleted
							instr = instr[:-1]				# delete last char
							self.tty.doprint("/" + lastch)	# show deletion as "/x"
						else :								# del to beginning of line
							return(None)					# return cancel
					elif acceptset and not (ch in acceptset) :	# if unacceptable
						self.tty.doprint("\a")				# ring bell
					else :									# normal case
						instr += ch							# add to string
					continue								# try again

			except KeyboardInterrupt, message :				# if aborted by BREAK
				print("Exception: " + str(message))
				self.tty.doprint("\n...BREAK...\n\n")		# show BREAK
				return(None)								# prompt failed


	def endabort(self) :									# end any output abort
		try :
			self.tty.doprint('')							# print nothing to absorb abort event
		except KeyboardInterrupt, message :					# if aborted
			pass											# ignore

		
	def runui(self) :
		self.tty.open(0)									# initialize a TTY on COM1
		self.readtask.start()								# start reading
		while True :
			try: 
				self.endabort()								# end abort if necessary
				self.draininput()							# use up any queued input
				cmd = self.prompt("\nType N for news, W for weather, S to send: ",['N','W','S'])
				print("Command: %s" % (repr(cmd,)))			# done
				if cmd == 'N' :
					print("News")
					self.tty.doprint('\n\n')
					testnews(self.tty)						# type news
				elif cmd == 'W' :
					print("Weather")
					self.tty.doprint('\n\n')
					testweather(self.tty)					# type weather
				elif cmd == 'S' :
					print "Send"
					self.tty.doprint('\n')
					testsend(self)							# send something
				else:
					continue								# ask again

			except KeyboardInterrupt, message :				# if aborted
				print("Exception: " + str(message))
				self.tty.doprint("\n*** BREAK ***\n\n")		# show BREAK
				continue									# ask again
											

#
#	Main program
#
def main() :
	ui = simpleui()
	ui.runui()												# run the test

main()

