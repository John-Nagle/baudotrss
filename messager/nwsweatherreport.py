#
#   nwsweatherreport  --  get and parse weather report from National Weather Service
#
#   Weather reports are in Digital Weather Markup Language, an XML format.  The schema for them is
#   http://graphical.weather.gov/xml/DWMLgen/schema/DWML.xsd
#
import urllib
import urllib2
import BeautifulSoup
import datetime
import calendar
import re
import msgutils
import placenames                       # spell out state
#
#   Constants
#
#   Prototype URL for fetching weather via latitude and longitude
NWSPROTOURL = "http://forecast.weather.gov/MapClick.php?lat=%1.4f&lon=%1.4f&unit=0&lg=english&FcstType=dwml"
#
#   Utility functions
#
def gettextitem(tree, key) :
    """
    Look for <key>text</key> in tree and return simple text.
    """
    item = tree.find(key)                   # find containing XML item
    if not item :                           # if no find
        raise RuntimeError('XML document did not contain an expected "%s" item.' % (key,))
    text = item.find(text=True)             # find text contained in XML item      
    if not text :                           # if no find
        raise RuntimeError('XML document did not contain text for an expected "%s" item.' % (key,))
    return(text.strip())
#
#   class UTC -- a time zone item for UTC
#
#   This is in Python 3.x in a different form, but not in 2.7
#
class UTC(datetime.tzinfo) :
    def utcoffset(self, d) :                # zero offset from UTC
        return(datetime.timedelta(0))
    def dst(self, sink) :                   # no Daylight Savings Time for UTC
        return(None)
        
timezoneutc = UTC()                         # singleton
        
def parseisotime(s) :
    """
    Parse subset of ISO 8601 time format, including time zone.
    
    Result is "aware" datetime object, in UTC.
    """
    s = s.strip()
    datetimepart = s[0:19]                  # extract fixed-length time part (will fail if microseconds)
    offsetpart = s[19:]                     # extract time zone offset
    dt = datetime.datetime.strptime(datetimepart,"%Y-%m-%dT%H:%M:%S")   # datetime, naive.
    if (len(offsetpart) > 0) :              # if have offset
        if offsetpart.upper() == "Z" :      # if Zulu time
            offset == 0
        else :
            fields = re.match(r'([+-])(\d\d):(\d\d)', offsetpart)
            if not fields :
                raise RuntimeError("Unable to parse time string: %s" % (s,))
            sign = fields.group(1)          # + or -
            hours = int(fields.group(2))    # has to be valid number, passed RE
            minutes = int(fields.group(3))
            offset = (hours*60 + minutes)   # compute unsigned value of offset
            if sign == "-" :                # if - sign
                offset = -offset            # invert offset
            #   Now have offset in minutes.  Apply to dt.
        #   Apply time zone offset
        dt -= datetime.timedelta(minutes=offset) # apply offset
        dt = dt.replace(tzinfo=timezoneutc) # make this an "aware" object
    return(dt)
#
#   class nwsperiod 
#
class nwsperiod(object) :
    """
    National Weather Service forecast data for one period
    """
    
    def __init__(self, timeinfo, forecasttext) :
        """
        Set time and text of a forecast
        """
        self.err = None
        self.timeinfo = timeinfo                    # (timestamp, time name)
        self.forecasttext = forecasttext            # text of forecast
        
    def hoursinfuture(self, forecasttime) :
        """
        How far ahead is this forecast looking, in hours?
        """
        timediff = self.timeinfo[0] - forecasttime  # how far ahead is this?
        secsahead = timediff.days * 86400 + timediff.seconds  # seconds ahead
        return (secsahead / 3600.0)                 # hours ahead
        
        
    def asString(self) :
        """
        Display weather forecast for a period as a string
        """
        (timestamp, timename) = self.timeinfo       # unpack time info
        # convert to local time from UTC timestamp
        localforecasttime = datetime.datetime.fromtimestamp(calendar.timegm(timestamp.timetuple()))
        s = msgutils.editdate(localforecasttime)    # date only as "May 1"
        if not timename  :                          # Usually have "Tueseday evening", etc. from NWS
            timename = msgutils.edittime(localforecasttime) # if not, use actual time
        s = timename + ", " + s                     # prefix it to date
        return("%s: %s" % (s, self.forecasttext))   # human-readable string
        
        
