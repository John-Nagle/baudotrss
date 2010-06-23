#
#	aethericmsgfeed.py  -  fetch SMS messages via Google Voice, as steampunk "Aetheric Message" machine.
#
#	John Nagle
#	January, 2010
#
#	Subclass of SMSfeed that uses "Aetheric Message" machine processing.
#
#	License: LGPL
#
#
import smsfeed
import re

kaethericmsgre = re.compile(r'\s*TO\s+(.+)[:\-](.+)',re.IGNORECASE)	# TO: name : content
#
#	class AethericMessageFeed  --  read SMS messages from a Google Voice account, "Aetheric Message" processing
#
class AethericMessageFeed(smsfeed.SMSfeed) :	

	kheadertext = "\n\n\a\n\a. . . THE AETHERIC MESSAGE MACHINE COMPANY, LTD.  . . ."	# printed as header
	ktrailertext =   ". . . END OF MESSAGE . . .\n\n"
	kerrormsg1 = 'Aetheric messages, to be delivered, must begin "TO full name :".  The ":" is required.  Please try again.'
	kerrormsg1s = 'No "TO name "'	# note problem
	kackmsg1 = 'Yr. message to "%s" received for delivery by The Aetheric Msg Machine Co, Ltd and St.Clair Aeronauts.'
	kenablesmsreplies = True								# true to send SMS replies for errors and acks
	kenableprintrejects = False								# true if we will print rejected messages
					
	#
	#	Called from outside the thread
	#
	def __init__(self, username, password, persistentdir, logger) :
		smsfeed.SMSfeed.__init__(self, username, password, persistentdir, logger ) 
		self.hdrtitle = "Aetheric Message"
		self.url = self.hdrtitle
		self.hdrtext = self.kheadertext					# default header, can be replaced
		self.trailertext = self.ktrailertext			# default trailer
		self.enablesmsreplies = self.kenablesmsreplies	# send SMS replies?


	#	Doitem -- called for each item to be printed
	#
	#	Overriding standard processing to reply to sender
	#
	def doitem(self, msgitem, convs) :
		msgitem = self.processitem(msgitem, convs)		# make into a message item
		if msgitem :									# if got an item
			if msgitem.errmsg :							# if error, handle as error
				self.inqueue.put(msgitem)				# enqueue it
				return
			#	Non-error. Check formatting.
			#	Messages must be of the form "To <name> <: or -> <content>"
			matchitem = kaethericmsgre.match(msgitem.body) # parse SMS message content
			if matchitem :
				(topart, contentpart) = matchitem.group(1,2)	# decompose message
				if not topart is None and not contentpart is None : #	if valid
					msgitem.msgdeliverto = topart.strip()		# break body field into TO and body fields
					msgitem.body = contentpart			# delete TO info from body field
					self.inqueue.put(msgitem)			# process item
					replytext = self.kackmsg1 % (topart,)	# format reply
					if self.enablesmsreplies :
						self.sendSMS(msgitem.msgfrom, replytext)	# send ack to sender
					return
			#	Trouble - not valid
			#	Prints on Teletype as normal message, but the error is noted
			if self.enablesmsreplies :
				self.sendSMS(msgitem.msgfrom, self.kerrormsg1)	# reply to caller
			msgitem.body = "ERROR: %s\n\n%s" % (self.kerrormsg1s, msgitem.body)
			if self.kenableprintrejects :				# if printing rejected messages
				self.inqueue.put(msgitem)				# still print, but as error 
				
	