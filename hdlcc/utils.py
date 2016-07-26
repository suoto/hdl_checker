# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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
import shutil
from threading import Lock

_logger = logging.getLogger(__name__)

def setupLogging(stream, level, color=True): # pragma: no cover
    "Setup logging according to the command line parameters"
    if type(stream) is str:
        class Stream(file):
            """File subclass that allows RainbowLoggingHandler to write
            with colors"""
            _lock = Lock()
            def isatty(self):
                return color
            def write(self, *args, **kwargs):
                with self._lock:
                    super(Stream, self).write(*args, **kwargs)

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
def terminateProcess(pid): # pragma: no cover
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

def interruptProcess(pid): # pragma: no cover
    "Send SIGINT to PID"
    os.kill(pid, signal.SIGINT)

def isProcessRunning(pid):
    "Checks if a process is running given its PID"
    if onWindows():
        return _isProcessRunningOnWindows(pid)
    else:
        return _isProcessRunningOnPosix(pid)

def _isProcessRunningOnPosix(pid):
    "Checks if a given PID is runnning under POSIX OSs"
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

def _isProcessRunningOnWindows(pid):
    """
    Enumerates active processes as seen under windows Task Manager on Win
    NT/2k/XP using PSAPI.dll (new api for processes) and using ctypes.Use it as
    you please.

    Based on information from
    http://support.microsoft.com/default.aspx?scid=KB;EN-US;Q175030&ID=KB;EN-US;Q175030

    By Eric Koome email ekoome@yahoo.com
    license GPL

    (adapted from code found at
    http://code.activestate.com/recipes/305279-getting-process-information-on-windows/)
    """
    from ctypes import windll, c_ulong, sizeof, byref

    #PSAPI.DLL
    psapi = windll.psapi

    arr = c_ulong * 256
    list_of_pids = arr()
    cb = sizeof(list_of_pids)
    cb_needed = c_ulong()

    #Call Enumprocesses to get hold of process id's
    psapi.EnumProcesses(byref(list_of_pids),
                        cb,
                        byref(cb_needed))

    #Number of processes returned
    number_of_pids = cb_needed.value/sizeof(c_ulong())

    pid_list = [i for i in list_of_pids][:number_of_pids]
    return int(pid) in pid_list

def writeListToFile(filename, _list): # pragma: no cover
    "Well... writes '_list' to 'filename'. This is for testing only"
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

# pylint: disable=missing-docstring
def onWindows():
    return sys.platform == 'win32'

def onMac(): # pragma: no cover
    return sys.platform == 'darwin'

def onTravis(): # pragma: no cover
    return 'TRAVIS' in os.environ

def onCI(): # pragma: no cover
    return 'CI' in os.environ
# pylint: enable=missing-docstring

def getFileType(filename):
    "Gets the file type of a source file"
    extension = filename[str(filename).rfind('.') + 1:].lower()
    if extension in ['vhd', 'vhdl']:
        return 'vhdl'
    if extension == 'v':
        return 'verilog'
    if extension in ('sv', 'svh'):
        return 'systemverilog'
    assert False, "Unknown file type: '%s'" % extension


if not hasattr(p, 'samefile'):
    def samefile(file1, file2):
        "Emulated version of os.path.samefile"
        return os.stat(file1) == os.stat(file2)
else:
    samefile = p.samefile # pylint: disable=invalid-name

def getDefaultCachePath(project_file): # pragma: no cover
    """
    Gets the default path of hdlcc cache.
    Intended for testing only.
    """
    return p.join(p.abspath(p.dirname(project_file)), '.hdlcc')

def cleanProjectCache(project_file): # pragma: no cover
    """
    Removes the default hdlcc cache folder.
    Intended for testing only.
    """
    if project_file is None:
        _logger.debug("Can't clean None")
    else:
        cache_folder = getDefaultCachePath(project_file)
        if p.exists(cache_folder):
            shutil.rmtree(cache_folder)

def handlePathPlease(*args):
    """
    Join args with pathsep, gets the absolute path and normalizes
    """
    return p.normpath(p.abspath(p.join(*args)))

