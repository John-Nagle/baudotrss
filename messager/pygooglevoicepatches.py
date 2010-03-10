#
#	Temporary fixes to PyGoogleVoice to allow reading more than one page from input.
#
#	These are TEMPORARY FIXES until something better can be implemented by the project developer.
#
#	Apply to pygooglevoice 0.5 only.
#
#	John Nagle
#	January, 2009
#	nagle@animats.com
#
import googlevoice
from googlevoice.util import *
settings = googlevoice.settings
log = googlevoice.voice.log

#
#	Replacing voice.py / __do_page:
#
def do_page(self, page, data=None, headers={}):
        """
        Loads a page out of the settings and pass it on to urllib Request
        """
        ####print("PATCHED version of __do_page")		# ***TEMP***
        page = page.upper()
        doget = False								# do POST or GET?
		#	Hokey fix.  if this is a request for a second page, do a GET, not a POST
        if page in ('DOWNLOAD','XML_SEARCH') or (isinstance(data,dict) and "page" in data) :
            doget = True    
        if isinstance(data, dict) or isinstance(data, tuple):
            data = urlencode(data)
        headers.update({'User-Agent': 'PyGoogleVoice/0.5'})
        if log:
            log.debug('%s?%s - %s' % (getattr(settings, page)[22:], data or '', headers))
        if doget :									# if doing GET, not POST
            url = getattr(settings, page)			# construct URL
            if data != "" :							# if URLencoded data
                url += "?" + data					# append, with preceding "?"
            return urlopen(Request(url, None, headers))
        if data:
            headers.update({'Content-type': 'application/x-www-form-urlencoded;charset=utf-8'})
        return urlopen(Request(getattr(settings, page), data, headers))
#
#	Replacing util.py / __call__:
#
def call(self):
        ####print("PATCHED version of __call__")	#### ***TEMP***
        self.json, self.html = '',''
        parser = ParserCreate()
        parser.StartElementHandler = self.start_element
        parser.EndElementHandler = self.end_element
        parser.CharacterDataHandler = self.char_data
        data = self.datafunc()			# fetch data outside try block, so network exceptions propagate
        try:
            parser.Parse(data, 1)
        except:
            raise ParsingError			# parsing errors only, not HTTP errors
        return self.folder

#	
#	Apply patches, replacing functions within pygooglevoice
#
googlevoice.Voice._Voice__do_page = do_page
googlevoice.util.XMLParser.__call__ = call

#
#	fetchfolderpage  --  workaround for "pygooglevoice" issue #22
#
#	Google Voice folders are returned 10 entries at a time, so getting them all requires
#	multiple reads
#
def fetchfolderpage(voice, pagetype, pagenumber=1) :	# fetch page N (starting from 1) of inbox
	params = None										# params for fetching page, if any
	if pagenumber > 1 :									# if not first page, must put page number in URL
		params = {'page' : "p" + str(pagenumber)}		# get page "p2", etc.
	xmlparser = voice._Voice__get_xml_page(pagetype, params)	# violate class privacy per developer instructions
	return (xmlparser)									# return XML parser object			
