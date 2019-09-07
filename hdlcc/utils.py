# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
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

import abc
import functools
import logging
import os
import os.path as p
import shutil
import signal
import subprocess as subp
import sys
from collections import Counter
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from hdlcc import types as t
from hdlcc.path import Path

PY2 = sys.version_info[0] == 2

_logger = logging.getLogger(__name__)


def setupLogging(stream, level, color=True):  # pragma: no cover
    "Setup logging according to the command line parameters"

    # Copied from six source

    if sys.version_info[0] == 3:
        string_types = (str,)
    else:
        string_types = (basestring,)  # pylint: disable=undefined-variable

    if isinstance(stream, string_types):

        class Stream(object):  # pylint: disable=useless-object-inheritance
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
                    self._fd.write(toBytes(text))

        _stream = Stream(stream, "ab", buffering=0)
    else:
        _stream = stream

    try:
        # This is mostly for debugging when doing stuff directly from a
        # terminal
        from rainbow_logging_handler import RainbowLoggingHandler  # type: ignore

        handler = RainbowLoggingHandler(
            _stream,
            #  Customizing each column's color
            # pylint: disable=bad-whitespace
            color_asctime=("dim white", "black"),
            color_name=("dim white", "black"),
            color_funcName=("green", "black"),
            color_lineno=("dim white", "black"),
            color_pathname=("black", "red"),
            color_module=("yellow", None),
            color_message_debug=("color_59", None),
            color_message_info=(None, None),
            color_message_warning=("color_226", None),
            color_message_error=("red", None),
            color_message_critical=("bold white", "red"),
        )
        # pylint: enable=bad-whitespace
    except ImportError:  # pragma: no cover
        handler = logging.StreamHandler(_stream)
        handler.formatter = logging.Formatter(
            "%(levelname)-7s | %(asctime)s | "
            + "%(name)s @ %(funcName)s():%(lineno)d %(threadName)s "
            + "|\t%(message)s",
            datefmt="%H:%M:%S",
        )

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pynvim").setLevel(logging.WARNING)
    logging.getLogger("pyls_jsonrpc.endpoint").setLevel(logging.INFO)
    logging.root.addHandler(handler)
    logging.root.setLevel(level)


# From here: http://stackoverflow.com/a/8536476/1672783
def terminateProcess(pid):
    "Terminate a process given its PID"

    if onWindows():
        import ctypes

        process_terminate = 1
        handle = ctypes.windll.kernel32.OpenProcess(process_terminate, False, pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)


def isProcessRunning(pid):
    "Checks if a process is running given its PID"

    if onWindows():
        return _isProcessRunningOnWindows(pid)

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
    psapi.EnumProcesses(byref(list_of_pids), cb, byref(cb_needed))

    # Number of processes returned
    number_of_pids = int(cb_needed.value / sizeof(c_ulong()))

    pid_list = [i for i in list_of_pids][:number_of_pids]

    return int(pid) in pid_list


def onWindows():  # pragma: no cover # pylint: disable=missing-docstring
    return os.name == "nt"


def onMac():  # pragma: no cover # pylint: disable=missing-docstring
    return sys.platform == "darwin"


class UnknownTypeExtension(Exception):
    """
    Exception thrown when trying to get the file type of an unknown extension.
    Known extensions are one of '.vhd', '.vhdl', '.v', '.vh', '.sv', '.svh'
    """

    def __init__(self, path):
        super(UnknownTypeExtension, self).__init__()
        self._path = path

    def __str__(self):
        return "Couldn't determine file type for path '%s'" % self._path


def getFileType(filename):
    # type: (Path) -> t.FileType
    "Gets the file type of a source file"
    ext = filename.name.split(".")[-1].lower()
    if ext in t.FileType.vhd.value:
        return t.FileType.vhd
    if ext in t.FileType.verilog.value:
        return t.FileType.verilog
    if ext in t.FileType.systemverilog.value:
        return t.FileType.systemverilog
    raise UnknownTypeExtension(filename)


if not hasattr(p, "samefile"):

    def _samefile(file1, file2):
        """
        Emulated version of os.path.samefile. This is needed for Python
        2.7 running on Windows (at least on Appveyor CI)
        """

        return os.stat(file1) == os.stat(file2)


