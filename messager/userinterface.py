#
#    userinterface.py  --  keyboard-based user interface for Baudot teletype.
#
#    Python 2.6 or later.
#
#    User interface for news and weather display on Teletype
#
#    License: GPL.
#
#    John Nagle
#    February, 2009
#
import sys
assert(sys.version_info >= (2,6))           # Requires Python 2.6 or later.
import socket
import serial                               # PySerial
import baudot                               # baudot charset info
import threading
import baudottty
import nwsweatherreport                     # weather report
import newsfeed
import twiliofeed
import feedmanager
import time
import re
from six.moves import queue                 # Python 2/3 support
import traceback

#
#    Globals
#
DEFAULTCONFIG = "configdefault.cfg"

LONGPROMPT =    "\nType N for news, W for weather, S to send, O for off, CR to wait: "
SHORTPROMPT =    "\nN, W, S, O, or CR: "
CUTMARK = "\n\n--- CUT HERE ---\n\n"                # cut paper here
EJECTSTR = "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"   # paper eject sequence

ERRBELLS = "\a \a \a"                               # ring 3 slow bells on error
EXPANDESCAPESDICT = {"\\a": "\a", "\\n" :"\n" }     # useful escapes to expand

DEFAULTSOCKETTIMEOUT = 60*2                         # 2 minute socket timeout
#
#   expandescapes  
#
def expandescapes(s) :
    """
    Expand backslash escapes in strings.
    """
    return(re.sub(r'\\.',lambda x : EXPANDESCAPESDICT.get(x.group(0),x.group(0)), s))
    
#
#    printweather
#
def printweather(ui) :
    (state, city, zip) = ui.weathercity     # get city and state
    s = nwsweatherreport.getweatherreport(city, state, zip)
    s = ui.tty.convertnonbaudot(s)          # convert special chars to plausible equivalents
    s = baudottty.wordwrap(s)               # word wrap
    ui.tty.doprint(s)
    ui.tty.doprint("\n\n\n")
#
#    formatforsms  -- format text with SMS conventions.
#
#    Upper case first letter, and first letter after each period or question mark
#
def formatforsms(s) :
    uc = True                                               # Upper case if on
    out = ""                                                # accum output string here
    for ch in s :                                           # for all chars
        if ch in [".", "!", "?"] :                          # These characters force upper case.
            uc = True
        elif uc and not ch.isspace() :                      # if upper case mode and not space
            ch = ch.upper()                                 # make upper case
            uc = False                                      # once only
        else :
            ch = ch.lower()                                 # otherwise lower case
        out += ch
    return(out)
#
#    sendviasms  -- send SMS message
#
re1 = re.compile(r'\D')                                     # recognize non-digits
#
def sendviasms(ui) :
    ui.logger.debug("Beginning SMS message entry.")
    tty = ui.tty
    if ui.smsmsgfeed is None :
        tty.doprint("\a" + "NO MESSAGING ACCOUNT, CANNOT SEND." + '\n')        # print reply
        return                                              # can't do that
    numchars = ['0','1','2','3','4','5','6','7','8','9','0','.','-']    # acceptable in phone number
    sendto = ui.prompt("To No.: ",numchars,25)
    if sendto is None :                                     # if no message
        ui.logger.info("SMS send phone number is empty.")
        return                                              # ignore
    #    Check for reply to number from previous message
    if len(sendto) == 1 and sendto[0] in ['.','-'] : 
        if ui.smsmsgfeed.msgfrom : 
            sendto = ui.smsmsgfeed.msgfrom                  # use previous number
            tty.doprint("To No.: " + sendto + "\n")         # show number being sent to
        else :
            tty.doprint("\aThere is no message to which to reply.\n")
            return
    sendto = re1.sub('',sendto)                             # remove any non-digit chars
    if len(sendto) < 7 :                                    # if too short
        ui.logger.info('SMS phone number "%s" too short.' % (sendto,))
        return                                              # ignore
    sendtext = None                                         # no text yet
    while True :                                            # accumulate text
        s = ui.prompt(": ",None,70)                         # get text line
        if s is None :                                      # if no message
            ui.logger.debug('SMS send text is empty. (1)')
            return
        if s == '' :                                        # if blank line
            break                                           # done
        if sendtext is None  :                              # if first line
            sendtext = s                                    # now we have a string
        else :
            sendtext += '\n' + s                            # accum lines
    if sendtext is None :                                   # if nothing to send
        ui.logger.info("SMS send text is empty.")
        return
    sendtext = formatforsms(sendtext)                       # apply upper/lower case SMS conventions
    ui.logger.info("Sending to %s: %s" % (sendto, sendtext))    # logging
    reply = ui.smsmsgfeed.sendSMS(sendto, sendtext)
    if reply is None :                                      # if no error
        reply = "DONE"                                      # although sender says OK even when number not validated
    tty.doprint("\n" + reply + '\n')                        # print reply    


