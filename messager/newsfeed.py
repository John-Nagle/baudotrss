#
#    newsfeed.py  -  fetch news feed via Atom/RSS
#
#    John Nagle
#    February, 2009
#
#    Polls multiple RSS feeds, returns new items.
#
#    Usage: create a Newsfeeds object, and provide it with a list
#    of RSS URLs.  Run via "start" in feedmanager.  Get items
#    using queue in feedmanager.
#
#    The data returned is pure text, not HTML.  This is intended for
#    applications where the output is a printing device displaying
#    news updates. 
#
#    License: LGPL
#
import sys
#    Add additional paths for our files
sys.path.append("./feedparser")                         # in subdir
import re
import msgutils
import feedparser
import time
import feedmanager
import Queue
import rfc822                                           # for date parsing
import calendar                                         # for date parsing
import datetime
import urllib2
import hashlib
#
#    Constants
#
KPOLLINTERVAL = 90.0                                    # poll this often
NEWSMAXAGEDAYS = 30                                     # last 30 days of news only
#
#    Support functions
#
#    Patch feedparser to support time zone information in RFC2822 time stamps.
#
def RFC2822dateparser(aDateString):
    """parse a RFC2822 date, including time zone: 'Sun, 28 Feb 2010 11:57:48 -0500'"""
    dateinfo = rfc822.parsedate_tz(aDateString)         # parse date
    if dateinfo is None :                               # if none, fail
        return(None)                                    # next parser gets a chance
    utcstamp = rfc822.mktime_tz(dateinfo)               # convert to timestamp format
    utcdate = time.gmtime(utcstamp)                     # convert back to time tuple, but now in UT
    ####print("RFC2822dateparser: in: %s   dateinfo: %s  out: %s" % (repr(aDateString), repr(dateinfo), repr(utcdate))) ## ***TEMP***
    return(utcdate)                                     # feedparser wants UT time

feedparser.registerDateHandler(RFC2822dateparser)       # register above conversion with feedparser
#
kremovenonalpha = re.compile(r'\W')
#
def textsubset(s1, s2) :
    """
    True if s1 is a subset of s2, considering alphanumeric chars only
    """
    return(kremovenonalpha.sub("",s2).startswith(kremovenonalpha.sub("",s1)))
    
