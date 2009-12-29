#
#	newsfeed.py  -  fetch news feed via Atom/RSS
#
#	John Nagle
#	February, 2009
#
#	Polls multiple RSS feeds, returns new items.
#
#	Usage: create a Newsfeeds object, and provide it with a list
#	of RSS URLs.  Run via "start" in feedmanager.  Get items
#	using queue in feedmanager.
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
import feedmanager
import Queue
#
#	Constants
#
kpollinterval = 90.0									# poll this often
#
#	class Newsfeed  --  one news feed
#
class Newsfeed(feedmanager.Feed) :							

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
	#
	#	Called from outside the thread
	#
	def __init__(self, url, verbose=False) :
		feedmanager.Feed.__init__(self, "NEWS", verbose)
		self.setfeedurl(url)							# set feed URL
		self.expirationsecs = 60*60*24*2				# expire after not seen for 2 days
		####print(feedparser._HTMLSanitizer.acceptable_elements)	# ***TEMP***
		feedparser._HTMLSanitizer.acceptable_elements = self.acceptable_elements
		####print(feedparser._HTMLSanitizer.acceptable_elements)	# ***TEMP***
		####self.expirationsecs = 60						# ***TEMP DEBUG***

	def setfeedurl(self, url) :							# set new feed URL
		self.url = url									# save URL
		self.hdrtitle = None							# no header title yet
		self.hdrdate = None								# no header date yet
		self.etag = None								# no feed sequence id yet
		self.modified = None							# no last-modified timestamp yet
		self.itemqueued = {}							# item has been queued for printing
		self.markingallasread = True					# marking all stories as read.

	def markallasread(self) :							# mark all stories as read
		try: 
			while True :								# drain
				self.inqueue.get_nowait()				# get input, if any
		except Queue.Empty:								# when empty
			pass										# done
		if self.verbose :
			print("News feed queue emptied.")
		self.markingallasread = True					# mark all as read for one cycle			

	def unmarkallasread(self) :							# clear items already read
		self.markingallasread = False					# do not mark all as read
		self.itemqueued = {}							# no item has been queued for printing
		self.modified = None							# no last-modified date
		self.etag = None								# no previous RSS read
		self.forcepoll()								# force an immediate poll

	def gettitle(self) :								# get feed title 
		if self.hdrtitle :
			return(self.hdrtitle)
		else:
			return(self.url)							# use URL if unable to read

	def getpollinterval(self) :							# how often to poll
		return(kpollinterval)

	def itemdone(self, item) :							# done with this item - item printed
		pass											# we don't keep persistent state of news printed

	def formattext(self, msgitem) :						# format a msg item, long form
		emsg = msgitem.errmsg
		date_string = time.strftime("%B %d, %I:%M %p", msgitem.msgtime)	# formatted time
		#	Format for printing as display message
		if emsg :										# short format for errors
			s = "%s: %s\n" % (date_string, emsg)
			return(s)									# return with error msg
		#	Long form display
		s = msgitem.subject + '\n(' + date_string + ')\n' + msgitem.body + '\n\n' # Add CR at end
		return(s)										# no error

	def summarytext(self, msgitem) :
		emsg = msgitem.errmsg
		#	Format for printing as short message
		if emsg :										# short format for errors
			s = "%s: %s\n" % (msgitem.msgtime, emsg)
			return(s)									# return with error msg
		date_string = time.strftime("%B %d, %I:%M %p", msgitem.msgtime)	# formatted time
		fmt = "FROM %s  TIME %s: %s"
		s = fmt % (msgitem.msgfrom, date_string, msgitem.body[:40])
		return(s)										# no error


	#
	#	Called from within the thread
	#		
	def fetchitems(self) :								# fetch more items from feed source
		try :											# try fetching
			now = time.time()							# timestamp
			d = feedparser.parse(self.url,etag=self.etag,modified=self.modified)	# fetch from URL
			if d is None or not hasattr(d,"status") :	# if network failure
				raise IOError("of network or news source failure")
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
			self.hdrtitle = d.feed.title				# feed title
			hdrdescription = d.feed.description			# feed description
			hdrdate = "" #### d.feed.date				# date as string
			#	Process all entries in feed just read.
			#	Ignore items that were previously seen
			for entry in d.entries :					# get items from feed
				msgitem = self.doentry(entry, now)		# do this entry
				if msgitem :							# if new item to print
					self.inqueue.put(msgitem)			# save this item
			self.markingallasread = False				# if marking all as read, stop doing that.
			#	Purge stories not seen in a while.
			self.purgeolditems(now-self.expirationsecs, self.itemqueued)	# purge old previousy read stories when expired

		except (IOError, AttributeError) as message :	# if trouble
			errmsg = 'No "%s" news because %s.' % (self.gettitle(), str(message))
			self.logerror(errmsg)						# log

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
		msgitem = feedmanager.FeedItem(self, self.gettitle(), dateparsed, dateparsed, title, description)
		#	Have we read this item already?  Check for duplicates.
		#	If either the ID or the text is duplicated, it's a duplicate.
		#	Sometimes IDs change when the text does not, because of server-side problems.
		seen = msgitem.digest in self.itemqueued 		# true if already seen
		if self.markingallasread :						# if marking all as read
			seen = True									# pretend we've seen this story
		self.itemqueued[msgitem.digest] = now			# keep keys of stories read
		if seen :										# if already seen
			if self.verbose :
				print("Old feed item: (%s)  %s" % (id, title.encode('ascii','replace')))			# Note news item
			return(None)
		#	New news item, prepare for display
		if self.verbose :
			print("New feed item: (%s)  %s" % (id,title.encode('ascii','replace')))		# Note news item
		return(msgitem)									# build and return new item

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

	def logwarning(self, errmsg) :							# log warning message
		print('WARNING: Feed "%s": %s' % (self.url, errmsg))# just print for now

	def logerror(self, errmsg) :							# log warning message
		print('ERROR: Feed "%s": %s' % (self.url, errmsg))# just print for now
		if self.inqueue.empty () :							# only add error if empty.  Will repeat if problem
			dateparsed = time,localtime()					# error is now
			newitem = feedmanager.FeedItem(self, self.gettitle(), dateparsed, dateparsed, None, None, errmsg)
			self.inqueue.put(newitem)						# add to output queue

									
