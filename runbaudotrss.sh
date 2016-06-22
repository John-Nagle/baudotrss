#!/bin/bash
#
#   Run Baudotrss
#
#   Use dummy test file if no config file specified.
#
#   Find directory in which this script resides.
#   The code should be in ${CODEDIR}/messager
#
#   Once running, keyboard commands are accepted.
#       N   print all news
#       S   Send SMS
#       W   print weather
#       O   off
#       ESC Simulate BREAK; stop printing or wake up.
#       CR  Wait for new messages.
#
CODEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TESTCFG=${CODEDIR}/configtest.cfg
#
echo "Program files should be in: " ${CODEDIR}
if [ "$1" != "" ]; then
    PARAMS=$@
else
    PARAMS=${TESTCFG}
fi
echo "Configuration file and options: " ${PARAMS}
#
echo python3 ${CODEDIR}/messager/baudotrss.py  ${PARAMS} -v
python3 ${CODEDIR}/messager/baudotrss.py  ${PARAMS} -v
sleep 5