#
#    Very simple user interface for testing.
#
#
#    uireadtask -- task to read from serial port
#
class uireadtask(threading.Thread) :

    instate = (PRINTING, FLUSHING, READING) = range(3)      # input state
    inidlesecs = 0.3                                        # 500ms of idle means flushing is done
    #
    #    Called from outside the thread
    #

    def __init__(self, owner) :
        threading.Thread.__init__(self)                     # initialize base class
        self.owner = owner                                  # BaudotTTY object to use
        self.instate = self.PRINTING                        # initially in PRINTING state
        self.aborting = False                               # external request to terminate
        self.statelock = threading.Lock()                   # lock on read state
        self.lastread = time.time()                         # time last char read

    def abort(self) :                                       # terminate this task
        if not self.is_alive() :                            # if not started
            return                                          # no problem.
        self.aborting = True                                # abort this task at next read timeout
        self.join(10.0)                                     # wait for thread to finish
        if self.is_alive() :
            raise RuntimeError("INTERNAL ERROR: read thread will not terminate.  Kill program.")

    #
    #    Called from within the thread.
    #

    #
    #    Read thread.  Stops anything else going on, echoes input.
    #
    #    Nulls are not echoed, because two nulls will trip the "Send/Receive" lever to "Receive",
    #    and we use NULL for a backspace key.
    #
    #   If no keyboard is present, all this does is sense "break", which will redo the previous command.
    #   So RO machines will reprint news if a BREAK button is sent. 
    #   Continuous breaks are ignored.
    #
    def run(self) :
        try :
            self.dorun()                                    # do run thread
        except serial.SerialException as message :          # trouble
            self.owner.logger.error("Connection to Teletype failed: " + str(message))
            self.owner.inqueue.put(message)                 # put exception on output queue to indicate abort
            return                                          # read task ends
        except Exception as message :                       # trouble
            self.owner.logger.exception("Internal error in read thread: " + str(message))
            self.owner.inqueue.put(message)                 # put exception on output queue to indicate abort
            return                                          # read task ends

    def dorun(self) :                                       # the thread
        self.owner.logger.debug("Starting read thread.")    # reading starts
        tty = self.owner.tty                                # the TTY object
        halfduplex = self.owner.halfduplex                  # true if half duplex
        if halfduplex :                                     # in half duplex
            shift = tty.outputshift                         # get shift from output side to start.
        while not self.aborting :                           # until told to stop
            s = tty.readbaudot()                            # get some input
            if len(s) == 0 :                                # timeout
                continue                                    # do nothing
            for b in s :
                istate = self.flushcheck()                  # do flushing check
                if istate != self.READING :                 # if not reading
                    if b == baudot.Baudot.NULL :            # if received a NULL when not reading
                        self.owner.logger.info("BREAK detected")            # treat as a break
                        tty.flushOutput()                   # Flush whatever was printing
                        break                               # ignore remaining input
                    else :                                  # non-break while printing
                        self.owner.logger.debug("Ignoring input.")
                        continue                            # usually means half-duplex echoing back
                shift = tty.writebaudotch(None, None)       # get current shift state
                if shift is None :                          # if none
                    shift = baudot.Baudot.LTRS              # assume LTRS
                if not (b in [baudot.Baudot.NULL, baudot.Baudot.LF]) :     # if not (null or LF), echo char.
                    if halfduplex :
                        #    Update shift in half duplex.  This needs to be synched better between input and output.
                        if b == baudot.Baudot.LTRS :        # if LTRS
                            shift = baudot.Baudot.LTRS      # now in LTRS
                        elif b == baudot.Baudot.FIGS :      # if FIGS
                            shift = baudot.Baudot.FIGS      # now in FIGS
                    else :
                        shift = tty.writebaudotch(b, shift) # write to tty in indicated shift state
                ch = tty.conv.chToASCII(b, shift)           # convert to ASCII
                self.owner.logger.debug("Read %s" % (repr(ch),))
                if not (b in [baudot.Baudot.LTRS, baudot.Baudot.FIGS]) : # don't send shifts in ASCII
                    self.owner.inqueue.put(ch)              # send character to input
        #    Terminated
        self.aborting = False                               # done, reset termination

    def acceptinginput(self, ifreading) :                   # is somebody paying attention to the input?
        with self.statelock :                               # lock
            if ifreading :                                  # if switching to reading
                if self.instate == self.PRINTING :          # if in PRINTING state
                    self.instate = self.FLUSHING            # go to FLUSHING state
                    self.owner.logger.debug("Start flushing input.")    # Input now being ignored, to allow half duplex.
            else :                                          # if switching to writing
                self.instate = self.PRINTING                # back to PRINTING state

    def flushcheck(self) :                                  # for half duplex, note when output has flushed
        now = time.time()                                   # time we read this character
        with self.statelock :
            if self.instate == self.FLUSHING :              # if in FLUSHING state
                if now - self.lastread > self.inidlesecs :  # if no input for quiet period
                    self.instate = self.READING             # go to READING state
                    self.owner.logger.debug("Stop flushing input.")     # will start paying attention to input again.
            self.lastread = now                             # update timestamp
        return(self.instate)                                # return input state

