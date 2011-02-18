#
#    weatherreport.py  -  fetch US weather report from NOAA
#
#    John Nagle
#    February, 2009
#
#    License: LGPL
#
#    Simplistic weather report retrieval via FTP.
# 
#
import urllib2
import re
#
baseurl = "ftp://tgftp.nws.noaa.gov/data/forecasts/city/"    # base URL to read
#
#    getweatherreport  --  get weather report as concise ASCII string
#
def getweatherreport(statecode, cityname):
    statecode = statecode.strip().lower()
    cityname = cityname.strip().lower()
    url = baseurl + statecode + '/' + re.sub(' ','_',cityname) + '.txt' # build URL to open
    try:
        opener = urllib2.urlopen(url)           # URL opener object 
        s = opener.read()                       # read entire contents
        opener.close()                          # close
        ####print(s)                                # ***TEMP***
        return(s)                               # return result
    except IOError as message :                 # if trouble
        s = "Unable to get forecast for " + cityname + "(" + statecode + "): " + str(message)
        return(s)

