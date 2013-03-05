#
#    feedmanager.py  -  manage feeds from multiple sources
#
#    Part of "baudottty".
#
#    John Nagle
#    November, 2009
#
#    Polls multiple RSS and SMS feeds, returns items.
#
#    The data returned is pure text, not HTML.  This is intended for
#    applications where the output is a printing device displaying
#    news updates. 
#
#    License: LGPL
#
import re
import time
import datetime
import types
import Queue
import threading
import hashlib
import msgutils
#
#   Constants
#
MINERRMSGINTERVALSECS = 120.0            # minimum interval between error msgs
#
#   class FeedItem  -- one item from a feed
#
class FeedItem(object) :

    #   Names of printable header fields, for display purposes
    kheaderfields = [("FROM","msgfrom"), ("DATE", "msgdate"), ("TIME","msgtime"),
        ("MSG. NO", "serial"), 
        ("DELIVER TO", "msgdeliverto"), ("DELIVER AT","msgdeliverynote"),("SUBJECT","subject")]

    def __init__(self, feed, msgfrom, msgdate, msgtime, subject, body, errmsg = None) :
        self.feed = feed                                # Feed object
        self.msgdate = msgdate                          # message date
        self.msgtime = msgtime                          # message time
        self.msgfrom = msgfrom                          # message source
        self.msgdeliverto = None                        # optional DELIVER TO field
        self.msgdeliverynote = None                     # optional DELIVERY NOTE field
        self.subject = subject                          # subject, if source has subjects
        self.body = body                                # body text
        self.errmsg = errmsg                            # error message if any
        self.calcdigest()                               # calculate message digest, for duplicate removal

    def setnote(self, msgdeliverynote) :                # set DELIVERY NOTE field
        self.msgdeliverynote = msgdeliverynote

    def setto(self, msgdeliverto) :                     # set DELIVER TO field
        self.msgdeliverto = msgdeliverto 

    def formathdr(self, delim="\n") :                   # general-purpose formatting of header
        #    Format header fields
        hdr = ""
        for (printname, attrname) in self.kheaderfields :  # process fields
            val = getattr(self, attrname, None)            # get field value if present
            if val is None :                            # not present
                continue
            strval = ""                                 # convert types to strings as necessary
            if type(val) in (types.StringType, types.UnicodeType) :
                strval = val
            elif isinstance(val, time.struct_time) :    # if time object
                strval = time.strftime("%B %d, %I:%M %p", val)    # formatted time
            else :
                strval = repr(val)                      # default
            hdr += printname + ": " + strval + delim    # add to string
        return(hdr)


    def formattext(self) :                              # return long formatted version of content
        return(self.feed.formattext(self))              # use feed-specific format

    def summarytext(self) :                             # return item summary
        return(self.feed.summarytext(self))

    def gettitle(self) :                                # get title of feed
        return(self.feed.gettitle())

    def itemdone(self) :                                
        """
        Indicate done (printed, sent, etc.) with item.
        
        Only one item per feed can be outstanding (obtained with getitem, but not done)
        at a time.
        """
        self.feed.itemdonebase(self)                    # item will not be returned again after a crash

    def calcdigest(self) :                              # calculate message digest for uniqueness
        self.feed.calcdigest(self)                      # use feed-specific calculation