#
#   class nwsxml  --  National Weather Service XML in useful format
#
class nwsxml(object) :
    """
    National Weather Service data from XML
    """
    def __init__(self, verbose = False) :
        self.verbose = verbose                  # true if verbose
        self.err = None                         # no errors yet
        self.location = None                    # printable city, state
        self.creationtime = None                # date/time of forecast
        self.latitude = None                    # latitude (string)
        self.longitude = None                   # longitude (string)
        self.perioditems = []                   # forecast items for time periods
        
    def _parseheader(self, tree) :
        """
        Parse forecast header info - location, time, etc.
        """
        #   Make sure this is a proper forecast document
        dwmlitem = tree.find("dwml")                        # should be Digital Weather Markup Language
        if not dwmlitem :                                   # This isn't a valid weather report
            msg = "Weather forecast not found"              # note problem
            titleitem = tree.find("title")                  # probably HTML
            if titleitem :                                  # pull title from HTML if present
                titletext = titleitem.find(text=True)
                if titletext :
                    msg = titletext
            raise RuntimeError(msg)                         # fails
        #   Get creation date/time
        creationitem = tree.find("creation-date")           # timestamp item 
        if not creationitem :
            raise RuntimeError("No forecast creation date found")
        creationtime = creationitem.find(text=True)         # get period text, which is a timestamp
        if creationtime is None :
            raise RuntimeError("No forecast creation date/time")
        self.creationtime = parseisotime(creationtime.strip()) # convert to timestamp
        #   Get location name
        locitem = tree.find("data", type="forecast")        # find forecast item
        if not locitem :
            raise RuntimeError("No forecast data item")
        pointitem = locitem.find("point")                   # point item within forecast
        if not pointitem :
            raise RuntimeError("No location point data item")
        cityitem = locitem.find("city")                     # city item within point
        self.latitude = pointitem["latitude"]               # get fields of interest
        self.longitude = pointitem["longitude"]
        if cityitem :
            state = cityitem['state']
            city = cityitem.find(text=True)                 # get city name
            if not city :
                raise RuntimeError("No city name")
            state = placenames.CODE_STATE.get(state, state) # spell out state name if possible
            self.location = city + ", " + state
        else :                                              # no city, use NWS area description
            areaitem = locitem.find("area-description")     # go for area description
            if not areaitem :
                raise RuntimeError("No city or area item") 
            area = areaitem.find(text=True)                 # "6 Miles ESE Hidden Valley Lake CA"
            if not area :
                raise RuntimeError("No area description")
            print("Area: " + unicode(area))                 # ***TEMP***
            self.location = area                            # use NWS area description
      
    def _parsetimeitems(self, key, timeitems) :
        """
        Parse time items within a time layout.  Return time item list or None
        Time item list is [(timestamp, timeastext),..]
        """
        timeitemlist = []                                   # accumulate time items here
        for timeitem in timeitems :                         # for time items in this set         
            try :
                periodname = timeitem["period-name"]        # get period name
            except KeyError:
                periodname = None                           # OK, no period name.  Some items don't have them
            periodtime = timeitem.find(text=True)           # get period text, which is a timestamp
            if periodtime is None :
                raise RuntimeError("No period date/time in time item")
            if periodtime.strip() == "NA" :                 # if any time not available
                if self.verbose :                           # discard entire time layout
                    print("Found NA item in time item list for key '%s'" % (key,))
                return(None)
            periodtime = parseisotime(periodtime.strip())   # should convert to timestamp
            timeitemlist.append((periodtime, periodname))   # Nth entry for this time layout
        return(timeitemlist)                                # success, have list      
    
    def _parsetimelayouts(self, tree) :
        """
        Find and index time layouts by time layout key.  Returns 
        { key: (perioddatetime, periodname), ... }
        """
        timelayouts = {}                                    # key, parse tree
        timelayouttrees = tree.findAll("time-layout")       # find all time layouts
        for timelayouttree in timelayouttrees :             # for all trees
            keytag = timelayouttree.find("layout-key")      # find layout key
            if keytag is None :
                raise RuntimeError("No 'time-layout' tag found in time layout")
            key = keytag.findAll(text=True)                 # get text
            if key is None or len(key) != 1 :               # must be a single text item
                raise RuntimeError("No time layout key found in time layout")
            key = key[0].strip()                            # clean up key
            timeitemlist = self._parsetimeitems(key, timelayouttree.findAll('start-valid-time'))    
            if timeitemlist :                               # if got list
                timelayouts[key] = timeitemlist             # item for this key
                if self.verbose :
                    print("Time layout '%s': %s" % (key, unicode(timeitemlist)))
        return(timelayouts)
        
    def _parseforecasts(self, tree, timelayouts) :
        """
        Find text forecast.  Each forecast has an associated time layout name.
        The time layout is a separate item which associates timestamps with
        the forecast.
        """
        wordedforecasts = tree.findAll("wordedforecast")    # find forecasts
        if wordedforecasts is None or len(wordedforecasts) == 0 :
            raise RuntimeError("Forecast text not found in data")
        for wordedforecast in wordedforecasts :             # for each forecast
            timelayoutkey = wordedforecast["time-layout"]   # get time layout name
            if timelayoutkey is None :
                raise RuntimeError("Forecast time layout key not found in data")
            forecasttextitems = wordedforecast.findAll("text")  # get text items
            forecasttexts = []                              # text items
            for forecasttextitem in forecasttextitems :     # for all text items
                textparts = forecasttextitem.findAll(text=True) # get all text items
                s = (" ".join(textparts)).strip()           # get all text as one string
                forecasttexts.append(s)                     # save forecast text
            #   Now find matching time layout item for forecast
            timelayoutkey = timelayoutkey.strip()
            if not (timelayoutkey in timelayouts) :         # if time layout not on file for this key
                raise RuntimeError("Time layout key '%s' not found in time layouts" % (timelayoutkey,))
            timelayout = timelayouts[timelayoutkey]         # get relevant layout
            #   The number of time layouts and the number of forecast texts has to match
            if len(timelayout) != len(forecasttexts) :
                if (self.verbose) :
                    print("Time layout: %s" % (unicode(timelayout,)))
                    print("Forecasts: %s" % (unicode(forecasttexts,)))
                raise RuntimeError("Time layout key '%s' has %d forecast times, but there are %d forecasts" %
                    (timelayoutkey, len(timelayout), len(forecasttexts)))
            #   We have a good set of forecasts and time stamps.    
            if self.verbose :
                print("Forecast time layout key %s matches time layout %s" % (timelayoutkey, unicode(timelayout)))          
            for i in range(len(timelayout)) :
                    self.perioditems.append(nwsperiod(timelayout[i], forecasttexts[i]))   # new forecast item

  
        
    def parse(self, tree) :
        """
        Take in BeautifulSoup XML parse tree of XML forecast and update object.
        """
        try :
            #   Get forecast 
            self._parseheader(tree)                         # parse header (location, time, etc.)
            timelayouts = self._parsetimelayouts(tree)      # get time layouts needed to timestamp forecasts
            self._parseforecasts(tree, timelayouts)         # parse forecasts
                
        except (EnvironmentError, RuntimeError) as message :
            self.err = "Unable to interpret weather data: %s." % (message,)
            return
            
        
    def asString(self, hoursahead = 99999999) :
        """
        Return object as useful string.
        
        hoursahead limits how far ahead the forecast will be reported.
        """
        if self.err :
            return("ERROR: %s" % (self.err,))
        if self.verbose :
            print("Forecast creation time: " + self.creationtime.isoformat()) 
        # convert to local time from UTC timestamp
        localforecasttime = datetime.datetime.fromtimestamp(calendar.timegm(self.creationtime.timetuple()))
        timemsg = "%s at %s" % (msgutils.editdate(localforecasttime), msgutils.edittime(localforecasttime))
        s = "Weather forecast for %s on %s.\n\n" % (self.location, timemsg)   # header line
        return(s + "\n\n".join(
            [x.asString() for x in self.perioditems if x.hoursinfuture(self.creationtime) < hoursahead]))
