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


# Make the serializer transparent
try:
    import json as serializer
    def dump(*args, **kwargs):
        """
        Wrapper for json.dump
        """
        return serializer.dump(indent=True, *args, **kwargs)
except ImportError:  # pragma: no cover
    try:
        import cPickle as serializer
    except ImportError:
        import pickle as serializer

    dump = serializer.dump  # pylint: disable=invalid-name

PY2 = sys.version_info[0] == 2

_logger = logging.getLogger(__name__)

def setupLogging(stream, level, color=True): # pragma: no cover
    "Setup logging according to the command line parameters"

    # Copied from six source
    if sys.version_info[0] == 3:
        string_types = str,
    else:
        string_types = basestring,

    if isinstance(stream, string_types):
        class Stream(object):
            """
            File subclass that allows RainbowLoggingHandler to write
            with colors
            """
            _lock = Lock()
            _color = color

            def __init__(self, *args, **kwargs):
                self._fd = open(*args, **kwargs)

            def isatty(self):
                """
                Tells if this stream accepts control chars
                """
                return self._color

            def write(self, text):
                """
                Writes to the stream
                """
                with self._lock:
                    try:
                        self._fd.write(toBytes(text))
                    except:
                        _logger.exception("Something went wrong!")

        _stream = Stream(stream, 'ab', buffering=1)
    else:
        _stream = stream

    try:
        from rainbow_logging_handler import RainbowLoggingHandler
        handler = RainbowLoggingHandler(
            _stream,
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
    except ImportError: # pragma: no cover
        handler = logging.StreamHandler(_stream)  # pylint: disable=redefined-variable-type
        log_format = "%(levelname)-8s || %(name)-30s || %(message)s"
        handler.formatter = logging.Formatter(log_format)

    logging.root.addHandler(handler)
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

    # PSAPI.DLL
    psapi = windll.psapi

    arr = c_ulong * 256
    list_of_pids = arr()
    cb = sizeof(list_of_pids)  # pylint: disable=invalid-name
    cb_needed = c_ulong()

    # Call Enumprocesses to get hold of process id's
    psapi.EnumProcesses(byref(list_of_pids),
                        cb,
                        byref(cb_needed))

    # Number of processes returned
    number_of_pids = int(cb_needed.value/sizeof(c_ulong()))

    pid_list = [i for i in list_of_pids][:number_of_pids]
    return int(pid) in pid_list

def writeListToFile(filename, _list): # pragma: no cover
    "Well... writes '_list' to 'filename'. This is for testing only"
    _logger.debug("Writing to %s", filename)

    open(filename, mode='w').write(
        '\n'.join([str(x) for x in _list]))

    mtime = p.getmtime(filename)
    time.sleep(0.01)

    if onWindows():
        cmd = 'copy /Y "{0}" +,,{0}'.format(filename)
        _logger.debug(cmd)
        subp.check_call(cmd, shell=True)
    else:
        subp.check_call(['touch', filename])

    for i in range(10):
        if p.getmtime(filename) != mtime:
            break
        _logger.debug("Waiting...[%d]", i)
        time.sleep(0.1)


def onWindows():  # pragma: no cover # pylint: disable=missing-docstring
    return sys.platform == 'win32'

def onMac():      # pragma: no cover # pylint: disable=missing-docstring
    return sys.platform == 'darwin'

def onTravis():   # pragma: no cover # pylint: disable=missing-docstring
    return 'TRAVIS' in os.environ

def onCI():       # pragma: no cover # pylint: disable=missing-docstring
    return 'CI' in os.environ

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
    return p.normpath(p.abspath(p.join(*args)))  # pylint: disable=no-value-for-parameter

def removeDuplicates(seq):
    """
    Fast removal of duplicates within an iterable
    """
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]

# Copied from ycmd
def toBytes(value):
    """
    Consistently returns the new bytes() type from python-future.
    Assumes incoming strings are either UTF-8 or unicode (which is
    converted to UTF-8).
    """
    if not value:
        return bytes()

    # This is tricky. On py2, the bytes type from builtins (from python-future) is
    # a subclass of str. So all of the following are true:
    #   isinstance(str(), bytes)
    #   isinstance(bytes(), str)
    # But they don't behave the same in one important aspect: iterating over a
    # bytes instance yields ints, while iterating over a (raw, py2) str yields
    # chars. We want consistent behavior so we force the use of bytes().
    if type(value) == bytes:
        return value

    # This is meant to catch Python 2's native str type.
    if isinstance(value, bytes):
        return bytes(value, encoding='utf8')

    if isinstance(value, str):
        # On py2, with `from builtins import *` imported, the following is true:
        #
        #   bytes(str(u'abc'), 'utf8') == b"b'abc'"
        #
        # Obviously this is a bug in python-future. So we work around it. Also filed
        # upstream at: https://github.com/PythonCharmers/python-future/issues/193
        # We can't just return value.encode('utf8') on both py2 & py3 because on
        # py2 that *sometimes* returns the built-in str type instead of the newbytes
        # type from python-future.
        if PY2:
            return bytes(value.encode('utf8'), encoding='utf8')
        else:
            return bytes(value, encoding='utf8')

    # This is meant to catch `int` and similar non-string/bytes types.
    return toBytes(str(value))