#
#    Class simpleui  -- simple user interface for news, weather, etc.
#
class simpleui(object) :

    IDLETIMEOUT = 30                                        # seconds to wait before powerdown
    

    def __init__(self, tty, newsfeeds, config, logger) :
        self.tty = tty                                      # use TTY object
        self.logger = logger                                # use logger
        #   Configuration setup
        self.keyboard = config.getboolean("teletype","keyboard")   # if keyboard present
        self.halfduplex = config.getboolean("teletype","halfduplex")
        self.cutmarks = config.getboolean("format", "cutmarks")
        self.format = None
        self.smsmsgfeed = None                              # no SMS feed yet
        #   Object variables
        self.cutmarks = False                               # insert paper cutmarks if true
        self.needcut = False                                # need a cutmark
        self.needeject = False                              # need a page eject
        self.newsfeeds = newsfeeds                          # URL list from which to obtain news via RSS
        self.weathercity = (None, None)                     # state, city for weather
        self.itemprinting = None                            # ID of what's currently being printed
        self.uilock = threading.Lock()                      # lock object
        self.inqueue = queue.Queue()                        # input queue
        #   Set global socket timeout so feed readers don't hang.
        socket.setdefaulttimeout(DEFAULTSOCKETTIMEOUT)      # prevent hangs
        #    SMS feed initialization
        if config.has_section("twilio") :                 # if Twilio mode        
            self.smsmsgfeed = twiliofeed.Twiliofeed(
                config.get("twilio", "accountsid"),
                config.get("twilio", "authtoken"),
                config.get("twilio", "phone"),
                self.logger)
        if config.has_section("format") :                   # format config
            self.cutmarks = config.getboolean("format","cutmarks")
            if self.smsmsgfeed :                            # if have SMS feed
               self.smsmsgfeed.setheaders(
                    expandescapes(config.get("format","header")),
                    expandescapes(config.get("format","trailer")))
        if config.has_section("weather") :                  # get weather loc
            self.weathercity = (config.get("weather","state"), 
                config.get("weather", "city"), 
                config.get("weather", "zip"))               # city, state, zip
        #    Initialize TTY
        self.readtask = uireadtask(self)                    # input task
        #    Build list of feeds to follow
        self.feeds = feedmanager.Feeds(self.logger)         # create a news feed object 
        for url in newsfeeds :                              # for URLs listed
            self.feeds.addfeed(newsfeed.Newsfeed(url, self.logger))
        if self.smsmsgfeed :
            self.feeds.addfeed(self.smsmsgfeed)             # make this feed active

    def sendcutmark(self) :                                 # cut paper here
        if self.cutmarks :                                  # if cutmarks enabled
            if self.needcut :
                self.tty.doprint(CUTMARK)                  # send cut mark
        self.needcut = False                                # no cutmark needed

    def sendeject(self) :                                   # paper eject, sent when printer goes idle
        if self.cutmarks :                                  # if cutmarks enabled
            if self.needeject :                             # if printed something
                self.tty.doprint(CUTMARK)                  # send cut, then
                self.tty.doprint(EJECTSTR)                    # send eject
        self.needeject = False                              # no eject needed

    def draininput(self) :                                  # consume any queued input
        try: 
            while True :
                ch = self.inqueue.get_nowait()              # get input, if any
                if isinstance(ch, Exception) :              # if error in thread
                    raise ch                                # reraise exception here
        except queue.Empty:                                 # if empty
            return                                          # done

    def waitforbreak(self) :                                # wait for a BREAK, with motor off
        self.tty.doprint("\nOFF.\n")                        # indicate turn off
        self.readtask.acceptinginput(True)                  # accepting input, so we get BREAK chars
        while self.tty.outwaiting() > 0 :                   # wait for printing to finish
            time.sleep(1.0)                                 # finish printing.
        self.tty.motor(False)                               # turn motor off
        self.draininput()                                   # drain input
        ch = self.inqueue.get()                             # wait for input, any input
        if isinstance(ch, Exception) :                      # if error in thread
            raise ch                                        # reraise exception here
        self.tty.doprint("\n")                              # send CR to turn on motor and wake up

    #
    #    waitfortraffic  -- normal loop, waiting for something to come in.
    #
    def waitfortraffic(self, feed) :
        waiting = False
        feed.setlasttitleprinted(None)                      # forget last title printed; print new title on wakeup
        tty = self.tty                                      # the teletype to print to
        while True :                                        # read repeatedly - one story per iteration
            if not self.itemprinting :                      # if no unprinted item pending
                self.itemprinting = feed.getitem()          # get a new news item
            if self.itemprinting :                          # if something to print
                title = self.itemprinting.gettitle()        # get title
                s = self.itemprinting.formattext()          # item text
                errmsg = self.itemprinting.errmsg           # error message if any
                feedtype = self.itemprinting.feed.feedtype  # feed type
                title = title.encode('ascii','replace').decode('ascii')
                s = s.encode('ascii','replace').decode('ascii')  # limit to ASCII for the Teletype
                if waiting :                                # if was waiting
                    tty.doprint("\n\a")                     # wake up, ring bell
                    waiting = False                         # we have a story to print
                    powerdownstart = None                   # not waiting for motor power off
                #    Need to cut paper here?
                if title != feed.getlasttitleprinted() or feedtype == "SMS" :    # cut paper for source change or SMS
                    self.needcut = True                     # cut paper here
                self.sendcutmark()                          # cut paper here
                #    Print feed title if it changed
                if title != feed.getlasttitleprinted() :
                    feed.setlasttitleprinted(title)         # save new title so we can tell if it changed
                    title = tty.convertnonbaudot(title)     # convert special chars to plausible equivalents
                    title = baudottty.wordwrap(title)       # word wrap
                    self.logger.debug("Source: " + title)
                    tty.doprint(title )                     # print title
                    if errmsg :
                        tty.doprint(ERRBELLS)              # ring bells here
                    tty.doprint('\n')                       # end title line
                s = tty.convertnonbaudot(s)           # convert special chars to plausible equivalents
                s = baudottty.wordwrap(s)                   # word wrap
                if s[-1] != '\n' :                          # end with NL
                    s += '\n'
                ssum = re.sub("\s+"," ", self.itemprinting.summarytext()).lstrip()[:80]    # summarize story/msg by truncation
                self.logger.info("Printing: %s..." % (ssum,))        # print a bit of the new story
                tty.doprint(s)                              # print item
                self.itemprinting.itemdone()                # mark item as done
                self.itemprinting = None                    # item has been used up
                if errmsg is None :                         # if no error, get next story immediately
                    self.needeject = True                   # note that a page eject is needed on next idle
                    continue                                # try to get next story
            #    No traffic, wait for more to come in
            if not waiting :
                self.sendeject()                            # eject page if needed
                tty.doprint("WAITING...")                   # indicate wait
                waiting = True                              # waiting with motor off
                feed.setlasttitleprinted(None)              # forget last title printed; print new title on wakeup
                self.logger.info("No traffic, waiting...")
            if tty.kybdinterrupt :                          # if interrupted by BREAK, but not printing
                self.logger.info("Keyboard interrupt")
                return                                      # done
            #    Turn off motor after allowing enough time for all queued output.
            #    The USB serial devices have a huge queue.  We have to wait for it to empty.
            if tty.motorison() :                            # if motor running
                charsleft = tty.outwaiting()                # get chars left to print
                ####print("Queued: %d" % (charsleft,))      # ***TEMP***
                if charsleft <= 0 :                         # if done printing
                    tty.motor(False)                        # turn off Teletype motor
                    self.logger.info("Motor turned off.")
            time.sleep(1)                                   # wait 1 sec for next cycle


    def prompt(self, s, acceptset , maxchars = 1, timeout = None) :            # prompt and read reply
        shift = baudot.Baudot.LTRS                          # assume LTRS shift
        if acceptset and len(acceptset) > 0 and acceptset[0].isdigit() :    # if input demands numbers
            shift = baudot.Baudot.FIGS                      # put machine in FIGS shift for prompt
        instr = ''                                          # input string
        while True: 
            try: 
                self.logger.debug('Prompting for input "%s"' % (s,))
                self.tty.doprint(s)                         # output prompt
                self.tty.writebaudotch(shift,None)          # get into appropriate shift
                self.draininput()                           # drain any input
                self.readtask.acceptinginput(True)          # now accepting input
                while True :                                # accumulate input
                    if len(instr) >= maxchars :             # if accumulated enough
                        break                               # return string
                    if timeout :
                        timeout = timeout + self.tty.outwaitingtime()    # add extra time for printing in progress
                    ch = self.inqueue.get(True, timeout)    # get incoming char (ASCII)
                    if isinstance(ch, Exception) :          # if error in thread
                        raise ch                            # reraise exception here
                    elif ch == '\r' :                       # if end of line
                        break                               # done, return input string
                    elif ch == '\0' :                       # if the "delete char" (the blank key)
                        if len(instr) > 0 :                 # if have some chars
                            lastch = instr[-1]              # last char to be deleted
                            instr = instr[:-1]              # delete last char
                            self.tty.doprint("/" + lastch)  # show deletion as "/x"
                        else :                              # del to beginning of line
                            instr = None                    # no string, done
                            break                           # quit reading
                    elif acceptset and not (ch in acceptset) :    # if unacceptable
                        self.tty.doprint("/" + ch + "\a")   # show deletion, ring bell
                        self.tty.writebaudotch(shift,None)  # get back into appropriate shift
                    else :                                  # normal case
                        instr += ch                         # add to string
                    continue                                # try again
                self.readtask.acceptinginput(False)         # no longer accepting input
                return(instr)                               # return string

            except queue.Empty:                             # if timeout
                self.readtask.acceptinginput(False)         # no longer accepting input
                raise                                       # reraise Empty

            except baudottty.BaudotKeyboardInterrupt as message :    # if aborted by BREAK
                print("Break: " + str(message))
                self.tty.doprint("\n...CANCELLED...\n\n")   # input cancelled
                self.readtask.acceptinginput(False)         # no longer accepting input
                return(None)                                # prompt failed


    def endcancel(self, msg="") :                           # end any output cancellation
        try :
            self.tty.doprint(msg)                           # print nothing to absorb cancel event
        except baudottty.BaudotKeyboardInterrupt as message :    # if cancelled
            pass                                            # ignore

        
    def uiloop(self, initialcmdin = None) :
        useshortprompt = False                              # use long prompt the first time
        initialcmd = initialcmdin                           # initial command
        while True :
            try: 
                self.endcancel()                            # end cancel if necessary
                self.draininput()                           # use up any queued input
                try :
                    if initialcmd :                         # initial command avilable
                        cmd = initialcmd                    # use as first command
                        initialcmd = None                   # use it up
                    elif self.keyboard :                    # prompt if keyboard
                        promptmsg = SHORTPROMPT             # short prompt is abbreviated
                        if not useshortprompt :             # use it unless there was an error
                            promptmsg = LONGPROMPT          # print the long prompt this time
                            useshortprompt = True           # and the short prompt next time.
                        cmd = self.prompt(promptmsg ,       # prompt for input
                            ['N','W','S','O'],
                            1,simpleui.IDLETIMEOUT)
                    else :                                  # no keyboard
                        cmd = initialcmdin                  # do initial command again
                except queue.Empty :                        # if no-input timeout
                    self.tty.doprint('\n')
                    self.waitfortraffic(self.feeds)         # wait for traffic                
                    continue                                # and prompt again
                #    Read a one-letter command.  Handle it.    
                self.logger.info("Command: %s" % (repr(cmd,)))        # done
                if cmd == 'N' :
                    self.tty.doprint('\n\n')
                    self.feeds.unmarkallasread("NEWS")      # unmark all news, forcing a new display
                    self.waitfortraffic(self.feeds)         # type news
                elif cmd == 'W' :
                    self.tty.doprint('\n\n')
                    printweather(self)                      # type weather
                elif cmd == 'S' :
                    self.tty.doprint('\n')
                    sendviasms(self)                        # send something
                elif cmd == 'O' :                           # Turn off
                    self.feeds.markallasread("NEWS")        # mark all stories as read
                    self.waitforbreak()
                    continue
                elif cmd == '' :                            # plain return
                    self.waitfortraffic(self.feeds)         # wait for traffic                
                else:                                       # bogus entry
                    useshortprompt = False                  # print the long prompt
                    continue                                # ask again

            except baudottty.BaudotKeyboardInterrupt as message :    # if aborted
                self.logger.info("Break: " + str(message))
                self.endcancel("\n\n")                      # show BREAK, ignoring break within break
                continue                                    # ask again

    def abortthreads(self) :                                # abort all subordinate threads, called from exception
        #    Abort feed tasks
        self.feeds.abort()                                  # abort all feed tasks
        #    Abort read task.
        self.logger.debug("Waiting for read task to complete.")
        self.readtask.abort()                               # abort reading over at read task
        self.logger.debug("Read task has completed.")

    def runui(self, initialcmd = None) :
        try :
            if not self.keyboard :                          # if keyboard present
                self.logger.debug("No keyboard configured.")# no keyboard
                if initialcmd is None :                     # if no initial command
                    initialcmd = "N"                        # read news, forever.
            self.readtask.daemon = True                     # don't let read task survive control-C
            self.readtask.start()                           # start input
            self.uiloop(initialcmd)                         # run main UI loop
            
        except (EOFError, serial.SerialException) as message :            # if trouble
            self.logger.error("Teletype connection failed, aborting: " + str(message))
            self.abortthreads()                             # abort all threads
            raise
        except (KeyboardInterrupt) as message :             # if shutdown
            self.logger.error("Shutting down: " + str(message))
            self.abortthreads()                             # abort all threads
            raise
        except (RuntimeError) as message :                 # if trouble
            self.logger.exception("Unrecoverable error, aborting: " + str(message))
            self.abortthreads()                             # abort all threads
            raise                                           # re-raise exception with other thread exited.




