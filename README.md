# baudotrss
BaudotRSS - RSS and SMS support for antique 5-bit Teletype machines
RSS reader for Baudot Teletype machines

Simulates a classic "news ticker", printing current news and weather on old Baudot teletype machines. 

See it in action: https://www.youtube.com/watch?v=6F_hhp4nCHE
 

Supported hardware: Teletype Models 12, 15, 19, 28.

John Nagle

The Aetheric Message Machine Company, Ltd. http://www.aetherltd.com

April, 2009

License: GPL/LGPL.

For update history see README.txt in "messager".
Moved from SourceForge to GitHub in Febuary, 2016.


This is a Python program for driving classic Baudot teletype machines such as
the Model 15 or Model 28.  It's usable with both KSR machines (with a keyboard)
or RO machines (no keyboard).  It's been used at seven major steampunk conventions since
2009.

The program connects to RSS feeds and prints them on the Teletype as they are updated.
By default, it connects to the Reuters "Top Stories" feed, which prints about five
lines per news story.  So this is a useful demo program to leave running to drive
a Teletype in a museum situation.  A new story appears about once an hour.  If you
want more typing time, find a more active feed. 

The program supports connection to a web server which receives SMS messages from
Twilio and relays them to this program.  The server code is not part of this package.
However, if you configure a Twilio account, you can send SMS from the Teletype keyboard.

System requirements:

	Computer:		Intel 32-bit, with hardware serial port.  (USB to serial
                    converters will usually not work at 45.45 baud.)
	Operating system	Windows 7 / Linux.
	Python system:		2.7 or 3.x
	Required packages:	beautifulsoup4
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
						see http://www.aetherltd.com".
						
    For sending SMS messages:
                        An account with Twilio.
                        
    For receiving SMS messages:
                        A server which supports our message API. 
    	
								

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

A configuration file must be created, with at least the "port" and "baud" parameters
in the [teletype] section.  Use "configsample.cfg" as a prototype and edit it.

If you use a port name of "TEST", the program will print to the computer console
window and accept input from it.  This allows test operation without a real Teletype.

Installation (Linux)
	
    Unpack distribution into an empty directory.

Running the program:

    ./runbaudotrss.sh [options] [configfiles] [feedurls]
    
or

    python3 baudotrss.py [options] [configfiles] [feedurls]

(Python 2.7 will work, if necessary.)
    
The "runbaudotrss.sh" script is a convenience for running 
the program from a startup icon.

    Usage: baudotrss.py [options] [configfiles] [feedurls]
    
    
    
Installation (Windows 7) (May work on Windows XP; untested)

    Download "baudotrss.exe". No Python installation is required.
    
Running the program:

    baudotrss.exe [options] [configfiles] [feedurls]
    

Main options:

   -h, --help            show help message and exit
   --ryrypat             Prints RYRYRYRY... forever, for testing
   --alphapat            Prints ABCDEFG... forever, for testing
   --verbose             More debug output from program

With no options, the program will send a Reuters news feed to the
first available serial port at 45.45 baud in Baudot.
  
The program is configured by creating a text file ending in ".cfg",
and naming it on the command line.  The default configuration is
in "configdefault.cfg", and comments there show the format of a
config file.  Any item in a user-provided config file overrides the
default values. 

The most important configuration options are in the [teletype] section:

    [teletype]                  # Machine params
    #   Serial port - either /dev/usbxxx on Linux, or number (1=COM1:, etc) on Windows
    #   Or TEST, for a demo without a real Teletype connected.
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

"Send" refers to sending SMS messages.  A Twilio account is
required for this feature.  Its authorization inof must be specified with
in the configuration file.

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
is normally run in the background.  It will run forever until killed
with control-C.
