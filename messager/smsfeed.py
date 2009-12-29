#
#	smsfeed.py  -  fetch SMS messages via Google Voice
#
#	John Nagle
#	November, 2009
#
#	Polls Google Voice storage of SMS messages
#
#	The data returned is pure text, not HTML.  This is intended for
#	applications where the output is a printing device displaying
#	news updates. 
#
#	License: LGPL
#
#
import sys
import googlevoice
import time
import datetime
import httplib
import urllib2
import BeautifulSoup
import feedmanager
import threading
import re
#
#	Temporary patch to "googlevoice".	Adds "recent_html" attribute to "Voice" objects,
#	so we can read recent messages
#
if not "recent" in googlevoice.settings.FEEDS :
	googlevoice.settings.FEEDS = googlevoice.settings.FEEDS + ("recent",)
#
#	Useful regular expressions
#
kremovetrailcolon = re.compile(r':$')						# trailing colon

#
#	extractsms  --  extract SMS messages from BeautifulSoup tree of Google Voice SMS HTML.
#
#	Output is a list of dictionaries, one per message.
#
def extractsms(htmlsms) :
	msgitems = []										# accum message items here
	#	Extract all conversations by searching for a DIV with an ID at top level.
	tree = BeautifulSoup.BeautifulSoup(htmlsms)			# parse HTML into tree
	conversations = tree.findAll("div",attrs={"id" : True},recursive=False)
	for conversation in conversations :
		#	For each conversation, extract each row, which is one SMS message.
		rows = conversation.findAll(attrs={"class" : "gc-message-sms-row"})
		for row in rows :								# for all rows
			#	For each row, which is one message, extract all the fields.
			msgitem = {"id" : conversation["id"]}		# tag this message with conversation ID
			spans = row.findAll("span",attrs={"class" : True}, recursive=False)
			for span in spans :							# for all spans in row
				cl = span["class"]
				msgitem[cl] = (" ".join(span.findAll(text=True))).strip()	# put text in dict
			msgitems.append(msgitem)					# add msg dictionary to list
	return(msgitems)