#
#    class Feed   --  base class for feeds
#
class Feed(threading.Thread) :
    """
    Feed --  base class for all feeds
    """
    kidleinterval = 60.0                                # if no item request for this long, stop polling
    #    Called from outside thread
    def __init__(self, feedtype, logger) :
        threading.Thread.__init__(self)                 # initialize base class
        self.logger = logger                            # logger object
        self.feedtype = feedtype                        # "NEWS" or "SMS"
        self.inqueue = Queue.Queue()                    # input queue
        self.aborting = False                           # not yet aborting
        self.lastpoll = 0.0                             # no last poll yet
        self.lastget = time.time()                      # last get request
        self.header = None                              # no special header
        self.trailer = None                             # no special trailer
        self.lasterrmsg = ""                            # for error undup
        self.lasterrtime = 0                            # last error time
        self.lastitem = None                            # last item returned
        
    def setheaders(self, header, trailer) :
        """
        Set header and trailer for display.
        """
        self.header = header
        self.trailer = trailer
    

    def abort(self) :                               # abort thread
        self.logger.debug('Aborting feed "%s"' % (self.feedtype,))
        if not self.is_alive() :                    # if not started
            self.logger.debug('Not running feed "%s"' % (self.feedtype,))
            return                                  # no problem.
        self.aborting = True                        # abort this task at next read timeout
        self.join(20.0)                             # wait for thread to finish
        if self.is_alive() :
            raise RuntimeError('INTERNAL ERROR: "%s" feed thread will not terminate.  Kill program.' % (self.gettitle(),))
        else :
            self.logger.debug('Shut down feed "%s"' % (self.feedtype,))


    def getitem(self) :                                 # get a queue item - called every few seconds
        assert(self.lastitem == None)                   # an item is in use - should not call
        if not self.is_alive() :                        # if thread not running
            raise RuntimeError('Feed "%s" reader has failed.' % (self.gettitle(),))    # fail caller, so program will shut down
        self.lastget = time.time()                      # time of last get request, for idle check
        try: 
            item = self.inqueue.get_nowait()            # get input if any
            if isinstance(item, Exception) :            # if item is an exception, thread raised an exception
                raise item                              # raise exception to force shutdown
            self.lastitem = item                        # item currently being worked on 
            return(item)                                # otherwise just return item
        except Queue.Empty:                             # if empty
            return(None)                                # done
            
    def itemdonebase(self, item) :
        """
        Note that the one outstanding item is done.
        """
        assert(self.lastitem == item)                   # must be valid item
        self.itemdone(item)                             # call in subclass 
        self.lastitem = None                            # no item active now
        
    def itemdone(self) :
        raise(RuntimeError("itemdone unimplemented"))   # must override in subclass
        
    def isfeedidle(self) :                              # if feed is idle
        """
        True if feed is idle - nothing being printed, and nothing queued.
        """
        return(self.lastitem is None and self.inqueue.empty())  # nothing going on?  

    def forcepoll(self) :                               # force an immediate poll
        self.lastpoll = 0.0                             # in a few seconds

    def formattext(self, item) :                        # default formatting, can override
        if item.errmsg :
            return("ERROR: " + item.errmsg)
        return(item.body)                               # otherwise body

    def summarytext(self, item) :                       # short version, default formatting
        raise RuntimeError("feedmanager.summarytext not overridden")    # subclass must override
        

    #    Called from within thread
    def run(self) :                                      # working thread
        try:
            while not self.aborting :                    # until killed
                self.dopoll()                            # do a poll cycle
                time.sleep(5.0)                          # wait at least 5 secs
            self.logger.debug('Feed "%s" shutting down.' % (self.gettitle(),))    # note abort
        except Exception as message :                    # if trouble
            self.logger.exception('Feed "%s" exception: %s' % (self.gettitle(), str(message)))
            self.inqueue.put(message)                    # queue exception for main task and exit

    def dopoll(self) :                                   # do one poll cycle
        if not self.inqueue.empty() :                    # if data available
            return                                       # nothing to do    
        now = time.time()                                # time now
        timetopoll = self.getpollinterval() - (now - self.lastpoll)    # seconds untl next poll
        if now - self.lastget > self.kidleinterval :     # if nobody wants data (Teletype not running)
            self.logger.debug("Off, no poll.")
            return                                       # nothing to do
        self.logger.debug("Next %s poll in %1.1fs." % (self.feedtype, timetopoll))
        if timetopoll >= 0.0 :                           # if too soon
            return
        #    Time to do a poll
        self.logger.info("Polling %s" % (self.feedtype,))
        self.fetchitems()                                # ask feed for some items
        self.lastpoll = time.time()                      # wait a full poll interval before asking again
        
    def calcdigest(self, item) :                 
        """
        Calculate message digest for uniqueness check
        Generic version.  Some feeds have their own.
        """
        m = hashlib.md5()                               # begin a hash of the fields present
        for (printname, attrname) in item.kheaderfields :    # for all header fields
            m.update(repr(getattr(item, attrname,"")))  # add attr to hash
        if item.body :
            m.update(repr(item.body))                   # body of msg
        item.digest = m.hexdigest()                     # get message digest as hex string, to check if seen before

        
    def logwarning(self, errmsg) :                      # log warning message
        self.logger.warning('SMS:": %s' % (errmsg,))    

    def logerror(self, errmsg) :      
        """
        Return error message to Teletype.  
        
        Duplicate messages are suppressed.
        """
        self.logger.error('SMS error: %s' % (errmsg, ))      # Returned as error message
        #   Only add error if empty.  Will repeat if problem
        if self.lasterrmsg == errmsg :          # if duplicate error
            timesinceerror = time.time() - self.lasterrtime
            if timesinceerror < MINERRMSGINTERVALSECS :
                return                          # don't print too often
        if self.inqueue.empty () :              # if nothing queued
            timenow = datetime.datetime.now()   # timestamp
            newitem = FeedItem(self, None, 
                msgutils.editdate(timenow), 
                msgutils.edittime(timenow), 
                None, None, errmsg)
            self.inqueue.put(newitem)           # add to output queue
            self.lasterrtime = time.time()      # record err printed
            self.lasterrmsg = errmsg
                                    
#
#    class Feeds  --  handle multiple news feeds
#
class Feeds(object) :
    def __init__(self, logger) :
        self.logger = logger                            # logging object
        self.feeds = []                                 # no feeds yet
        self.lasttitle = None                           # no last title

    def addfeed(self, feed) :                           # add a feed
        self.feeds.append(feed)                         # add a feed
        feed.start()                                    # start the feed running

    def abort(self) :                                   # abort all feeds
        for feed in self.feeds :                        # tell all feeds to abort
            feed.abort()                                # if they don't, we will hang. 
        for feed in self.feeds :                        # wait for finish 
            feed.join()

    def getitem(self) :                                 # get one item, from some feed
        for feed in self.feeds :                        # try all feeds
            item = feed.getitem()                       # get one item
            if item :                                   # if got an item
                return(item)                            # return it
        return(None)                                    # no new items available

    def setlasttitleprinted(self,title) :
        self.lasttitle = title                          # set last title printed

    def getlasttitleprinted(self) :                     # get last title printed
        return(self.lasttitle)

    def markallasread(self, feedtype) :                 # mark all stories as read
        for feed in self.feeds :                        # try all feeds
            if feed.feedtype == feedtype :              # if desired type of feed
                feed.markallasread()                    # mark all as read

    def unmarkallasread(self, feedtype) :               # unmark all stories as unread
        for feed in self.feeds :                        # try all feeds
            if feed.feedtype == feedtype :              # if desired type of feed
                feed.unmarkallasread()                  # mark all as read

