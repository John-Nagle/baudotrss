#
#    baudot.py  --  conversion support for Baudot character set.
#
#    Used for Baudot teletypes.
#
#    Python 2.6 and above.
#
#    License: LGPL
#
#    This is intended for use with systems that are converting to and from
#    Baudot just before printing.  It's not intended for bulk conversion.
#    Because the shift state (LTRS or FIGS) of the printer matters in Baudot, the input
#    and output in interactive applications have to be coordinated.  So batch
#    encoding is not useful.
#
#    This module just handles the code conversions.  Machine handling is in "baudottty".
#
#
#    J. Nagle
#    February, 2009
#
#
#    class Baudot --  convert to and from Baudot for one printer.
#
class Baudot(object) :
                                                # control chars as integer constants
    FIGS =  0x1b                                # FIGS/LTRS shift chars in Baudot
    LTRS =  0x1f
    LF =    0x02                                # LF in Baudot
    CR =    0x08                                # CR in Baudot
    SPACE = 0x04                                # SPACE in Baudot
    NULL =  0x00                                # NULL in Baudot
    #    Tables for US TTY code.  There are some other alphabets, and other options for the FIGS shift.
    USTTYltrs = [
        '\0','E','\n','A',' ','S','I','U','\r','D','R','J','N','F','C','K',
        'T','Z','L','W','H','Y','P','Q','O','B','G',None,'M','X','V',None]
    USTTYfigs = [
        '\0','3','\n','-',' ','\a','8','7','\r','$','4','\'',',','!',':','(',
        '5','"',')','2','#','6','0','1','9','?','&',None,'.','/',';',None]
        
    #   Tables for ITA2 code.  Minor differences from USTTY.  Apostrophe and Bell are reversed.
    ITA2ltrs = USTTYltrs
    ITA2figs = [
        '\0','3','\n','-',' ','\'','8','7','\r','$','4','\a',',','!',':','(',
        '5','"',')','2','#','6','0','1','9','?','&',None,'.','/',';',None]
    
    
    #   The Fractions font.  This has 1/8, 1/4, 3/8, 1/2, 5/8, 3/4, and 7/8,
    #   which we do not support at this time. We lose the characters
    #   ":", "!", ";", "(", ")", ",", and ".".  Also, "?" moves.
    FractionsLtrs = USTTYltrs
    FractionsFigs = [
        '\0','3','\n','-',' ','\a','8','7','\r','$','4','\'',None,None,None,None,
        '5','"',None,'2','#','6','0','1','9',None,'&',None,'?','/',None,None]
       
    CHARSETS = {                                    # character sets by name
            "USTTY": (USTTYltrs, USTTYfigs),
            "ITA2" : (ITA2ltrs, ITA2figs),
            "FRACTIONS":(FractionsLtrs, FractionsFigs)} 
    assert(len(USTTYltrs) == 32)                    # exactly 32
    assert(len(USTTYfigs) == 32)                    # exactly 32
    assert(len(ITA2ltrs) == 32)                     # exactly 32
    assert(len(ITA2figs) == 32)                     # exactly 32
    assert(len(FractionsLtrs) == 32)                # exactly 32
    assert(len(FractionsFigs) == 32)                # exactly 32

    SHIFTS = (LTRS, FIGS, None)                     # "None" means we don't know what shift the printer is in.
    
    def __init__(self, charset=None) :
        self.substitutechar = None                  # substitute for bad chars (ASCII)
        self.tobaudottab = None                     # conversion table for conversion to Baudot
        self.toasciiltrstab = None                  # to ASCII, LTRS portion
        self.toasciifigstab = None                  # to ASCII, FIGS portion
        if charset is None :
            charset = "USTTY"                       # default charset
        self.charset = charset.upper()              # store char set
        if not self.charset in Baudot.CHARSETS :         # if config error
            raise(ValueError('Character set "%s" requested, not supported.' % (self.charset,)))
        (ltrtab, figtab) = Baudot.CHARSETS[self.charset] # look up character set
        self.buildconversion(ltrtab, figtab)        # build conversion table
        
    def getcharset(self) :
        """
        Get character set in use (USTTY or FRACTIONS)
        """
        return(self.charset)
                
    def buildconversion(self, ltrstab, figstab, substitutechar = '?') : # build and set conversion table
        self.toasciiltrstab = ltrstab               # set letters and figures tables
        self.toasciifigstab = figstab
        self.substitutechar = substitutechar        # set substitute char (ASCII)
        #    Build ASCII -> Baudot table
        self.tobaudottab = []                       # the conversion table 0..127
        for i in range(128) :                       # initialize entries to unknown char
            self.tobaudottab.append((None, None))   # no data
        for i in range(len(ltrstab)) :              # build LTRS part of table
            if not ltrstab[i] is None :             # skip untranslatables
                self.tobaudottab[ord(ltrstab[i].lower())] = (i, Baudot.LTRS)
                self.tobaudottab[ord(ltrstab[i].upper())] = (i, Baudot.LTRS) 
        for i in range(len(figstab)) :              # build FIGS part of table
            if not figstab[i] is None :             # skip untranslatables
                shift = Baudot.FIGS                 # assume need FIGS shift
                if ltrstab[i] == figstab[i] :       # if same char in both shifts
                    shift = None                    # never need a shift 
                self.tobaudottab[ord(figstab[i])] = (i, shift)    # 
        for (bb,shift) in self.tobaudottab :        # all Baudot entries
            if not (bb is None) :                   # Python 2/3 issue
                assert(isinstance(bb,int))          # must be int 

    #
    #   printableBaudot -- true if Baudot char advances char position
    #
    #   Used in counting character position for carriage return purposes.
    #   Input is a one-byte "bytes" value
    #   We use the tables because the Baudot value of BELL varies.
    #
    def printableBaudot(self, chn, shift) :
        if shift == Baudot.FIGS :                   # convert to ASCII, to find out if printable
            ach = self.toasciifigstab[chn]
        else :    
            ach = self.toasciiltrstab[chn]
        return(not (ach is None or ach < ' '))      # true if printable char 

    #
    #   chToBaudot --  convert ASCII char to Baudot
    #
    #   Input is a an ASCII char as an integer
    #
    #   Returns (baudotchar, shiftneeded)
    #
    #   "shiftneeded" is LTRS, FIGS, or None
    #
    def chToBaudot(self,chn) :
        if chn > 127 or chn < 0 :                   # if out of range char
            if self.substitutechar is None :        # if no substitution char for bad chars
                raise IndexError("Out of range character to convert to Baudot")
            chn = ord(self.substitutechar)          # use substitute char
        b = self.tobaudottab[chn]                   # convert to Baudot and shift
        if b[0] is None :                           # if no conversion available
            if self.substitutechar is None :        # if no substitution char for bad chars
                raise IndexError("Unknown character to convert to Baudot")
            chn = ord(self.substitutechar)          # use substitute char
            b = self.tobaudottab[chn]               # convert to Baudot and shift
        return(b)

    #
    #    chToASCII  --  convert one Baudot char to ASCII
    #
    #    Input is a Baudot character as an int.
    #    Returns NULL for Baudot characters with no ASCII equivalent (LTRS, FIGS)
    #
    #    Caller must know the shift state.
    #
    def chToASCII(self, bn, shift) :
        if bn > 32 or bn < 0:                       # if out of range for Baudot
            if self.substitutechar is None :        # if no substitution char for bad chars
                raise IndexError("Out of range character to convert to ASCII")
            return(self.substitutechar)             # use substitute char
        if shift == Baudot.FIGS :                   # if in FIGS
            ch = self.toasciifigstab[bn]            # convert figure to ASCII
        else :
            ch = self.toasciiltrstab[bn]            # convert letter to ASCII
        if ch is None :                             # if no ASCII equivalent
            return(None)                            # use substitute char
        assert(isinstance(ch, str))                 # ***TEMP***
        return(ch)
                