#
#   getnwsforecast -- get National Weather Service forecast for lat, lon
#
#   Synchronous.  Result as text
#
def getnwsforecast(lat, lon, verbose=False) :
    url = NWSPROTOURL % (lat, lon)
    if verbose :
        print("NWS url: %s" % url)          # show URL
    try:
        opener = urllib2.urlopen(url)           # URL opener object 
        xmltext = opener.read()                 # read entire contents
        opener.close()                          # close
        tree = BeautifulSoup.BeautifulStoneSoup(xmltext)
        if verbose :
            print(tree.prettify())              # print tree for debug
        forecast = nwsxml(verbose)              # get new forecast
        forecast.parse(tree)                    # parse forecast
        return(forecast.asString(72))           # return result 
    except IOError as message :                 # if trouble
        s = "Unable to get weather forecast: " + str(message)
        return(s)
 
#
#   getziplatlong --  get latitude and longitude given ZIP code.
#
#   Service by NWS
#
NWSZIPURL = "http://graphical.weather.gov/xml/sample_products/browser_interface/ndfdXMLclient.php?listZipCodeList=%s"
NWSZIPRE = re.compile(r'\s*([+-]?\d+\.\d*)\s*,\s*([+-]?\d+\.\d*)\s*')   # matches 123.45,-345.23
#
#   getziplatlong  
#
def getziplatlong(zip, verbose=False) :
    """
    Get latitude and longitude for a US ZIP code
    
    Uses NWS NDFD service.
    """
    url = NWSZIPURL % (urllib.quote_plus(zip),)
    if verbose :
        print("NWS ZIP lookup url: %s" % (url,))          # show URL
    try:
        opener = urllib2.urlopen(url)           # URL opener object 
        xmltext = opener.read()                 # read entire contents
        opener.close()                          # close
        tree = BeautifulSoup.BeautifulStoneSoup(xmltext)
        if verbose :
            print(tree.prettify())              # print tree for debug
        latlon = gettextitem(tree, "latlonlist")# look for lat lon item
        #   Format of latLon is number, number
        matches = NWSZIPRE.match(latlon)        # looking for 123.45,-345.23
        if not matches :
            raise RuntimeError("ZIP code lookup found no result.")
        lat = matches.group(1)
        lon = matches.group(2)
        return((None, lat, lon))                # returns (msg, lat, lon)
    except (RuntimeError, EnvironmentError) as message :                 # if trouble
        s = "Unable to get location of ZiP %s: %s" % (zip, str(message))
        return((s, None, None))