#
#	class SMSfeed  --  read SMS messages from a Google Voice account.
#
class SMSfeed(feedmanager.Feed) :	

	kreadlistfile = "smsread.txt"						# list of SMS messages already read, as hashes	
	kheadertext = "\n\n\a\n\a- - - THE AETHERIC MESSAGE MACHINE COMPANY, LTD.  - - -"	# printed as header
	kpollinterval = 60.0								# poll this often (seconds)
	kdeleteinterval = 60*60								# delete this often (seconds)
	kdeleteage = 60*60*24								# delete conversation if nothing in this period
					
	#
	#	Called from outside the thread
	#
	def __init__(self, username, password, persistentdir = None, verbose=False) :
		feedmanager.Feed.__init__(self, "SMS", verbose)
		self.lock = threading.Lock()					# lock object.  One login at a time.
		self.username = username
		self.password = password
		self.hashread = {}								# items we've read from Google Voice
		self.hashprinted = {}							# items we've delivered for printing
		self.errmsg = None								# no pending error message
		self.hdrtitle = "Aetheric Message"
		self.voice = None								# no Voice object yet
		self.url = self.hdrtitle
		self.msgfrom = None								# phone number of last message returned to user
		self.hdrtext = self.kheadertext					# default header, can be replaced
		self.persistentdir = persistentdir				# save hashes of already-printed messages
		self.lastdelete = 0.0							# time of last delete cycle
		self.loadhashes()								# load existing hashes

	def itemdone(self, item) :							# item has been printed, mark as done
		#	Update permanent file of messages printed.
		#	This is updated only after the message has been printed, so we don't lose
		#	messages if the program crashes.
		digest = item.digest							# digest done
		if digest is None :								# if no digest (probably error message)
			return										# done
		self.hashprinted[digest] = True					# note as printed
		self.savehashes()								# mark as printed
		self.msgfrom = item.msgfrom						# get From source if any

	def getpollinterval(self) :							# poll this often
		return(self.kpollinterval)

	def markallasread(self) :
		pass											# deliberately not supported for messages

	def unmarkallasread(self) :							# deliberately not supported for messages
		pass

	def formattext(self, msgitem) :						# format a msg item, long form
		emsg = msgitem.errmsg
		#	Format for printing as display message
		if emsg :										# short format for errors
			s = "%s: %s\n" % (msgitem.msgtime, emsg)
			return(s)									# return with error msg
		msgdate = "UNKNOWN"								# date can be None.  Handle.
		if msgitem.msgdate :							# if date present
			msgdate = msgitem.msgdate					# use it
		fmt = "%s\nFROM: %s\nDATE: %s\nTIME: %s\n\n%s\n\n%s"
		trailer =   "- - - END OF MESSAGE - - -\n\n\n\n\n\n\n"
		s = fmt % (self.hdrtext, msgitem.msgfrom, msgitem.msgdate, msgitem.msgtime, msgitem.body, trailer)
		return(s)										# no error

	def summarytext(self, msgitem) :
		emsg = msgitem.errmsg
		#	Format for printing as display message
		if emsg :										# short format for errors
			s = "%s: %s\n" % (msgitem.msgtime, emsg)
			return(s)									# return with error msg
		fmt = "SMS FROM %s  TIME %s: %s"
		s = fmt % (msgitem.msgfrom, msgitem.msgtime, msgitem.body[:40])
		return(s)										# no error

	def sendSMS(self, number, text) :					# sending capability
		"""
		Send SMS message
		"""
		try: 
			voice = self.login()						# get logged in if necessary, will throw if fail
			voice.send_sms(number, text)
			return(None)								# success
		except IOError as message:
			return(self.fetcherror("Input or output error", message))
		except googlevoice.util.ValidationError as message :
			return(self.fetcherror("Reply validation error", message))
		except googlevoice.util.ParsingError as message :
			return(self.fetcherror("Reply parsing error No. 1", message))
		except googlevoice.util.JSONError as message:
			return(self.fetcherror("Reply parsing error No. 2", message))
		except googlevoice.util.DownloadError as message:
			return(self.fetcherror("Down-load error", message))
		except googlevoice.util.LoginError as message :
			return(self.fetcherror("Messaging system does not recognize you", message))


	#	
	#	Called from within the thread
	#

	def getmsgsreadfilename(self) :						# returns name of file for messages read
		if self.persistentdir is None :
			return(None)
		return(self.persistentdir + "/" + self.kreadlistfile)
		
	def loadhashes(self) :								# load hashes from persistent file
		if self.getmsgsreadfilename() is None :
			return
		try :
			fd = open(self.getmsgsreadfilename(),"r")	# get file
			for line in fd.readlines() :				# read all lines
				line = line.strip()						# remove blanks
				if line == "" or line.startswith("#"):	# ignore blank lines and comments
					continue
				self.hashread[line] = True				# we have read this before
				self.hashprinted[line] = True			# we have printed this
			fd.close()
		except IOError:									# no file, no problem.
			return

	def savehashes(self) :
		if self.getmsgsreadfilename() is None :
			return
		try :
			if self.verbose :
				print('Saving IDs of messages read to "%s"' % (self.getmsgsreadfilename(),))
			fd = open(self.getmsgsreadfilename(),"w")	# overwrite file
			fd.write("# Hashes of Google Voice messages already printed.\n")	# identify file for humans
			for line in self.hashprinted.keys() :		# write out items we've printed
				fd.write(str(line) + "\n")
			fd.close()									# 
		except IOError:									# no file, no problem.
			return		

	def gettitle(self) :								# get feed title 
		return(self.hdrtitle)	 


	def login(self) :									# get logged in if necessary
		#	Get logged in, or throw.
		with self.lock :
			if self.voice is None :						# login if necessary
				if self.verbose :
					print("Logging into Google Voice")	# note login
				self.voice = googlevoice.Voice()		# get new voice object
				self.voice.login(self.username, self.password)		# try to login
			assert(self.voice)							# must have voice object at this point
			return(self.voice)							# return a usable voice object

	def logout(self) :
		with self.lock :
			if self.voice :
				try:									# logout can fail
					self.voice.logout()					# logout if necessary
				except:									# ignore logout problems
					pass
			self.voice = None
			
	def fetchitems(self) :								# fetch more items from feed source
		try :
			voice = self.login()						# log in if necessary
			voice.inbox()								# obtain and parse inbox
			htmlsms = voice.inbox.html					# get html from inbox
			####print("htmlsms: " + repr(htmlsms))			# ***TEMP***
			msgs = extractsms(htmlsms)					# parse HTML into more useful form
			#	Extract conversation data, because the HTML data doesn't have all the info.
			convs = {}									# map id -> conversation object
			for conv in voice.inbox.folder.messages :	# for all conversations
				id = conv.id
				convs[id] = conv						# index by ID
			if self.verbose :
				print("%d SMS messages in inbox." % (len(msgs),))	# number in inbox
			for hash in self.hashread.keys() :			# for everything we've read
				self.hashread[hash] = False				# not yet seen on this round
			for msg in msgs :							# for each item
				self.doitem(msg, convs)					# handle it
			#	Purge no-longer-current items from previously seen list
			dellist = []
			for hash in self.hashread.keys() :			# for all in dict
				if not self.hashread[hash] :			# not yet seen on this round
					dellist.append(hash)				# add to to-delete list
			for hash in dellist :						# apply to-delete list to dict
				del(self.hashread[hash])
			#	Purge no-longer-current items from printed list
			dellist = []
			for hash in self.hashprinted.keys() :		# for all in dict
				if not hash in self.hashread :			# not seen on this round
					dellist.append(hash)				# add to to-delete list
			for hash in dellist :						# apply to-delete list to dict
				del(self.hashprinted[hash])
			self.deleteoldmsgs(msgs)					# delete day-old messages on server if indicated

		#	Exception handling
		except AttributeError as message :				# if trouble
			self.logerror(self.fetcherror("Internal error when fetching message", message))
		except IOError as message:
			self.logerror(self.fetcherror("Input or output error", message))
		except googlevoice.util.ValidationError as message :
			self.logerror(self.fetcherror("Reply validation error", message))
		except googlevoice.util.ParsingError as message :
			self.logerror(self.fetcherror("Reply parsing error No. 1", message))
		except googlevoice.util.JSONError as message:
			self.logerror(self.fetcherror("Reply parsing error No. 2", message))
		except googlevoice.util.DownloadError as message:
			self.logerror(self.fetcherror("Down-load error", message))
		except httplib.HTTPException as message:
			self.logerror(self.fetcherror("Reply protocol error (HTTP)", message))
		except urllib2.URLError as message:
			self.logerror(self.fetcherror("Network error", message))
		except googlevoice.util.LoginError as message :
			self.logerror(self.fetcherror("Messaging system does not recognize you", message))

	def fetchconversations(self) :							# fetch SMS conversation folders
		try :
			voice = self.login()							# log in if necessary
			return(voice.sms())								

		#	Exception handling
		except AttributeError as message :				# if trouble
			self.logerror(self.fetcherror("Internal error when fetching message", message))
		except IOError as message:
			self.logerror(self.fetcherror("Input or output error", message))
		except googlevoice.util.ValidationError as message :
			self.logerror(self.fetcherror("Reply validation error", message))
		except googlevoice.util.ParsingError as message :
			self.logerror(self.fetcherror("Reply parsing error No. 1", message))
		except googlevoice.util.JSONError:
			self.logerror(self.fetcherror("Reply parsing error No. 2", message))
		except googlevoice.util.DownloadError as message:
			self.logerror(self.fetcherror("Down-load error", message))
		except httplib.HTTPException as message:
			self.logerror(self.fetcherror("Reply protocol error (HTTP)", message))
		except urllib2.URLError as message:
			self.logerror(self.fetcherror("Network error", message))
		except googlevoice.util.LoginError as message :
			self.logerror(self.fetcherror("Messaging system does not recognize you", message))


	def fetcherror(self, msgtxt, message) :				# report fetch error
		if message and len(str(message)) > 0:			# if useful exception info
			msgtxt += '. (' + str(message) + ')'		# add it
		msgtxt += '.'
		self.logwarning(msgtxt)							# log
		self.logout()
		return(msgtxt)

	def doitem(self, msgitem, convs) :
		if self.verbose :
			print("SMS in: %s" % (str(msgitem),))		# print message
		msgtime = msgitem['gc-message-sms-time'].strip()	# fetch named fields from Google's HTML - time without date
		msgtext = msgitem['gc-message-sms-text'].strip()	# the message text
		msgfrom = msgitem['gc-message-sms-from'].strip()	# sending phone number
		msgid = msgitem['id'].strip()					# conversation ID
		#	Get message date.  The Google Voice SMS row items only have a time, not a date.
		#	The conversation data has a date and time, but it's for the latest item in the
		#	conversation.  So we take the date from the conversation data, and the time
		#	from the message data.  This really isn't correct, but since we delete conversations
		#	older than one hour, it's not too troublesome.
		conv = None										# no matching info from JSON yet
		msgdate = None									# no message date yet
		if msgid in convs :								# is JSON info available for this conversation?
			conv = convs[msgid]							# look up conversation info to get date
			timestamp = conv.displayStartDateTime		# get time and date from conversation as a datetime object
			msgdate = timestamp.strftime("%B %d")		# display date as "November 12
			msgdate = re.sub(r'\s0',' ',msgdate)		# remove lead zeroes within date
		else :
			print("No matching JSON data for SMS msg ID " + str(msgid))	# unmatched JSON and HTML.  Not serious.
		#	Data cleanup
		msgfrom = kremovetrailcolon.sub("",msgfrom)		# remove trailing ":" that Google seems to append
		msgitem = feedmanager.FeedItem(self, msgfrom, msgdate, msgtime, None, msgtext)	# build output item
		digest = msgitem.digest							# get message digest as hex string, to check if seen before
		if digest in self.hashread :					# if already seen
			self.hashread[digest] = True				# note seen again
			return										# done
		self.hashread[digest] = True					# new message, note seen, but not yet printed
		if msgfrom.upper().startswith("ME") :			# if msg from self
			return										# ignore
		if self.verbose :
			print("New SMS msg from %s: %s" % (msgfrom, msgtext))
		#	If msg is from "Me", ignore it.  That's an echo of something we sent.
		self.inqueue.put(msgitem)						# add to output queue

	#	Delete old conversations.  Only call when no messages remain to be printed.
	def deleteoldmsgs(self, msgs) :						# delete old messages on server
		if not self.inqueue.empty() :					# if output queue not empty
			return
		now = time.time()								# time now
		if now - self.lastdelete < self.kdeleteinterval :	# too soon for delete cycle
			return
		if self.verbose :
			print("Deleting conversations older than %1.1f hours." % (self.kdeleteinterval / (60*60),))
		#	Get msg IDs from inbox.  Only these need to be deleted.
		ids = {}										# IDs of messages in inbox
		for msg in msgs :
			ids[msg["id"]] = True
		#	Get all SMS conversations	
		folder = self.fetchconversations()				# get all conversations
		for conv in folder.messages :					# for all conversations
			id = conv.id
			timestamp = conv.displayStartDateTime		# last update to conversation
			timediff = datetime.datetime.now() - timestamp		# age of conversation
			age = timediff.days * (60*60*24) + timediff.seconds	# convert to seconds
			ininbox = id in ids							# true if in inbox
			if self.verbose :
				print(" Conversation %s from %s at %s, age %1.1f days, inbox=%s" % 
					(id, str(conv.phoneNumber), str(timestamp), age/(24*60*60.0), str(ininbox)))
			if age > self.kdeleteage and ininbox :					# if old enough to delete
				if self.verbose :
					print(" Deleting conversation %s from %s at %s, age %1.1f days." % 
						(id, str(conv.phoneNumber), str(timestamp), age/(24*60*60.0)))
				conv.delete()							# mark as read
		self.lastdelete = now							# timestamp of last delete cycle


	def logwarning(self, errmsg) :						# log warning message
		print('WARNING: SMS:": %s' % (errmsg,))			# just print for now

	def logerror(self, errmsg) :						# return warning message to Teletype
		print('ERROR: SMS": %s' % (errmsg, ))				# Returned as error message
		if self.inqueue.empty () :						# only add error if empty.  Will repeat if problem
			newitem = feedmanager.FeedItem(self, None, "Today", "Now", None, None, errmsg)
			self.inqueue.put(newitem)					# add to output queue




									
