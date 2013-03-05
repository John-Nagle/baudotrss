#
#   messager - utility functions
#
#   Part of baudotrss
#
import re
#
#   Utility functions
#
def edittime(dt) :
    """
    Edit time into "3:02 PM"
    """
    s = dt.strftime("%I:%M %p")                 # "07:30 PM"
    s = re.sub(r'^0+','',s)                     # "7:30 PM"
    return(s)
    msgdate = timestamp.strftime("%B %d")       # "March 12"
    
DAYSUFFIX = {"1" : "st", "2" : "nd", "3" : "rd" }   # special case date suffixes

def editdate(dt) :
    """
    Edit date into: "November 2nd", for archaic cuteness.
    """
    month = dt.strftime("%B")                   # "March"
    day = dt.strftime("%d")                     # "02"
    assert(len(day) == 2)                       # must be 2 digit
    suffix = "th"
    if (day < "10" or day > "20") :             # if not teen number
        suffix = DAYSUFFIX.get(day[-1], suffix) # apply suffix table on last digit
    day = re.sub(r'^0+','',day)                 # "2"
    s = "%s %s%s" % (month, day, suffix)        # "March 2nd"
    return(s)
