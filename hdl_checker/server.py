#!/usr/bin/env python
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
"HDL Checker server launcher"

# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
import os
import sys
from threading import Timer

import six

from hdl_checker import __version__ as version
from hdl_checker import handlers, lsp
from hdl_checker.utils import (
    getTemporaryFilename,
    isProcessRunning,
    setupLogging,
    terminateProcess,
)

_logger = logging.getLogger(__name__)


def parseArguments():
    "Argument parser for standalone hdl_checker"

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument("--host", action="store", help="[HTTP] Host to serve")
    parser.add_argument("--port", action="store", type=int, help="[HTTP] Port to serve")
    parser.add_argument(
        "--lsp",
        action="store_true",
        default=False,
        help="Starts the server in LSP mode. Defaults to false",
    )

    parser.add_argument(
        "--attach-to-pid",
        action="store",
        type=int,
        help="[HTTP, LSP] Stops the server if given PID is not active",
    )
    parser.add_argument("--log-level", action="store", help="[HTTP, LSP] Logging level")
    parser.add_argument(
        "--log-stream",
        action="store",
        help="[HTTP, LSP] Log file, defaults to stdout when in HTTP or a "
        "temporary file named hdl_checker_log_pid<PID>.log when in LSP mode. "
        "Use NONE to disable logging altogether",
    )

    parser.add_argument(
        "--stdout",
        action="store",
        help="[HTTP] File to redirect stdout to. Defaults to a temporary file "
        "named hdl_checker_stdout_pid<PID>.log",
    )
    parser.add_argument(
        "--stderr",
        action="store",
        help="[HTTP] File to redirect stdout to. Defaults to a temporary file "
        "named hdl_checker_stderr_pid<PID>.log. "
        "Use NONE to disable redirecting stderr altogether",
    )

    parser.add_argument(
        "--version",
        "-V",
        action="store_true",
        help="Prints hdl_checker version and exit",
    )

    try:
        import argcomplete  # type: ignore

        argcomplete.autocomplete(parser)
    except ImportError:  # pragma: no cover
        pass

    args = parser.parse_args()

    if args.version:
        sys.stdout.write("%s\n" % version)
        sys.exit(0)

    if args.lsp:
        args.host = None
        args.port = None
    else:
        args.host = args.host or "localhost"
        args.port = args.port or 50000
        args.log_stream = args.log_stream or sys.stdout

    # If not set, create a temporary file safely so there's no clashes
    if args.log_stream == "NONE":
        args.log_stream = None
    else:
        args.log_stream = args.log_stream or getTemporaryFilename("log")

    if args.stderr == "NONE":
        args.stderr = None
    else:
        args.stderr = args.stderr or getTemporaryFilename("stderr")

    args.log_level = args.log_level or logging.INFO

    return args


# Copied from ycmd!
def openForStdHandle(filepath):
    """
    Returns a file object that can be used to replace sys.stdout or
    sys.stderr
    """
    # Need to open the file in binary mode on py2 because of bytes vs unicode.
    # If we open in text mode (default), then third-party code that uses `print`
    # (we're replacing sys.stdout!) with an `str` object on py2 will cause
    # tracebacks because text mode insists on unicode objects. (Don't forget,
    # `open` is actually `io.open` because of future builtins.)
    # Since this function is used for logging purposes, we don't want the output
    # to be delayed. This means no buffering for binary mode and line buffering
    # for text mode. See https://docs.python.org/2/library/io.html#io.open
    if six.PY2:
        return open(filepath, mode="wb", buffering=0)
    return open(filepath, mode="w", buffering=1)


def _setupPipeRedirection(stdout, stderr):  # pragma: no cover
    "Redirect stdout and stderr to files"
    if stdout is not None:
        sys.stdout = openForStdHandle(stdout)
    if stderr is not None:
        sys.stderr = openForStdHandle(stderr)


def _binaryStdio():  # pragma: no cover
    """
    (from https://github.com/palantir/python-language-server)

    This seems to be different for Window/Unix Python2/3, so going by:
        https://stackoverflow.com/questions/2850893/reading-binary-data-from-stdin
    """

    if six.PY3:
        # pylint: disable=no-member
        stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    else:
        # Python 2 on Windows opens sys.stdin in text mode, and
        # binary data that read from it becomes corrupted on \r\n
        if sys.platform == "win32":
            # set sys.stdin to binary mode
            # pylint: disable=no-member,import-error
            import msvcrt

            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        stdin, stdout = sys.stdin, sys.stdout

    return stdin, stdout


def run(args):
    """
    Import modules and tries to start a hdl_checker server
    """
    # LSP will use stdio to communicate
    _setupPipeRedirection(None if args.lsp else args.stdout, args.stderr)

    if args.log_stream:
        setupLogging(args.log_stream, args.log_level)

    globals()["_logger"] = logging.getLogger(__name__)

    def _attachPids(source_pid, target_pid):
        "Monitors if source_pid is alive. If not, terminate target_pid"

        def _watchPidWrapper():
            "PID attachment monitor"
            try:
                if isProcessRunning(source_pid):
                    Timer(1, _watchPidWrapper).start()
                else:
                    _logger.warning("Process %d is not running anymore", source_pid)
                    terminateProcess(target_pid)
            except (TypeError, AttributeError):  # pragma: no cover
                return

        _logger.debug("Setting up PID attachment from %s to %s", source_pid, target_pid)

        Timer(2, _watchPidWrapper).start()

    _logger.info(
        "Starting server. Our PID is %s, %s. Version string for hdl_checker is '%s'",
        os.getpid(),
        "no parent PID to attach to"
        if args.attach_to_pid is None
        else "our parent is %s" % args.attach_to_pid,
        version,
    )

    if args.lsp:
        stdin, stdout = _binaryStdio()
        server = lsp.HdlCheckerLanguageServer()
        lsp.setupLanguageServerFeatures(server)
        server.start_io(stdin=stdin, stdout=stdout)
    else:
        if args.attach_to_pid is not None:
            _attachPids(args.attach_to_pid, os.getpid())

        handlers.app.run(host=args.host, port=args.port, threads=10, server="waitress")


def main():
    return run(parseArguments())


if __name__ == "__main__":
    main()