else:
    _samefile = p.samefile  # pylint: disable=invalid-name

samefile = _samefile


def removeDuplicates(seq):
    """
    Fast removal of duplicates within an iterable
    """
    seen = set()
    seen_add = seen.add

    return [x for x in seq if not (x in seen or seen_add(x))]


# Copied from ycmd
def toBytes(value):  # pragma: no cover
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

    if isinstance(value, bytes):
        return value

    # This is meant to catch Python 2's native str type.

    if isinstance(value, bytes):
        return bytes(value, encoding="utf8")

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
            return bytes(value.encode("utf8"), encoding="utf8")

        return bytes(value, encoding="utf8")

    # This is meant to catch `int` and similar non-string/bytes types.

    return toBytes(str(value))


def getTemporaryFilename(name):
    """
    Gets a temporary filename following the format 'hdlcc_pid<>.log' on Linux
    and 'hdlcc_pid<>_<unique>.log' on Windows
    """
    basename = "hdlcc_" + name + "_pid{}".format(os.getpid())

    if onWindows():
        return NamedTemporaryFile(
            prefix=basename + "_", suffix=".log", delete=False
        ).name

    return p.join(p.sep, "tmp", basename + ".log")


def isFileReadable(path):
    # type: (Path) -> bool
    """
    Checks if a given file is readable
    """
    try:
        open(path.name, "r").close()

        return True
    except IOError:
        return False


def getCachePath():
    """
    Get the base path of a folder used to cache data. MacOS is treated as Unix
    """

    if onWindows():
        return p.join(os.environ["LOCALAPPDATA"], "Caches", "hdlcc")

    return p.join(os.environ["HOME"], ".cache", "hdlcc")


def runShellCommand(cmd_with_args, shell=False, env=None, cwd=None):
    # type: (Union[Tuple[str], List[str]], bool, Optional[Dict], Optional[str]) -> Iterable[str]
    """
    Runs a shell command and handles stdout catching
    """
    _logger.debug(" ".join(cmd_with_args))

    try:
        stdout = list(
            subp.check_output(
                cmd_with_args,
                stderr=subp.STDOUT,
                shell=shell,
                env=env or os.environ,
                cwd=cwd,
            ).splitlines()
        )
    except subp.CalledProcessError as exc:
        stdout = list(exc.output.splitlines())
        _logger.debug(
            "Command '%s' failed with error code %d.\nStdout:\n%s",
            cmd_with_args,
            exc.returncode,
            "\n".join([x.decode() for x in stdout]),
        )
    except OSError as exc:
        _logger.debug("Command '%s' failed with %s", cmd_with_args, exc)
        raise

    return [x.decode() for x in stdout]


def removeIfExists(filename):
    try:
        os.remove(filename)
    except OSError:
        pass


def removeDirIfExists(dirname):
    try:
        shutil.rmtree(dirname)
    except OSError:
        pass


class HashableByKey(object):
    """
    Implements hash and comparison operators properly across Python 2 and 3
    """

    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def __hash_key__(self):
        """ Implement this attribute to use it for hashing and comparing"""

    def __hash__(self):
        #  return hash(self.__hash_key__)
        try:
            return hash(self.__hash_key__)
        except:
            print("Couldn't hash %s" % self.__hash_key__)
            raise

    def __eq__(self, other):
        """Overrides the default implementation"""

        if isinstance(other, self.__class__):
            return self.__hash_key__ == other.__hash_key__

        return NotImplemented  # pragma: no cover

    def __ne__(self, other):  # pragma: no cover
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)

        if result is not NotImplemented:
            return not result

        return NotImplemented


def logCalls(func):  # pragma: no cover
    # type: (Callable) -> Callable
    "Decorator to Log calls to func"
    import pprint

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # type: (...) -> Callable
        _str = "%s(%s, %s)" % (func.__name__, args, pprint.pformat(kwargs))
        try:
            result = func(self, *args, **kwargs)
            _logger.info("%s => %s", _str, repr(result))

            return result
        except:
            _logger.exception("Failed to run %s", _str)
            raise

    return wrapper


def getMostCommonItem(items):
    data = Counter(items)
    return max(items, key=data.get)
