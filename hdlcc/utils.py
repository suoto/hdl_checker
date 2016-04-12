# This file is part of HDL Code Checker.
#
# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.
"Common stuff"

import sys
import os
import os.path as p
import logging
import signal
import time
import subprocess as subp

_logger = logging.getLogger(__name__)


def setupLogging(stream, level, color=True):
    "Setup logging according to the command line parameters"
    if type(stream) is str: # pragma: no cover
        class Stream(file):
            """File subclass that allows RainbowLoggingHandler to write
            with colors"""
            def isatty(self):
                return color
            def write(self, *args, **kwargs):
                super(Stream, self).write(*args, **kwargs)
                super(Stream, self).write("\n")

        stream = Stream(stream, 'ab', buffering=1)

    try:
        from rainbow_logging_handler import RainbowLoggingHandler
        rainbow_stream_handler = RainbowLoggingHandler(
            stream,
            #  Customizing each column's color
            # pylint: disable=bad-whitespace
            color_asctime          = ('dim white',  'black'),
            color_name             = ('dim white',  'black'),
            color_funcName         = ('green',      'black'),
            color_lineno           = ('dim white',  'black'),
            color_pathname         = ('black',      'red'),
            color_module           = ('yellow',     None),
            color_message_debug    = ('color_59',   None),
            color_message_info     = (None,         None),
            color_message_warning  = ('color_226',  None),
            color_message_error    = ('red',        None),
            color_message_critical = ('bold white', 'red'))
            # pylint: enable=bad-whitespace

        logging.root.addHandler(rainbow_stream_handler)
        logging.root.setLevel(level)
    except ImportError: # pragma: no cover
        file_handler = logging.StreamHandler(stream)
        #  log_format = "%(levelname)-8s || %(name)-30s || %(message)s"
        #  file_handler.formatter = logging.Formatter(log_format)
        file_handler.formatter = logging.Formatter()
        logging.root.addHandler(file_handler)
        logging.root.setLevel(level)

# From here: http://stackoverflow.com/a/8536476/1672783
def terminateProcess(pid):
    "Terminate a process given its PID"
    if onWindows():
        import ctypes
        process_terminate = 1
        handle = ctypes.windll.kernel32.OpenProcess(
            process_terminate, False, pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)

def interruptProcess(pid):
    "Send SIGINT to PID"
    os.kill(pid, signal.SIGINT)

def writeListToFile(filename, _list):
    "Well... writes '_list' to 'filename'"
    _logger.info("Writing to %s", filename)
    open(filename, 'w').write('\n'.join([str(x) for x in _list]))
    mtime = p.getmtime(filename)
    time.sleep(0.01)

    if onWindows():
        cmd = 'copy /Y "{0}" +,,{0}'.format(filename)
        _logger.info(cmd)
        subp.check_call(cmd, shell=True)
    else:
        subp.check_call(['touch', filename])

    for i in range(10):
        if p.getmtime(filename) != mtime:
            break
        _logger.debug("Waiting...[%d]", i)
        time.sleep(0.1)

def addToPath(path):
    "Adds path to the PATH environment variable"
    path_value = os.pathsep.join([path, os.environ['PATH']])
    os.environ['PATH'] = path_value
    if onWindows():
        os.putenv('PATH', path_value)

def removeFromPath(path):
    "Removes path to the PATH environment variable"
    path_list = os.environ['PATH'].split(os.pathsep)
    path_list.remove(path)
    os.environ['PATH'] = os.pathsep.join(path_list)
    if onWindows():
        os.putenv('PATH', os.pathsep.join(path_list))

def onWindows(): # pylint: disable=missing-docstring
    return sys.platform == 'win32'

def onMac(): # pylint: disable=missing-docstring
    return sys.platform == 'darwin'

def onTravis(): # pylint: disable=missing-docstring
    return 'TRAVIS' in os.environ

def onCI(): # pylint: disable=missing-docstring
    return 'CI' in os.environ

