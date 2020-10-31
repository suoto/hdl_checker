# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.
"Common stuff"

import abc
import functools
import logging
import os
import os.path as p
import pprint
import re
import shutil
import signal
import subprocess as subp
import sys
from collections import Counter
from tempfile import NamedTemporaryFile
from threading import Timer
from typing import Callable, Dict, Iterable, List, Optional, Tuple, TypeVar, Union

import six

_logger = logging.getLogger(__name__)

ON_WINDOWS = os.name == "nt"
ON_LINUX = sys.platform == "linux"
ON_MAC = sys.platform == "darwin"


def setupLogging(stream, level):  # pragma: no cover
    "Setup logging according to the command line parameters"
    if isinstance(stream, six.string_types):
        _stream = open(stream, "a")
    else:
        _stream = stream

    handler = logging.StreamHandler(_stream)
    handler.formatter = logging.Formatter(
        "%(levelname)-7s | %(asctime)s | "
        + "%(name)s @ %(funcName)s():%(lineno)d %(threadName)s "
        + "|\t%(message)s",
        datefmt="%H:%M:%S",
    )

    logging.root.addHandler(handler)
    logging.root.setLevel(level)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pynvim").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.INFO)


# From here: http://stackoverflow.com/a/8536476/1672783
def terminateProcess(pid):
    "Terminate a process given its PID"

    if ON_WINDOWS:
        import ctypes  # pylint: disable=import-outside-toplevel

        process_terminate = 1
        handle = ctypes.windll.kernel32.OpenProcess(process_terminate, False, pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)


def isProcessRunning(pid):
    "Checks if a process is running given its PID"

    if ON_WINDOWS:
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
    from ctypes import (  # pylint: disable=import-outside-toplevel
        windll,
        c_ulong,
        sizeof,
        byref,
    )

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

    pid_list = list(list_of_pids)[:number_of_pids]

    return int(pid) in pid_list


if not hasattr(p, "samefile"):

    def _samefile(file1, file2):
        """
        Emulated version of os.path.samefile. This is needed for Python
        2.7 running on Windows (at least on Appveyor CI)
        """

        return os.stat(file1) == os.stat(file2)


else:
    _samefile = p.samefile  # pylint: disable=invalid-name

samefile = _samefile  # pylint: disable=invalid-name


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

        if six.PY2:
            return bytes(value.encode("utf8"), encoding="utf8")

        return bytes(value, encoding="utf8")

    # This is meant to catch `int` and similar non-string/bytes types.

    return toBytes(str(value))


def getTemporaryFilename(name):
    """
    Gets a temporary filename following the format 'hdl_checker_pid<>.log' on Linux
    and 'hdl_checker_pid<>_<unique>.log' on Windows
    """
    try:
        name, suffix = name.split(".")
    except ValueError:
        suffix = None

    basename = "hdl_checker_" + name + "_pid{}".format(os.getpid())

    if ON_WINDOWS:
        return NamedTemporaryFile(
            prefix=basename + "_", suffix="." + (suffix or "log"), delete=False
        ).name

    return p.join(p.sep, "tmp", basename + "." + (suffix or "log"))


def isFileReadable(path):
    # type: (str) -> bool
    """
    Checks if a given file is readable
    """
    try:
        open(path, "r").close()

        return True
    except IOError:
        return False


def runShellCommand(cmd_with_args, shell=False, env=None, cwd=None):
    # type: (Union[Tuple[str], List[str]], bool, Optional[Dict], Optional[str]) -> Iterable[str]
    """
    Runs a shell command and handles stdout catching
    """
    _logger.debug(" ".join(cmd_with_args))

    try:
        return (
            subp.check_output(
                cmd_with_args,
                stderr=subp.STDOUT,
                shell=shell,
                env=env or os.environ,
                cwd=cwd,
            )
            .decode(errors="replace")
            .splitlines()
        )
    except subp.CalledProcessError as exc:
        stdout = tuple(exc.output.decode(errors="replace").splitlines())
        _logger.debug(
            "Command '%s' failed with error code %d.\nStdout:\n%s",
            cmd_with_args,
            exc.returncode,
            "\n".join(stdout),
        )
        return stdout
    except OSError as exc:
        _logger.debug("Command '%s' failed with %s", cmd_with_args, exc)
        raise


