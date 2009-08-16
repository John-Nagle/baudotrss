#
#	newsfeed.py  -  fetch news feed via Atom/RSS
#
#	John Nagle
#	February, 2009
#
#	Polls multiple RSS feeds, returns new items.
#
#	Usage: create a Newsfeeds object, and provide it with a list
#	of RSS URLs.  Call "getitem" to get the next item from some feed.
#	When no items are available, None is returned.  Then wait 1-2 minutes
#	and call "getitem" again.
#
#	The data returned is pure text, not HTML.  This is intended for
#	applications where the output is a printing device displaying
#	news updates. 
#
#	License: LGPL
#
import sys
#	Add additional paths for our files
sys.path.append("./feedparser")							# in subdir
import re
import feedparser
import time
#
#	strtime -- time as a string.  Accepts "None"
#
def strtime(t) :
	if t is None :										# None case
		return("(None)")
	return(time.asctime(t))								# normal case
#
#	class Newsfeed  --  one news feed
#
class Newsfeed(object) :							
	MONTHS = ["ZERO","January", "February", "March", "April", "May", "June", 
		"July", "August", "September", "October", "November"]

	#	FeedParser's list of acceptable HTML elements.
	standard_acceptable_elements = ['a', 'abbr', 'acronym', 'address', 'area', 'b', 'big',
      'blockquote', 'br', 'button', 'caption', 'center', 'cite', 'code', 'col',
      'colgroup', 'dd', 'del', 'dfn', 'dir', 'div', 'dl', 'dt', 'em', 'fieldset',
      'font', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'input',
      'ins', 'kbd', 'label', 'legend', 'li', 'map', 'menu', 'ol', 'optgroup',
      'option', 'p', 'pre', 'q', 's', 'samp', 'select', 'small', 'span', 'strike',
      'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'textarea', 'tfoot', 'th',
      'thead', 'tr', 'tt', 'u', 'ul', 'var']

	#	Our list. We drop almost all markup, then truncate at the first remaining tag.
	acceptable_elements = ['a','p','br']				# severely censor HTML markup

	def __init__(self, url, verbose=False) :
		self.verbose = verbose							# set verbose
		self.setfeedurl(url)							# set feed URL
		self.expirationsecs = 60*60*24*2				# expire after not seen for 2 days
		####print(feedparser._HTMLSanitizer.acceptable_elements)	# ***TEMP***
		feedparser._HTMLSanitizer.acceptable_elements = self.acceptable_elements
		####print(feedparser._HTMLSanitizer.acceptable_elements)	# ***TEMP***
		####self.expirationsecs = 60						# ***TEMP DEBUG***

	def setfeedurl(self, url) :							# set new feed URL
		self.url = url									# save URL
		self.hdrtitle = "???"							# no header title yet
		self.hdrdate = None								# no header date yet
		self.availitems = []							# no items queued for read
		self.etag = None								# no feed sequence id yet
		self.modified = None							# no last-modified timestamp yet
		self.idpreviouslyread = {}						# prevously read item IDs 
		self.textpreviouslyread = {}					# previously read story text
		self.errmsg = None								# no error message

	def getitem(self) :									# get one item
		if len(self.availitems) > 0 :					# if items available
			return(self.availitems.pop(0))				# return first item on list
		self.fetchitems()								# empty, try to fetch more items
		if len(self.availitems) > 0 :					# if items available
			return(self.availitems.pop(0))				# return first item on list
		if self.errmsg :								# if error available
			s = self.errmsg	+ '\n'						# return it
			self.errmsg = None							# use it up
			return(("ERROR", s))						# report error item
		return(None)									# no items

	def markallasread(self) :							# mark all stories as read
		self.availitems = []							# clear list of items
		while self.getitem() :							# use up all items
			self.availitems = []						# clear list of items
			pass

	def gettitle(self) :								# get feed title 
		return(self.hdrtitle)	 
			
	def fetchitems(self) :								# fetch more items from feed source
		try :											# try fetching
			now = time.time()							# timestamp
			d = feedparser.parse(self.url,etag=self.etag,modified=self.modified)	# fetch from URL
			if d.status == 304 :						# if no new items
				if self.verbose :						# if verbose
					print("Feed polled, no changes.")
				return									# nothing to do
			if self.verbose :							# if verbose
				print("Read feed: %d entries, status %s" % (len(d.entries), d.status))
			if d.status != 200 :						# if bad status
				raise IOError("of connection error No. %d" % (d.status,))
			oldetag = self.etag							# save old etag for diagnosis
			oldmodified = self.modified					# save old timestamp for diagnosis
			self.etag = d.etag							# save position in feed for next time
			self.modified = d.modified					# save last update timestamp for next time
			self.hdrtitle = d.feed.title + '\n'			# feed title
			hdrdescription = d.feed.description			# feed description
			hdrdate = "" #### d.feed.date				# date as string
			didentry = False							# found something worth doing
			#	Process all entries in feed just read.
			#	Ignore items that were present in the previous read of this feed.
			for entry in d.entries :					# get items from feed
				entrymsg = self.doentry(entry, now)		# do this entry
				if entrymsg :							# if new item to print
					self.availitems.append(entrymsg)	# save this item
					didentry = True						# found some entry worth doing
			#	Purge stories not seen in a while.
			self.purgeolditems(now-self.expirationsecs,self.idpreviouslyread)	# purge old previousy read stories when expired
			self.purgeolditems(now-self.expirationsecs,self.textpreviouslyread)	# purge old previousy read stories when expired
			if not didentry :							# if found nothing to do
				self.logwarning('Feed stamps changed from ("%s",%s) to ("%s",%s) but no new content.' % 
					(oldetag, strtime(oldmodified), d.etag, strtime(d.modified)))	# note

		###	***Exception handling needs improvement***
		except IOError as message :						# if trouble
			self.errmsg = "No news because " + str(message) + "."
			self.logwarning(self.errmsg)				# log
		except AttributeError as message :				# if trouble
			self.errmsg = "No news because " + str(message) + "."
			self.logwarning(self.errmsg)				# log

	def purgeolditems(self,expirationtime,dict) :			# purge old items already seen and printed
		#	We have to do this the hard way, because stories can appear in the feed, be preempted
		#	by higher priority stories, and reappear later.
		expired = []									# expired items
		for elt in dict :								# for item in dictionary
			if dict[elt] < expirationtime :				# if expired
				expired.append(elt)						# note expired
		for elt in expired :							# for all expired items
			del(dict[elt])								# delete from dict
			if self.verbose :
				print("Expired: %s" % (elt,))			# debug

	def doentry(self,entry, now)	:					# do one feed entry
		title = entry.title								# title of entry
		id = entry.id									# ID of entry
		description = entry.description					# description of entry
		#	Clean up news item.  Should do this via feedparser utilities.
		description = self.cleandescription(entry.description)
		date = entry.date								# date of entry
		dateparsed = entry.date_parsed					# date parsed
			####print("Date parsed: " + str(dateparsed))
		#	Have we read this item already?  Check for duplicates.
		#	If either the ID or the text is duplicated, it's a duplicate.
		#	Sometimes IDs change when the text does not, because of server-side problems.
		seen = id in self.idpreviouslyread				# true if already seen
		self.idpreviouslyread[id] = now					# keep keys of stories read
		if seen :										# if already read
			if self.verbose :
				print("Old feed item: (%s)  %s" % (id,title.encode('ascii','replace')	))			# Note news item
			return(None)								# don't do it again
		textinfo = (title, description)					# check for duplicate text; feed source botches this
		seen = textinfo in self.textpreviouslyread		# already seen?
		self.textpreviouslyread[textinfo] = now			# keep text of stories read
		if seen :										# if already seen
			if self.verbose :
				print("Old feed item: (%s)  %s" % (id,entry.title.encode('ascii','replace')))			# Note news item
			return(False)
		#	New news item, prepare for display
		date_string = self.MONTHS[dateparsed.tm_mon] + " " + str(dateparsed.tm_mday)
		entrymsg = date_string + ": " + title + "\n" + description + '\n\n' # Add CR at end
		if self.verbose :
			print("New feed item: (%s)  %s" % (id,title.encode('ascii','replace')))			# Note news item
		return((self.hdrtitle,entrymsg))

	def cleandescription(self, s)	:			# clean up description for printing
		#	Clean up news item.  Should do this via feedparser utilities.
		####print("Before clean:\n" + s.encode('ascii','replace'))			# ***TEMP***
		s = re.sub(r'<div.*','',s)				# remove Reuters crap at end ***TEMP***
		s = re.sub(r'<a.*','',s)				# remove Reuters crap at end ***TEMP***
		s = re.sub(r'&mdash;','-',s)			# convert HTML escape for mdash
		s = re.sub(r'&\w+;','?',s)				# any other special chars become question mark
		s = re.sub(r'<p>','\n\n',s)				# convert breaks to newlines.
		s = re.sub(r'</p>',' ',s)				# remove closing paragraph tag
		s = re.sub(r'<br>','\n\n',s)			# convert breaks to newlines.
		s = re.sub(r'<br/>','\n\n',s)			# convert breaks to newlines.
		s = re.sub(r'<[^>]*>',' ',s)			# remove any remaining markup
		s = re.sub(r'[\t\r ]+',' ',s)			# all whitespace becomes a single space
		s = re.sub(r'\n[ ]+','\n',s)			# remove whitespace at end of line
		s = re.sub(r'\n\n\n+','\n\n',s)			# never more than two newlines
		####print("After clean:\n" + s.encode('ascii','replace'))				# ***TEMP***
		return(s.strip())						# remove any lead/trail white space

	def logwarning(self, msg) :							# log warning message
		print('WARNING: Feed "%s": %s' % (self.url, msg))	# just print for now
									
#
#	class Newsfeeds  --  handle multiple news feeds
#
class Newsfeeds(object) :
	def __init__(self, feedlist, verbose=False) :
		self.verbose = verbose							# set verbose
		self.feeds = []									# list of feeds
		self.lasttitle = None							# last title returned
		for feedurl in feedlist :
			self.feeds.append(Newsfeed(feedurl,verbose))	# add this feed

	def getitem(self) :									# get one item, from some feed
		for feed in self.feeds :						# try all feeds
			item = feed.getitem()						# get one item
			if item :									# if got an item
				return(item)							# return it
		return(None)									# no new items available

	def setlasttitleprinted(self,title) :
		self.lasttitle = title							# set last title printed

	def getlasttitleprinted(self) :						# get last title printed
		return(self.lasttitle)

	def markallasread(self) :							# mark all stories as read
		for feed in self.feeds :						# try all feeds
			feed.markallasread()						# mark all as read