#        
#   USGS place name lookup
#
USGSGNISURL = "http://geonames.usgs.gov/pls/gnis/x?fname='%s'&state='%s'&cnty=&cell=&ftype='Civil'&op=1"  
#
#   getplacelatlong  
#
def getplacelatlong(city, state, verbose=False) :
    """
    Get latitude and longitude for a US place name.
    
    Uses USGS GINS service.
    """
    state = placenames.CODE_STATE.get(state, state)     # USGS requires state name, not abbreviation 
    url = USGSGNISURL % (urllib.quote_plus(city), urllib.quote_plus(state))
    if verbose :
        print("USGS url: %s" % (url,))          # show URL
    try:
        opener = urllib2.urlopen(url)           # URL opener object 
        xmltext = opener.read()                 # read entire contents
        opener.close()                          # close
        tree = BeautifulSoup.BeautifulStoneSoup(xmltext)
        if verbose :
            print(tree.prettify())              # print tree for debug
        features = tree.findAll("usgs")         # find all USGS features
        bestfeaturename = None                  # pick best match name
        lat = None
        lng = None
        for feature in features :               # find best matching name
            featurename = gettextitem(feature,"feature_name")
            if (bestfeaturename is None or      # pick either first or exact match
                (city.upper() == featurename.upper())) :
                bestfeaturename = featurename
                lat = gettextitem(feature,"feat_latitude_nmbr")
                lng = gettextitem(feature,"feat_longitude_nmbr")
        if bestfeaturename is None :
            raise RuntimeError("City not found")
        return((None, bestfeaturename, lat, lng))

    except (RuntimeError, EnvironmentError) as message :                 # if trouble
        s = "Unable to get location of %s, %s: %s" % (city, state, str(message))
        return((s, None, None, None))
#
#   getweatherreport  -- main interface
#
def getweatherreport(city, state, zip) :
    """
    Get weather report, given city, state, zip info.
    """
    if zip :                                    # if have ZIP code
        (msg, lat, lon) = getziplatlong(zip)    # look up by ZIP code
    elif city and state :                       # look up by city, state
        (msg, place, lat, lon) = getplacelatlong(city, state)
    else :                                      # no location
        msg = "No location configured for weather reports."
    if msg :
        return(msg)
    return(getnwsforecast(float(lat),float(lon)))  # return actual forecast
   
#
#   Unit test
#
#
#   testcity
#
def testcity(city, state, verbose=False) :
    print("Test city: %s, %s." % (city, state))
    loc = getplacelatlong(city, state, verbose)
    (msg, place, lat, lon) = loc
    if msg :
        print("ERROR: " + msg)
    else :
        s = getnwsforecast(float(lat), float(lon), verbose)
        print(s)
    print("")    
#
#   testzip
#
def testzip(zip, verbose=False) :
    print("Test ZIP: %s." % (zip,))
    loc = getziplatlong(zip, verbose)
    (msg, lat, lon) = loc
    if msg :
        print("ERROR: " + msg)
    else :
        s = getnwsforecast(float(lat), float(lon), verbose)
        print(s)
    print("")  
        
if __name__== "__main__" :                      # if unit test 
    lat = 37.7749295                            # San Francisco, CA
    lon= -122.4194155
    s = getnwsforecast(lat, lon, True)
    print(s)
    lat = 38.7749295                            # Near Konocti
    lon = -122.4194155
    s = getnwsforecast(lat, lon, False)
    print(s)
    #   Look up by ZIP
    testzip("22204", True)
    testzip("94062", False)
    #   Look up by city
    testcity("San Francisco", "CA", True)
    testcity("City of San Jose", "CA", True)
    testcity("New York", "NY", False)
    testcity("Athens", "GA", False)
 
