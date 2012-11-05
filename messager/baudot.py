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
#    J. Nagle
#    February, 2009
#
#
#    class Baudot --  convert to and from Baudot for one printer.
#
class Baudot(object) :
    FIGS = b'\x1b'                                  # FIGS/LTRS shift chars in Baudot
    LTRS = b'\x1f'
    LF = b'\x02'                                    # LF in Baudot
    CR = b'\x08'                                    # CR in Baudot
    SPACE = b'\x04'                                 # SPACE in Baudot
    NULL = b'\x00'                                  # NULL in Baudot
    #    Tables for US TTY code.  There are some other alphabets, and other options for the FIGS shift.
    USTTYltrs = [
        b'\0',b'E',b'\n',b'A',b' ',b'S',b'I',b'U',b'\r',b'D',b'R',b'J',b'N',b'F',b'C',b'K',
        b'T',b'Z',b'L',b'W',b'H',b'Y',b'P',b'Q',b'O',b'B',b'G',None,b'M',b'X',b'V',None]
    USTTYfigs = [
        b'\0',b'3',b'\n',b'-',b' ',b'\a',b'8',b'7',b'\r',b'$',b'4',b'\'',b',',b'!',b':',b'(',
        b'5',b'"',b')',b'2',b'#',b'6',b'0',b'1',b'9',b'?',b'&',None,b'.',b'/',b';',None]
        
    #   Tables for ITA2 code.  Minor differences from USTTY.  Apostrophe and Bell are reversed.
    ITA2ltrs = USTTYltrs
    ITA2figs = [
        b'\0',b'3',b'\n',b'-',b' ',b'\'',b'8',b'7',b'\r',b'$',b'4',b'\a',b',',b'!',b':',b'(',
        b'5',b'"',b')',b'2',b'#',b'6',b'0',b'1',b'9',b'?',b'&',None,b'.',b'/',b';',None]
    
    
    #   The Fractions font.  This has 1/8, 1/4, 3/8, 1/2, 5/8, 3/4, and 7/8,
    #   which we do not support at this time. We lose the characters
    #   ":", "!", ";", "(", ")", ",", and ".".  Also, "?" moves.
    FractionsLtrs = USTTYltrs
    FractionsFigs = [
        b'\0',b'3',b'\n',b'-',b' ',b'\a',b'8',b'7',b'\r',b'$',b'4',b'\'',None,None,None,None,
        b'5',b'"',None,b'2',b'#',b'6',b'0',b'1',b'9',None,b'&',None,b'?',b'/',None,None]
       
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
                
    def buildconversion(self, ltrstab, figstab, substitutechar = b'?') : # build and set conversion table
        self.toasciiltrstab = ltrstab               # set letters and figures tables
        self.toasciifigstab = figstab
        self.substitutechar = substitutechar        # set substitute char (ASCII)
        #    Build ASCII -> Baudot table
        self.tobaudottab = []                       # the conversion table 0..127
        for i in range(128) :                       # initialize entries to unknown char
            self.tobaudottab.append((None, None))   # no data
        for i in range(len(ltrstab)) :              # build LTRS part of table
            if not ltrstab[i] is None :             # skip untranslatables
                self.tobaudottab[ord(ltrstab[i])] = (bytes(chr(i)), Baudot.LTRS)    # 
        for i in range(len(figstab)) :              # build FIGS part of table
            if not figstab[i] is None :             # skip untranslatables
                shift = Baudot.FIGS                 # assume need FIGS shift
                if ltrstab[i] == figstab[i] :       # if same char in both shifts
                    shift = None                    # never need a shift 
                self.tobaudottab[ord(figstab[i])] = (bytes(chr(i)), shift)    # 

    #
    #    printableBaudot -- true if Baudot char advances char position
    #
    #    Used in counting character position for carriage return purposes.
    #
    def printableBaudot(self, ch, shift) :
        chn = ord(ch)                               # for index
        if shift == Baudot.FIGS :                   # convert to ASCII, to find out if printable
            ach = self.toasciifigstab[chn]
        else :    
            ach = self.toasciiltrstab[chn]
        return(not (ach is None or ach < ' '))      # true if printable char 

    #
    #    chToBaudot --  convert ASCII char to Baudot
    #
    #    Returns (baudotchar, shiftneeded)
    #
    #    "shiftneeded" is LTRS, FIGS, or None
    #
    def chToBaudot(self,ch) :
        chn = ord(ch.upper())                       # get integer value of char
        if chn > 127 :                              # if out of range char
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
    #    chToASCII  --  convert one char to ASCII
    #
    #    Returns NULL for Baudot characters with no ASCII equivalent (LTRS, FIGS)
    #
    #    Caller must know the shift state.
    #
    def chToASCII(self, b, shift) :
        bn = ord(b)                                 # convert to integer
        if bn > 32 :
            if self.substitutechar is None :        # if no substitution char for bad chars
                raise IndexError("Out of range character to convert to ASCII")
            return(self.substitutechar)             # use substitute char
        if shift == Baudot.FIGS :                   # if in FIGS
            ch = self.toasciifigstab[bn]            # convert figure to ASCII
        else :
            ch = self.toasciiltrstab[bn]            # convert letter to ASCII
        if ch is None :                             # if no ASCII equivalent
            if self.substitutechar is None :        # if no substitution char for bad chars
                raise IndexError("Unknown character to convert to ASCII")
            return(self.substitutechar)             # use substitute char
        return(ch)
                
