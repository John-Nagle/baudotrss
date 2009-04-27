RSS reader for Baudot Teletype machines

Simulates a classic "news ticker", printing current news and weather on old Baudot teletype machines. 
Useful for museum-type demonstration systems. 

Supported hardware: Teletype Models 12, 15, 19, 28.

John Nagle
Animats
April, 2009
License: GPL/LGPL.


This is a Python program for driving classic Baudot teletype machines such as
the Model 15 or Model 28.  It's usable with both KSR machines (with a keyboard)
or RO machines (no keyboard).  

The program connects to RSS feeds and prints them on the Teletype as they are updated.
By default, it connects to the Reuters "Top Stories" feed, which prints about five
lines per news story.  So this is a useful demo program to leave running to drive
a Teletype in a museum situation.  A new story appears about once an hour.  If you
want more typing time, find a more active feed. 

System requirements:
	Computer:			Intel 32-bit, with hardware serial port.  (USB to serial
						converters will usually not work at 45.45 baud.)
	Operating system	Windows 2000/XP. (Should work on Vista and Win7, not tested.)						
	Python system:		2.6 
	Required packages:	win32api
						pyserial
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
						see 
						http://www.animats.com/nagle/aetheric/connecting.html			

System configuration issues:
	If you're running this on a machine with a keyboard, it's useful to configure
	your operating system to turn off the input and output FIFO for the serial port. Otherwise,
	there's a a 4 character time delay built into the serial port, and at 45.45 baud,
	that's a full second. This makes interactive typing very painful.

Installation:
	As yet, there is no installer.  Download the source ".py" and ".bat" files.

Running the program:

Usage: userinterface.py [options] [feedurls]

Options:
  -h, --help            show this help message and exit
  -v, --verbose         Verbose mode
  -k, --keyboard        Keyboard present
  -c COMMAND, --cmd=COMMAND
                        Initial command
  -m, --markread        Mark all stories as read
  -b BAUD, --baud=BAUD  Baud rate
  -p PORT, --port=PORT  Port number (0=COM1)
  -l, --lf              Send LF at end of line
  -a OHDONTFORGETKEY, --ohdontforgetkey=OHDONTFORGETKEY
                        API key for OhDontForget messaging

If "--keyboard" is specified, the Teletype (not the computer) will prompt:

"Type N for news, U for news updates, W for weather, S to send:"

"News" reads the specified RSS feeds, printing any new items as they come in.

"News updates" is the same as "News", but discards all old news first.
So it will print "Waiting for news..." and wait.

"Send" refers to a limited capability for sending SMS messages from the Teletype
keyboard.  This requires requesting an API key from "ohdontforget.com".
We're looking for a better (two way) SMS solution.

"Weather" is currently the weather for San Francisco, CA.
This can be changed in the code at the line

	s = weatherreport.getweatherreport("ca","san_francisco")

Only state/city combinations supported by NOAA will work. 

When the Teletype is prompting for a command, after 30 seconds, it
will print "OFF" and turn off the motor.  Sending a BREAK will wake
it up again. Sending a BREAK when other printing is going on will
stop whatever is happening and prompt for a command.

There is no interactive interface or GUI on the computer.  This program
is normally run in the background.  It will run forever until killed.