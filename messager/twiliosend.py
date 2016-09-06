#
#   twiliosend.py  -  fetch SMS messages from our private server
#
#   John Nagle
#   November, 2010
#
#   Outgoing SMS sending.  Direct to Twilio, not our server.
#
#
#   License: LGPL
#
#
from six.moves import urllib
import xml
import base64
#
#   Constants
#   
TWILIOBASE = "https://api.twilio.com/2010-04-01/"            # Twilio base URL for API endpoint


class Twiliosend(object) :    
                   
    def __init__(self, accountsid, authtoken, ourphoneno, logger) :
        self.accountsid = accountsid                    # accounts ID - for all requests
        self.authtoken = authtoken                      # auth token
        self.ourphoneno = ourphoneno                    # our phone number
        self.logger = logger                            # debug output


    def twiliopost(self, url, fields) :                 # send to Twilio
        """
        Send POST request to Twilio server.  Used only for sending SMS.
        """
        try :
            data = None                                 # no data yet
            if fields :                                 # if data to POST
                data = urllib.parse.urlencode(fields).encode("ascii")   # encode POST data
            fd = None                                   # no file handle yet
            #   Always send with basic authentication.
            req = urllib.request.Request(url)           # empty URL request
            authstring = '%s:%s' %  (self.accountsid, self.authtoken) # compose authorization string
            authbytes = base64.b64encode(authstring.encode("ascii")) # str->ascii->base64
            req.add_header("Authorization", "Basic ".encode('ascii') + authbytes)
            fd = urllib.request.urlopen(req, data, 20.0) # do request
            s = fd.read()                               # read reply XML
            fd.close()                                  # done with fd
            tree = xml.etree.ElementTree.fromstring(s)  # parse into tree
            return(None, tree)
        except IOError as message:                      # trouble          
            self.logger.error("Twilio error: " + str(message))
            status = getattr(message,"code", 599)       # get HTTP fail code
            return(status, None)                        # fails
        except xml.etree.ElementTree.ParseError as message:
            self.logger.error("Twilio XML reply not parsable: " + str(message))
            status = getattr(message,"code", 599)       # get expat parser fail code
            return(status, None)
            
    def fetcherror(self, msgtxt, message) :             # report fetch error
        if message and len(str(message)) > 0:           # if useful exception info
            msgtxt += '. (' + str(message) + ')'        # add it
        msgtxt += '.'
        self.logger.warning(msgtxt)                     # log
        return(msgtxt)
         
        
    def sendSMS(self, number, text) :                   # sending capability
        """
        Send SMS message.  This goes directly to Twilio, not our server.
        """
        try: 
            self.logger.info("Sending SMS to %s: %s" % (number, text))
            fields = {"From" : self.ourphoneno , 
                "To"  : number, "Body" : text }
            url = "%sAccounts/%s/Messages" % (TWILIOBASE, self.accountsid)
            (status, tree) = self.twiliopost(url, fields)    # send to Twilio
            if status :
                return(self.fetcherror("Problem No. %s sending message" %
                    (status,), None))
            if tree is not None:                        # if reply parsed
                ####print("Got reply tree: \n" + xml.etree.ElementTree.tostring(tree, encoding="unicode", method="xml")) # ***TEMP***
                for tag in tree.iter("Status") :        # look for Status anywhere
                    print("Got status.")                # ***TEMP***
                    smsstatus = tag.text                # string in 
                    if smsstatus :
                        smsstatus = smsstatus.strip().lower()
                        if smsstatus == "queued" :
                            return(None)                # success
                        else :                          # fail
                            return(self.fetcherror(
                                'Problem "%s" sending message' % 
                                (smsstatus,), None))
            return(self.fetcherror(
                'Message sending service not responding properly',
                 None))
        except IOError as message:
            return(self.fetcherror("Input or output error", message))

