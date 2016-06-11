#
#    baudotrss.py  --  keyboard-based user interface for Baudot teletype.
#
#    Python 2.6 or later.
#
#    Main program for news and weather display on Teletype
#
#    License: GPL.
#
#    John Nagle
#    January, 2011
#
#
#    Constants
#
DEFAULTCONFIG = "configdefault.cfg"             # default config values.
READTIMEOUT = 1.0              # read timeout - makes read abort (control-C) work on Linux.

import sys
assert(sys.version_info >= (2,7))               # Requires Python 2.7 or later.
import traceback
import warnings
import logging
import optparse
import userinterface
import configparser
import baudottty


#
#    Suppress deprecation warnings.  We know feedparser and BeautifulSoup need updates.
#
warnings.filterwarnings(action='ignore', category=DeprecationWarning, module='BeautifulSoup')
warnings.filterwarnings(action='ignore', category=DeprecationWarning, module='feedparser')

#
#   opentty  --  create and open the TTY device
#
def opentty(port, baud, lf, extraltrs, charset) :
    extraltrs = min(10,max(1,extraltrs))        # sanity check
    tty = baudottty.BaudotTTY()                 # get a TTY object
    tty.open(port, baud, charset, READTIMEOUT)  # initialize a TTY on indicated port
    tty.eolsettings(lf, extraltrs)              # set end of line defaults
    return(tty)                                 # a BaudotTTY object

#
#   testpattern  -- print dumb test pattern forever
#
def testpattern(tty, options) :
    if options.alphapat :
        pat = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-$!&#'()\"/:;?,.\a\n"
    else :
        pat = "RY"                              # RYRYRYRY.... 
    while True :                                
        tty.doprint(pat)                        # print pattern forever
#
#    Main program
#
def main() :
    #    Handle command line options
    opts = optparse.OptionParser()                          # get option parse
    opts.add_option('-v', '--verbose', help="Verbose mode", action="store_true", default=False, dest="verbose")
    opts.add_option('-q', '--quiet', help="Quiet mode", action="store_true", default=False, dest="quiet")
    opts.add_option('-c', '--cmd', help="Initial command",dest="cmd",metavar="COMMAND")
    opts.add_option('-t', '--ryrypat', help="Print RYRY only.", action="store_true", 
        default=False, dest="ryrypat")
    opts.add_option('-a', '--alphapat', help="Print alphabet only.", action="store_true", 
        default=False, dest="alphapat")
    (options, args) = opts.parse_args()                     # get options
    #    Set up logging
    logging.basicConfig()                                   # configure logging system
    logger = logging.getLogger('Messager')                  # main logger
    if options.verbose :
        logger.setLevel(logging.DEBUG)                      # -v: very verbose
    elif options.quiet :
        logger.setlevel(logging.WARNING)                    # -q: errors only
    else :
        logger.setLevel(logging.INFO)                       # none: info messages

    try:         
        #   Process config files if present.
        #   There is a default config file, which can be overridden.
        configfiles = [DEFAULTCONFIG]                       # default
        feedurls = []
        for arg in args :                                   # file args
            if arg.lower().endswith(".cfg") :               # if config
                configfiles.append(arg)                     # use
            elif arg.lower().startswith("http") :           # if URL
                feedurls.append[arg]                        # is feed
            else :                                          # bad args
                raise(ValueError(
                'Command line "%s" should be a feed URL or a config file.' 
                % (arg,)))
        config = configparser.ConfigParser()            # read config file
        logger.info('Configuration from "%s"' % 
            ('", "'.join(configfiles)))                 # source of config
        config.read(configfiles)                        # fetch configs
        #   Get params
        if options.verbose :                            # dump config
            logger.debug("Configuration: ")
            for section in config.sections() :          # dump section
                logger.debug(" [%s]" % (section,))
                for (k,v) in config.items(section) :
                    logger.debug('   %s: "%s"' % (k,v))
                    
        #   Get mandatory parts of configuration    
        baud = config.getint("teletype", "baud")            # baud rate
        port = config.get("teletype", "port")               # serial or USB port
        if port.isdigit() :                                 # no longer allowed, pyserial change
            raise ValueError('Configuration error: "port" must be a name, such as COM1 or /dev/ttyUSB0')
        charset = config.get("teletype", "charset")         # USTTY, ITA2 or Fractions
        #   Get list of feeds from config
        for (k, v) in config.items("feeds") :               # get more from config
            if v and v.strip() != "" :                      # if non-null feed
                feedurls.append(v)                          # add feeds
        #    Startup messages
        logger.info("Options: " + repr(options))
        logger.info("Args: " + repr(args))                        
        logger.info("News feeds: %s" % (str(feedurls),))    # news feeds
        logger.info("Using port %s at %s baud." % (port, str(baud)))
        #   Try to open serial port to Teletype
        extraltrs = config.getint("teletype", "extraltrs")  # extra LTRS at EOL
        lf = config.getboolean("teletype","lf")             # LF on CR teletype feature
        tty = opentty(port, baud, lf, extraltrs, charset)   # open serial port, can raise
        logger.debug("Serial port: " + repr(tty.ser))       # print serial port settings
        if options.ryrypat or options.alphapat :            # if test pattern only       
            testpattern(tty, options)                       # just do dumb test pattern
            return                                          # and exit
        ui = userinterface.simpleui(tty, feedurls, config, logger) # user interface
        ui.feeds.markallasread("NEWS")                      # mark all news as read
    except (configparser.Error, ValueError) as message :
        print("\n\nConfiguration error - cannot start.\n%s" % (str(message),))
        return(1)
    except EnvironmentError as message :
        print("\n\nUnable to open serial port - cannot start.\n%s" % (str(message),))
        return(1)
    try: 
        ui.runui(options.cmd)                               # run the user interface
        return(0)
    except Exception as message :                           # any trouble
        traceback.print_exc()
        print("\n\n-----PROGRAM TERMINATED-----\n%s\n" % (str(message),))
        return(1)

main()                                                      # start program

