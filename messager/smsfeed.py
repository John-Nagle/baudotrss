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
import logging
import datetime
import httplib
import urllib2
import BeautifulSoup
import feedmanager
import threading
import re
from pygooglevoicepatches import fetchfolderpage			# applies temporary patches to Google Voice


#
#	Useful regular expressions
#
kremovetrailcolon = re.compile(r':$')						# trailing colon

#
#	extractsms  --  extract SMS messages from BeautifulSoup tree of Google Voice SMS HTML.
#
#	Output is a list of dictionaries. one per message
#	A page may indicate that there are more pages to be read.
#
#	Returns (listofdicts, morepagestoread)
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
	#	Check for more pages to read
	moreitem = tree.find("a",attrs = {"id" : "gc-inbox-next"})	# check for more pages to read
	morepages = not (moreitem is None)					# more pages to read?
	return(msgitems, morepages)

#
#	class SMSfeed  --  read SMS messages from a Google Voice account.
#
class SMSfeed(feedmanager.Feed) :	

	kreadlistfile = "smsread.txt"						# list of SMS messages already read, as hashes	
	kheadertext = "\n\n\a\n\a- - - SMS MESSAGE - - -"	# printed as header
	ktrailertext =   "- - - END OF MESSAGE - - -\n\n"

	kpollinterval = 60.0								# poll this often (seconds)

	#	Message deletion - we must delete from inbox occasionally, to prevent it from becoming too big.
	#	We can currently handle multi-page inboxes, so this is just a performance improvement.
	kdeleteinterval = 60*30								# delete this often (seconds) even if no traffic
	kdeleteage = 60*60*4								# delete conversation if nothing in this period 

	khtmlrewrites = [									# rewrite rules for cleaning HTML data
		(re.compile(r'&mdash;'),'-'),					# convert HTML escape for mdash
		(re.compile(r'&amp;'),'&'),						# convert HTML escape for ampersand
		(re.compile(r'&\w+;'),'?'),						# any other special chars become question mark
		(re.compile(r'&\#\w+;'),'?')					# get numeric escapes, too.
		]												# 

					
	#
	#	Called from outside the thread
	#
	def __init__(self, username, password, persistentdir, logger) :
		feedmanager.Feed.__init__(self, "SMS", logger)
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
		self.trailertext = self.ktrailertext			# default trailer
		self.persistentdir = persistentdir				# save hashes of already-printed messages
		self.logger = logger							# debug og to here
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
		self.lastdelete = 0.0							# schedule a delete from inbox cycle

	def getpollinterval(self) :							# poll this often
		return(self.kpollinterval)

	def markallasread(self) :
		pass											# deliberately not supported for messages

	def unmarkallasread(self) :							# deliberately not supported for messages
		pass

	def formattext(self, msgitem) :						# format a msg item, long form
		kheaderfields = [("FROM","msgfrom"), ("DATE", "msgdate"), ("DELIVER TO", "msgdeliverto"),
			("DELIVERY NOTE","msgdeliverynote")]
		emsg = msgitem.errmsg
		#	Format for printing as display message
		if emsg :										# short format for errors
			s = "%s: %s\n" % (msgitem.msgtime, emsg)
			return(s)									# return with error msg
		#	Combine header, body and trailer
		fmt = "%s\n%s\n%s\n%s\n"						# add four fields
		s = fmt % (self.hdrtext, msgitem.formathdr("\n"), msgitem.body, self.trailertext)
		return(s)										# no error

	def summarytext(self, msgitem) :
		emsg = msgitem.errmsg
		#	Format for printing as display message
		if emsg :										# short format for errors
			s = "%s: %s\n" % (msgitem.msgtime, emsg)
			return(s)									# return with error msg
		fmt = "SMS %s -- %s"
		s = fmt % (msgitem.formathdr("  "), msgitem.body[:40])
		return(s)										# no error

	def sendSMS(self, number, text) :					# sending capability
		"""
		Send SMS message
		"""
		try: 
			self.logger.info("Sending SMS to %s: %s" % (number, text))
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
			self.logger.debug('Saving IDs of messages read to "%s"' % (self.getmsgsreadfilename(),))
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
				self.logger.info("Logging into Google Voice")	# note login
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
			(msgs, convs) = self.fetchconversations()	# get all messages
			self.logger.info("%d SMS messages in inbox, %d to print." % (len(msgs),self.inqueue.qsize()))	# number in inbox
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
			if False :									# ***TEMP TURNOFF*** deleted msgs can come back from 
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

	#
	#	fetchconversations  --  fetch all conversations from Google Voice
	#
	def fetchconversations(self) :							# fetch all SMS conversation folders
		try :
			voice = self.login()							# log in if necessary
			pagenum = 1										# start at page 1 of results
			morepages = True								# there are more pages to do
			msgs = []										# messages retrieved
			convs = {}										# map id -> conversation object
			while morepages :								# while more pages to do
				xmlparser = fetchfolderpage(voice,"sms",pagenum)		# Use workaround code that can do multiple pages
				xmlparser()									# build folder object
				infolder = xmlparser.folder					# get folder part of folder (JSON data)
				htmlsms = xmlparser.html					# get HTML part of folder
				####voice.inbox()							# obtain and parse inbox
				####htmlsms = voice.inbox.html				# get html from inbox
				####infolder = voice.inbox.folder			# folder of interest
				(msgpage, morepages) = extractsms(htmlsms)	# parse HTML into more useful form
				msgs.extend(msgpage)						# add new set of messages
				self.logger.info("Fetched %d conversations from Google Voice page %d; %d convs. in inbox, more pages: %s." % 
						(len(infolder.messages), pagenum, infolder.totalSize, str(morepages)))
				#	Extract conversation data, because the HTML data doesn't have all the info.
				for conv in infolder.messages :				# for all conversations
					id = conv.id
					convs[id] = conv						# index by ID
				pagenum += 1								# advance page number for next page
			return(msgs, convs)								# return all conversations

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

	def processitem(self, msgitem, convs) :				# returns a msgitem
		self.logger.debug("SMS in: %s" % (str(msgitem),))		# print message
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
		msgtext = self.cleanhtml(msgtext)				# clean up message text, which can have HTML escapes
		msgfrom = kremovetrailcolon.sub("",msgfrom)		# remove trailing ":" that Google seems to append
		msgitem = feedmanager.FeedItem(self, msgfrom, msgdate, msgtime, None, msgtext)	# build output item
		digest = msgitem.digest							# get message digest as hex string, to check if seen before
		if digest in self.hashread :					# if already seen
			self.hashread[digest] = True				# note seen again
			return(None)								# done
		self.hashread[digest] = True					# new message, note seen, but not yet printed
		#	If msg is from "Me", ignore it.  That's an echo of something we sent.
		if msgfrom.upper().startswith("ME") :			# if msg from self
			return(None)								# ignore
		self.logger.debug("New SMS msg from %s: %s" % (msgfrom, msgtext))
		return(msgitem)									# return a msgitem

	#	Doitem -- called for each item to be printed
	#	Override this in subclasses for special processing
	def doitem(self, msgitem, convs) :
		msgitem = self.processitem(msgitem, convs)		# make into a message item
		if msgitem :									# if got an item
			self.inqueue.put(msgitem)					# enqueue it

	def cleanhtml(self, s)	:							# clean out HTML escapes
		for (pattern, rep) in self.khtmlrewrites :		# apply all rewrite rules
			s = pattern.sub(rep, s)						# in sequence
		return(s)										# return string without HTML escapes


	#	Delete old conversations.  Only call when no messages remain to be printed.
	#	The Google Voice inbox can only hold 10 messages, so we have to move
	#	printed conversations to the Trash.  
	#	But there's a race condition problem.  Deletion is by conversation, not message.
	#	We cannot tell, when deleting a conversation, if a message came in for it recently.
	#	We don't delete a conversation that had traffic in the last N minutes, but this
	#	is not airtight.  NEEDS WORK
	def deleteoldmsgs(self, msgs) :						# delete old messages on server
		if not self.inqueue.empty() :					# if output queue not empty
			return
		now = time.time()								# time now
		if now - self.lastdelete < self.kdeleteinterval :	# too soon for delete cycle
			return
		self.logger.info("Deleting conversations older than %1.1f minutes." % (self.kdeleteage / (60),))
		#	Get msg IDs from inbox.  Only these need to be deleted.
		ids = {}										# IDs of messages in inbox
		for msg in msgs :
			ids[msg["id"]] = True
		#	Get all SMS conversations	
		(msgs, convs) = self.fetchconversations()		# get all conversations
		for conv in convs.values() :					# for all conversations
			id = conv.id
			timestamp = conv.displayStartDateTime		# last update to conversation
			timediff = datetime.datetime.now() - timestamp		# age of conversation
			age = timediff.days * (60*60*24) + timediff.seconds	# convert to seconds
			ininbox = id in ids							# true if in inbox
			self.logger.debug(" Conversation %s from %s at %s, age %1.1f days, inbox=%s" % 
					(id, str(conv.phoneNumber), str(timestamp), age/(24*60*60.0), str(ininbox)))
			if age > self.kdeleteage and ininbox :					# if old enough to delete
				self.logger.info(" Deleting conversation %s from %s at %s, age %1.1f days." % 
						(id, str(conv.phoneNumber), str(timestamp), age/(24*60*60.0)))
				conv.delete()							# mark as read
		self.lastdelete = now							# timestamp of last delete cycle


	def logwarning(self, errmsg) :						# log warning message
		self.logger.warning('SMS:": %s' % (errmsg,))	

	def logerror(self, errmsg) :						# return warning message to Teletype
		self.logger.error('SMS": %s' % (errmsg, ))				# Returned as error message
		if self.inqueue.empty () :						# only add error if empty.  Will repeat if problem
			newitem = feedmanager.FeedItem(self, None, "Today", "Now", None, None, errmsg)
			self.inqueue.put(newitem)					# add to output queue




									
