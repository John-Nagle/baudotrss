#
#	smssend.py  --  Send SMS message
#
#	John Nagle
#	March, 2009
#
#	License: LGPL
#
#	Not too useful in its present form.  The only way to send SMS messages
#	is via the OhDontForget service, which is send-only and requires
#	an arrangement with the service. 
#
import xmlrpclib
import re
#
#	Regular expressions
#
redeletehtml = re.compile(r'\<.*')					# remove everything after "<"
redeleteprefix = re.compile(r'ERROR CREATING REMINDER: ')	# remove prefix

#
#	class SMSsend  -- base class for SMS sending
#
class SMSsend(object) :

	def send(self, sourcenum, destnum, msg) :
		raise Exception("Must subclass SMSsend")	# no, can't do that.


#
#	SMSsendOhDontForget  --  SMS send via OhDontForget service.
#
#	This requires an account wiht OhDontForget.  
#
#	Sends via XML,  Sent message looks like this:
#
#<?xml version="1.0"?>
#    <methodCall>
#    <methodName>send</methodName>
#        <params>
#            <param><value><string>API_KEY_PROVIDED_BY_ODF</string></value></param>
#            <param><value><string>5551231234</string></value></param>
#            <param><value><string>2008-10-01 12:00:00</string></value></param>
#            <param><value><string>Test Message from ODF</string></value></param>
#           <param><value><int>4</int></value></param>
#            <param><value><string></string></value></param>
#        </params>
#    </methodCall>
#
class SMSsendOhDontForget(SMSsend) :
	basemsg = """<?xml version="1.0"?>
    <methodCall>
    <methodName>send</methodName>
        <params>
            <param><value><string>%s</string></value></param>
            <param><value><string>%s</string></value></param>
            <param><value><string>%s</string></value></param>
            <param><value><string>%s</string></value></param>
            <param><value><int>%d</int></value></param>
            <param><value><string></string></value></param>
        </params>
    </methodCall>
	"""
	apiurl = "http://api.ohdontforget.com/RPC2"			# URL, as provided by service
	knownmessages = {									# known error messages, with translations
		"UNSUPPORTED CELL NUMBER." : "NO SUCH NUMBER"
		}

	def __init__(self, apikey) :
		self.apikey = apikey							# use submitted API key
		self.apiurl = SMSsendOhDontForget.apiurl		# use this URL
		self.pastdate = "2008-10-01 12:00:00"			# a date in the past
		self.tzoffset = 8								# Pacific time

	def fixerrmsg(self, s) :							# clean up and summarize error message
		s = redeletehtml.sub('',s).strip().upper()		# get message into string format
		s = redeleteprefix.sub('',s).strip()			# remove standard prefix if present
		if SMSsendOhDontForget.knownmessages.has_key(s) :
			s = SMSsendOhDontForget.knownmessages[s]	# use our preferred message if available
		return(s)

	def send(self, sourcenum, destnum, msg) :			# send msg
		proxy = xmlrpclib.ServerProxy(self.apiurl)		# set up XML-RPC connection
		try :
			reply = proxy.send(self.apikey, destnum, self.pastdate, msg, self.tzoffset,"")
			return(str(reply))
		except IOError, message:						# if trouble
			return("Sending failed: " + str(message))	# explain
		except xmlrpclib.Fault, message:				# trouble
			s = self.fixerrmsg(message.faultString)		# get message into clean string
			print(s)									# ***TEMP*** 
			return("\a\aFailed: " + s)
		except xmlrpclib.ProtocolError, message:		# trouble at other end
			s = self.fixerrmsg(msg.errmsg)				# get error message and clean up
			print(s)									# ***TEMP*** 
			return("\a\aTrouble: " + s)
			 
#
#	Unit test
#
def test() :
	obj = SMSsendOhDontForget()							# get sending obj.
	s = obj.send("Test","6509069109","Test of SMS")		# send some test
	print("Reply from send:\n" + repr(s))				# reply