#
#    class Newsfeed  --  one news feed
#
class Newsfeed(feedmanager.Feed) :                            

    #    FeedParser's list of acceptable HTML elements.
    standard_acceptable_elements = ['a', 'abbr', 'acronym', 'address', 'area', 'b', 'big',
      'blockquote', 'br', 'button', 'caption', 'center', 'cite', 'code', 'col',
      'colgroup', 'dd', 'del', 'dfn', 'dir', 'div', 'dl', 'dt', 'em', 'fieldset',
      'font', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'input',
      'ins', 'kbd', 'label', 'legend', 'li', 'map', 'menu', 'ol', 'optgroup',
      'option', 'p', 'pre', 'q', 's', 'samp', 'select', 'small', 'span', 'strike',
      'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'textarea', 'tfoot', 'th',
      'thead', 'tr', 'tt', 'u', 'ul', 'var']

    #    Our list. We drop almost all markup, then truncate at the first remaining tag.
    acceptable_elements = ['a','p','br']            # severely censor HTML markup
    #
    kescaperemovals = [
        (re.compile(r'&mdash;'),'-'),               # convert HTML escape for mdash
        (re.compile(r'&amp;'),'&'),                 # convert HTML escape for ampersand
        (re.compile(r'&\w+;'),'?'),                 # any other special chars become question mark
        (re.compile(r'&\#\w+;'),'?'),               # get numeric escapes, too.
        (re.compile(r'<[^>]*>'),' '),               # remove any remaining markup
        (re.compile(r'[\t\r ]+'),' '),              # all whitespace becomes a single space
        (re.compile(r'\n[ ]+'),'\n'),               # remove whitespace at end of line
        (re.compile(r'\n\n\n+'),'\n\n')]            # never more than two newlines
    
    khtmrewrites = [                                # rewrite rules for cleaning up news items
        (re.compile(r'<div.*'),''),                 # remove Reuters crap at end ***TEMP***
        (re.compile(r'<a.*'),''),                   # remove Reuters crap at end ***TEMP***
        (re.compile(r'<p>'),'\n\n'),                # convert breaks to newlines.
        (re.compile(r'</p>'),' '),                  # remove closing paragraph tag
        (re.compile(r'<br>'),'\n\n'),               # convert breaks to newlines.
        (re.compile(r'<br/>'),'\n\n'),              # convert breaks to newlines.
        (re.compile(r'<[^>]*>'),' ')]               # remove any remaining markup
         
    kdescriptionrewrites = khtmrewrites + kescaperemovals

    #
    #    Called from outside the thread
    #
    def __init__(self, url, logger) :
        feedmanager.Feed.__init__(self, "NEWS", logger)
        self.setfeedurl(url)                            # set feed URL
        self.expirationsecs = 60*60*24*2                # expire after not seen for 2 days
        self.maxage = 60*60*24*NEWSMAXAGEDAYS           # don't show items older than this
        ####print(feedparser._HTMLSanitizer.acceptable_elements)    # ***TEMP***
        feedparser._HTMLSanitizer.acceptable_elements = self.acceptable_elements
        ####print(feedparser._HTMLSanitizer.acceptable_elements)    # ***TEMP***
        ####self.expirationsecs = 60                        # ***TEMP DEBUG***

    def setfeedurl(self, url) :                            # set new feed URL
        self.url = url                                    # save URL
        self.hdrtitle = None                            # no header title yet
        ####self.hdrdate = None                                # no header date yet
        self.etag = None                                # no feed sequence id yet
        self.modified = None                            # no last-modified timestamp yet
        self.itemqueued = {}                            # item has been queued for printing
        self.markingallasread = True                    # marking all stories as read.

    def markallasread(self) :                           # mark all stories as read
        try: 
            while True :                                # drain
                self.inqueue.get_nowait()               # get input, if any
        except Queue.Empty:                             # when empty
            pass                                        # done
        self.logger.info("News feed queue emptied.")
        self.markingallasread = True                    # mark all as read for one cycle            

    def unmarkallasread(self) :                         # clear items already read
        try: 
            while True :                                # drain
                self.inqueue.get_nowait()               # get input, if any
        except Queue.Empty:                             # when empty
            pass                                        # done
        self.logger.info("News feed queue restarted.")  # restarting from beginning
        self.markingallasread = False                   # do not mark all as read
        self.itemqueued = {}                            # no item has been queued for printing
        self.modified = None                            # no last-modified date
        self.etag = None                                # no previous RSS read
        self.forcepoll()                                # force an immediate poll

    def gettitle(self) :                                # get feed title 
        if self.hdrtitle :
            return(self.hdrtitle)
        else:
            return(self.url)                            # use URL if unable to read

    def getpollinterval(self) :                            # how often to poll
        return(KPOLLINTERVAL)

    def itemdone(self, item) :                            # done with this item - item printed
        pass                                            # we don't keep persistent state of news printed

    def formattext(self, msgitem) :                        # format a msg item, long form
        emsg = msgitem.errmsg
        date_string = "%s, %s" % (msgitem.msgdate, msgitem.msgtime)    # formatted time
        #    Format for printing as display message
        if emsg :                                        # short format for errors
            s = "%s: %s\n" % (date_string, emsg)
            return(s)                                    # return with error msg
        #    Long form display
        s = msgitem.subject + '\n(' + date_string + ')\n' + msgitem.body + '\n\n' # Add CR at end
        return(s)                                        # no error

    def summarytext(self, msgitem) :
        emsg = msgitem.errmsg
        #    Format for printing as short message
        if emsg :                                        # short format for errors
            s = "%s: %s\n" % (msgitem.msgtime, emsg)
            return(s)                                    # return with error msg
        date_string = "%s, %s" % (msgitem.msgdate, msgitem.msgtime)    # formatted time
        fmt = "FROM %s  TIME %s: %s"
        s = fmt % (msgitem.msgfrom, date_string, msgitem.body[:40])
        return(s)                                        # no error
  
    #
    #    Called from within the thread
    #        
    def fetchitems(self) :                            
        """
        Fetch more items from feed source.
        """
        try :                                           # try fetching
            now = time.time()                           # timestamp
            d = feedparser.parse(self.url,etag=self.etag,modified=self.modified)    # fetch from URL
            if d is None or not hasattr(d,"status") :   # if network failure
                raise IOError("of network or news source failure")
            if d.status == 304 :                        # if no new items
                self.logger.debug("Feed polled, no changes.")
                return                                  # nothing to do
            self.logger.debug("Read feed: %d entries, status %s" % (len(d.entries), d.status))
            if d.status != 200 :                        # if bad status
                raise IOError("of connection error No. %d" % (d.status,))
            #   Get fields from feed.  
            if not "title" in d.feed :                  # if no title
                msg = self.handleunrecognizedfeed(self.url)     # Is this some non-RSS thing?
                raise IOError(msg)                      # handle error
            self.hdrtitle = d.feed.title                # feed title
            hdrdescription = d.feed.description         # feed description
            oldetag = self.etag                         # save old etag for diagnosis
            oldmodified = self.modified                 # save old timestamp for diagnosis
            if hasattr(d,"etag") :                      # if feed has etag indicating sequence    
                self.etag = d.etag                      # save position in feed for next time
            else :                                      # no etag, must re-read whole feed every time
                etag = None
            self.modified = getattr(d,"modified",None)  # save last update timestamp, if any, for next time
            hdrdate = "" #### d.feed.date               # date as string
            #    Process all entries in feed just read.
            #    Ignore items that were previously seen
            for entry in d.entries :                    # get items from feed
                msgitem = self.doentry(entry, now)      # do this entry
                if msgitem :                            # if new item to print
                    self.inqueue.put(msgitem)           # save this item
            self.markingallasread = False               # if marking all as read, stop doing that.
            #    Purge stories not seen in a while.
            self.purgeolditems(now-self.expirationsecs, self.itemqueued)    # purge old previousy read stories when expired

        except (IOError, AttributeError) as message :   # if trouble
            self.logger.exception(message)              # debug
            errmsg = 'No "%s" news because %s.' % (self.gettitle(), str(message))
            self.logerror(errmsg)                       # log

    def purgeolditems(self,expirationtime,dict) :       # purge old items already seen and printed
        #    We have to do this the hard way, because stories can appear in the feed, be preempted
        #    by higher priority stories, and reappear later.
        expired = []                                    # expired items
        for elt in dict :                               # for item in dictionary
            if dict[elt] < expirationtime :             # if expired
                expired.append(elt)                     # note expired
        for elt in expired :                            # for all expired items
            del(dict[elt])                              # delete from dict
            self.logger.debug("Expired: %s" % (elt,))   # debug

    def doentry(self,entry, now)    :                       # do one feed entry
        title = self.cleandescription(entry.title)          # title of entry
        id = getattr(entry,"id", None)                      # ID of entry
        description = entry.description                     # description of entry
        #    Clean up news item.  Should do this via feedparser utilities.
        description = self.cleandescription(entry.description)
        #   Check for title just being the beginning of the description
        if textsubset(title, description) :                 # if title is just beginning of description
            title = ""                                      # drop title
        try :                                               # feedparser >= 5.1.1
            date = entry.published                          # publication date of entry
            dateparsed = entry.published_parsed             # date parsed
        except AttributeError:                              # older feedparser
            date = entry.date                               # feedparser < 5.1.1
            dateparsed = entry.date_parsed
        # convert to local time.  Feedparser times are UT
        timestamp = calendar.timegm(dateparsed)             # get timestamp value
        ageinsecs = time.time() - timestamp                 # age of item in seconds
        if ageinsecs > self.maxage :                        # if too old
            self.logger.debug("Very old feed item date: %s - dropped" % (repr(date)))
            return(None)
        dateparsed = datetime.datetime.fromtimestamp(timestamp)
        assert(isinstance(dateparsed, datetime.datetime))
        msgitem = feedmanager.FeedItem(self, self.gettitle(), 
            msgutils.editdate(dateparsed), 
            msgutils.edittime(dateparsed), 
            title, description)
        #    Have we read this item already?  Check for duplicates.
        #    If either the ID or the text is duplicated, it's a duplicate.
        #    Sometimes IDs change when the text does not, because of server-side problems.
        seen = msgitem.digest in self.itemqueued        # true if already seen
        if self.markingallasread :                      # if marking all as read
            seen = True                                 # pretend we've seen this story
        self.itemqueued[msgitem.digest] = now           # keep keys of stories read
        logtext = "NO TITLE"                            # text for logging only
        if title :                                      # use title
            logtext = title[:40].encode('ascii','replace')
        elif description :                              # or description
            logtext = description[:40].encode('ascii','replace')
        if seen :                                       # if already seen
            self.logger.debug("Old feed item: (%s)  %s" % (id, logtext))     # Note news item
            ####self.logger.debug("Old feed item date: %s   %s" % (repr(date), repr(dateparsed)))    # ***TEMP***
            return(None)
        #    New news item, prepare for display
        self.logger.debug("New feed item: (%s)  %s" % (id,logtext))        # Note news item
        ####self.logger.debug("New feed item date: %s   %s" % (repr(date), repr(dateparsed)))    # ***TEMP***
        return(msgitem)                                    # build and return new item

    def cleandescription(self, s)    :                        # clean up description (item body) for printing
        if s is None :
            return(s)                                       # handle no description case
        #    Clean up news item.  Should do this via feedparser utilities.
        ####print("Before clean:\n" + s.encode('ascii','replace'))            # ***TEMP***
        for (pattern, rep) in self.kdescriptionrewrites :    # apply all rewrite rules
            s = pattern.sub(rep, s)                            # in sequence
        ####print("After clean:\n" + s.encode('ascii','replace'))                # ***TEMP***
        return(s.strip())                                    # remove any lead/trail white space 

    def calcdigest(self, item) :                 
        """
        Calculate message digest for uniqueness check
        Version for news feeds only.  Only looks at source, title and body.
        Some news sources (esp. Reuters) will resend the same message with a new timestamp. 
        """
        m = hashlib.md5()                               # begin a hash of the fields present
        m.update(repr(item.msgfrom))                    # source
        m.update(repr(item.subject))                    # subject
        m.update(repr(item.body))                       # body of msg
        item.digest = m.hexdigest()                     # get message digest as hex string, to check if seen before
        
        
    


                                    
