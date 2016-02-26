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


This is a Python program for driving classic Baudot teletype machines such as
the Model 15 or Model 28.  It's usable with both KSR machines (with a keyboard)
or RO machines (no keyboard).  

The program connects to RSS feeds and prints them on the Teletype as they are updated.
By default, it connects to the Reuters "Top Stories" feed, which prints about five
lines per news story.  So this is a useful demo program to leave running to drive
a Teletype in a museum situation.  A new story appears about once an hour.  If you
want more typing time, find a more active feed. 

The program supports connection to a web server which receives SMS messages from
Twilio and relays them to this program.  The server code is not part of this package.

System requirements:
	Computer:			Intel 32-bit, with hardware serial port.  (USB to serial
						converters will usually not work at 45.45 baud.)
	Operating system	Windows 7/Linux. 						
	Python system:		2.6 or 2.7 (No 3.x yet.)
	Required packages:	win32api
						pyserial
						feedparser
	Baudot teletype:	Model 15, 19 or 28 in proper working condition.
						Communications font, not weather font.
						Default baud rate is 45.45 baud.
						The program will work with or without unshift-on-space. 
						The program assumes automatic LF on CR.  If all the lines
						are typing on top of each other, add the "--lf" flag
						on the command line. 
						If a power relay is attached to the RTS line from the serial
						port, the Teletype motor will be turned on and off at
						the appropriate times.   
						
						For information on interfacing a current-loop Teletype to a PC,
						see http://www.aetherltd.com"			

System configuration issues:
	If you're running this on a machine with a keyboard, it's useful to configure
	your operating system to turn off the input and output FIFO for the serial port. Otherwise,
	there's a a 4 character time delay built into the serial port, and at 45.45 baud,
	that's a full second. This makes interactive typing very painful.

	USB to serial devices require special handling, as most will not run at 45.45 baud.
	Some will.  See "http://www.aetherltd.com/connectingusb.html".  Some USB to
    serial devices must be configured to run at a false baud rate.  For the device
    we use, the baud rate in the configuration file is set to 600 baud (an othewise
    unused value) and the device runs at 45.45 baud.  
    
    The file "configdefault.cfg" is a default configuration file, and documents the
    available parameters.  If a second configuration file with a name ending in .cfg
    is specified on the command line, items there override the defaults.

Installation:
	Usual setup.py rules apply.

Running the program:

Usage: baudotrss.py [options] [configfiles] [feedurls]

Options:
  -h, --help            show this help message and exit
  Do this to get the rest of the options.

  With no options, the program will send a Reuters news feed to the
  first available serial port at 45.45 baud in Baudot.
  
The program is configured by creating a text file ending in ".cfg",
and naming it on the command line.  The default configuration is
in "configdefault.cfg", and comments there show the format of a
config file.  Any item in a user-provided config file overrides the
default values. 

The most important configuration options are in the [teletype] section:

   [teletype]                  # Machine params
   #   Serial port - either /dev/usbxxx on Linux, or number (0=COM1:, etc) on Windows
   # port: 2
   #   Baud rate - Our USB interface, when set to 600 baud, runs at 45 baud.
   baud: 600

Those have to be right or nothing useful will happen.  "baud" should
be set to 45 for a 60-speed machine on a classic PC serial port.
We use 600 baud with our specially configured USB to serial converter.

   #    Typebar character set: USTTY, ITA2, or FRACTIONS
   charset: USTTY

Most Model 15 and 28 machines are USTTY.  Western Union machines
may be ITA2. 

   #   Keyboard - true if keyboard present on TTY.  False for RO machines.
   keyboard: True    
 
If a keyboard is configured, the Teletype (not the computer) will prompt:

"Type N for news, W for weather, S to send, O for off, or CR:"

"News" reads the specified RSS feeds, printing any new items as they come in.

"News updates" is the same as "News", but discards all old news first.
So it will print "Waiting for news..." and wait.

"Send" refers to sending SMS messages.  A Google Voice account is
required for this feature.  Its username and password must be specified with
"username" and "password" options in the configuration file.

There is also support for a Twilio SMS gateway, but this requires 
a Twilio account, a web hosting account, and some server side software
not included here.  

"Weather" is currently the weather for San Jose, CA
This can be changed in the configuration file.  Most named
places in the United States will work, but places without
unique names may not look up correctly.  It's usually easier
to specify the ZIP code in the "[weather]" section.  This
overrides any named city and state. 

"Off" shuts down any Teletype activity, until a BREAK is sent
to wake things up.  The program can sit indefinitely in OFF state
waiting for a BREAK.  

When the Teletype is prompting for a command, after 30 seconds, it
will print "WAITING" and turn off the motor.  Sending a BREAK will wake
it up again. Sending a BREAK when other printing is going on will
stop whatever is happening and prompt for a command.

Without a keyboard, the program will print the latest news, then
wait for further news updates.  If a BREAK is sent when no keyboard is 
configured, the printing of news starts again from the beginning.  
This is a good demo mode for receive only machines. 

If the program has a problem connecting to the Internet, the
problem will be reported on the Teletype, with three bells at
the beginning of the message.  The error message will be repeated
every two minutes until the problem is resolved.   

There is no interactive interface or GUI on the computer.  This program
is normally run in the background.  It will run forever until killed.