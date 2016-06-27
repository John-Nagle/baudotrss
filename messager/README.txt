RSS reader for Baudot Teletype machines

Simulates a classic "news ticker", printing current news and weather on old Baudot teletype machines. 
Useful for museum-type demonstration systems. 

Supported hardware: Teletype Models 12, 15, 19, 28.

John Nagle
Animats
April, 2009
License: GPL/LGPL.

Update history

Version 2.2:
- Used at Nova Albion Steampunk Exhibition, 2011.

Version 2.3:
- Minor changes only.
- For Clockwork Alchemy Steampunk Exhibition, 2012.
- More robust when network connection fails.  
- Compatible with newer versions of FeedParser.
- Some dead code removed.

Version 2.4:

Version 2.5:
- Weather information now obtained from NWS XML feed instead of
  discontinued NWS feed sites.
- Add support for ITA2 character set.
- Detects Internet connections stuck at WiFi logon pages.

Version 2.6:
- Avoids printing news items more than once, even if their timestamp changes.
- For machines with no keyboard, BREAK is now recognized, and will restart the
  news feeds from the beginning.
  
Version 2.9:
- Google Voice support removed due to Google changes to service.

Version 2.10:
- Code modernization
  - Support for Python 2.6 dropped.
  - Uses "bs4" library package rather than its own copy of BeautifulSoup.
  - Compatible with current version of "pyserial".
  
Version 3.0:
- Support for Python 2.7 and Python 3.
- Tested on both Windows 7 and Xubuntu.
- Removed dependency on lxml parser to ease installation.
  