def removeIfExists(filename):
    # type: (str) -> bool
    "Removes filename using os.remove and catches the exception if that fails"
    try:
        os.remove(filename)
        _logger.debug("Removed %s", filename)
        return True
    except OSError:
        _logger.debug("Failed to remove %s", filename)
        return False


def removeDirIfExists(dirname):
    # type: (str) -> bool
    """
    Removes the directory dirname using shutil.rmtree and catches the exception
    if that fails
    """
    try:
        shutil.rmtree(dirname)
        _logger.debug("Removed %s", dirname)
        return True
    except OSError:
        _logger.debug("Failed to remove %s", dirname)
        return False


class HashableByKey(object):  # pylint: disable=useless-object-inheritance
    """
    Implements hash and comparison operators properly across Python 2 and 3
    """

    __metaclass__ = abc.ABCMeta

    @property
    @abc.abstractmethod
    def __hash_key__(self):
        """ Implement this attribute to use it for hashing and comparing"""

    def __hash__(self):
        try:
            return hash(self.__hash_key__)
        except:  # pragma: no cover
            print("Couldn't hash %s" % repr(self.__hash_key__))
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

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # type: (...) -> Callable
        _str = "%s(%s, %s)" % (func.__name__, args, pprint.pformat(kwargs))
        try:
            result = func(self, *args, **kwargs)
            _logger.debug("%s => %s", _str, repr(result))

            return result
        except:
            _logger.exception("Failed to run %s", _str)
            raise

    return wrapper


T = TypeVar("T")  # pylint: disable=invalid-name


def getMostCommonItem(items):
    # type: (Iterable[T]) -> T
    """
    Gets the most common item on an interable of items
    """
    data = Counter(items)
    return max(items, key=data.get)


if six.PY2:

    def readFile(path):
        "Wrapper around open().read() that return \n for new lines"
        return open(path, mode="rU").read()


else:

    def readFile(path):
        "Wrapper around open().read() that return \n for new lines"
        return open(path, mode="r", newline="\n", errors='replace').read()


REPO_URL = "https://github.com/suoto/hdl_checker"
_TAGS = re.compile(r"^\w+\s+refs\/tags\/v(?P<tag>(?:\d+\.){2}\d+)", flags=re.MULTILINE)

VersionFormat = Tuple[int, ...]


def _getLatestReleaseVersion():
    # type: () -> Optional[VersionFormat]
    """
    Return the latest tag from https://github.com/suoto/hdl_checker, striping
    the leading 'v' (so that v1.0.0 becomes simply 1.0.0). If the connection to
    the URL fails, return None
    """
    proc = subp.Popen(
        ["git", "ls-remote", "--tags", REPO_URL],
        env={"GIT_TERMINAL_PROMPT": "0"},
        stdout=subp.PIPE,
        stderr=subp.PIPE,
    )

    timer = Timer(5, proc.kill)
    timer.start()

    try:
        stdout, stderr = proc.communicate()
    finally:
        timer.cancel()

    if not stdout or stderr:
        _logger.info(
            "Couldn't fetch latest tag from %s: '%s'", REPO_URL, stderr.decode()
        )
        return None

    tags = tuple(
        tuple(int(x) for x in tag.split(".")) for tag in _TAGS.findall(stdout.decode())
    )

    if tags:
        return sorted(tags)[-1]

    _logger.warning("Unable to get version from '%s'", stdout)
    return None


_VERSION_FORMAT = re.compile(r"^\d+\.\d+\.\d+$")


def onNewReleaseFound(func):
    # type: (Callable[[str], None]) -> None
    """
    Checks if a new release is out and calls func if the running an older
    version
    """
    from hdl_checker import (  # pylint: disable=import-outside-toplevel
        __version__ as current,
    )

    # When installing via pip from github, versioneer will report the current
    # version as 0+unknown, in which case we won't notify
    if not _VERSION_FORMAT.match(current):
        return

    latest = _getLatestReleaseVersion()

    if not latest:
        return

    _logger.debug("Current version is %s, latest is %s", current, latest)

    if latest > tuple(int(x) for x in current.split(".")):
        func(
            "HDL Checker version {} is out! (current version is {})".format(
                ".".join(map(str, latest)), current
            )
        )
