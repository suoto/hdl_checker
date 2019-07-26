#!/usr/bin/env python
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
"HDL Code Checker server launcher"

# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
import os
import os.path as p
import sys
from threading import Timer

from pyls.python_ls import start_io_lang_server

import hdlcc
import hdlcc.lsp
import hdlcc.utils as utils
from hdlcc import handlers

_logger = logging.getLogger(__name__)
PY2 = sys.version_info[0] == 2

_LSP_ERROR_MSG_TEMPLATE = {"method": "window/showMessage",
                           "jsonrpc": "2.0"}


def parseArguments():
    "Argument parser for standalone hdlcc"

    if ('--version' in sys.argv[1:]) or ('-V' in sys.argv[1:]):  # pragma: no cover
        print(hdlcc.__version__)
        sys.exit(0)

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--host', action='store',)
    parser.add_argument('--port', action='store', type=int)
    parser.add_argument('--attach-to-pid', action='store', type=int)
    parser.add_argument('--log-level', action='store', )
    parser.add_argument('--log-stream', action='store', )
    parser.add_argument('--nocolor', action='store_true', default=False)
    parser.add_argument('--lsp', action='store_true', default=False)

    parser.add_argument('--stdout', action='store')
    parser.add_argument('--stderr', action='store')

    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError: # pragma: no cover
        pass

    args = parser.parse_args()

    if args.lsp:
        args.host = None
        args.port = None
    else:
        args.host = args.host or 'localhost'
        args.port = args.port or 50000
        args.log_stream = args.log_stream or sys.stdout

    # If not set, create a temporary file safely so there's no clashes
    args.log_stream = args.log_stream or utils.getTemporaryFilename('log')
    args.stderr = args.stderr or utils.getTemporaryFilename('stderr')

    args.log_level = args.log_level or logging.INFO
    args.color = not args.nocolor

    del args.nocolor

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
    if PY2:
        return open(filepath, mode='wb', buffering=0)
    return open(filepath, mode='w', buffering=1)

def _setupPipeRedirection(stdout, stderr): # pragma: no cover
    "Redirect stdout and stderr to files"
    if stdout is not None:
        sys.stdout = openForStdHandle(stdout)
    if stderr is not None:
        sys.stderr = openForStdHandle(stderr)

def _binaryStdio():
    """
    (from https://github.com/palantir/python-language-server)

    This seems to be different for Window/Unix Python2/3, so going by:
        https://stackoverflow.com/questions/2850893/reading-binary-data-from-stdin
    """

    if not PY2:
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

def run(args): # pylint: disable=missing-docstring
    try:
        # LSP will use stdio to communicate
        _setupPipeRedirection(None if args.lsp else args.stdout, args.stderr)

        startServer(args)
    except Exception as exc:
        if args.lsp:  # pragma: no cover
            msg = ["Unable to start HDLCC LSP server: '%s'!" % repr(exc)]
            if args.stderr:
                msg += ["Check %s for more info" % args.stderr]
            else:
                msg += ["Use --stderr to redirect the output to a file for "
                        "more info"]
            _reportException(' '.join(msg))
        _logger.exception("Failed to start server")
        raise

def startServer(args):
    """
    Import modules and tries to start a hdlcc server
    """
    if args.log_stream:
        utils.setupLogging(args.log_stream, args.log_level, args.color)

    _logger = logging.getLogger(__name__)

    def _attachPids(source_pid, target_pid):
        "Monitors if source_pid is alive. If not, terminate target_pid"
        def _watchPidWrapper():
            "PID attachment monitor"
            try:
                if utils.isProcessRunning(source_pid):
                    Timer(1, _watchPidWrapper).start()
                else:
                    _logger.warning("Process %d is not running anymore", source_pid)
                    utils.terminateProcess(target_pid)
            except (TypeError, AttributeError):  # pragma: no cover
                return

        _logger.debug("Setting up PID attachment from %s to %s", source_pid,
                      target_pid)

        Timer(2, _watchPidWrapper).start()

    _logger.info(
        "Starting server. Our PID is %s, %s. Version string for hdlcc is '%s'",
        os.getpid(),
        "no parent PID to attach to" if args.attach_to_pid is None else \
        "our parent is %s" % args.attach_to_pid,
        hdlcc.__version__)

    if args.lsp:
        stdin, stdout = _binaryStdio()
        start_io_lang_server(stdin, stdout, True,
                             hdlcc.lsp.HdlccLanguageServer)
    else:
        if args.attach_to_pid is not None:
            _attachPids(args.attach_to_pid, os.getpid())

        handlers.app.run(host=args.host, port=args.port, threads=10,
                         server='waitress')

# This is a redefinition to be used as last resort if failed to setup
# the server
class MessageType:  # pylint: disable=too-few-public-methods
    "LSP message types"
    Error = 1
    Warning = 2
    Info = 3
    Log = 4


def _reportException(text):
    "Hand crafted message to report issues when starting up the HDLCC server"
    import json
    message = _LSP_ERROR_MSG_TEMPLATE.copy()
    message['params'] = {'message': text,
                         'type': MessageType.Error}

    body = json.dumps(message)

    # Ensure we get the byte length, not the character length
    content_length = len(body) if isinstance(body, bytes) else len(body.encode('utf-8'))
    response = ("Content-Length: {}\r\n"
                "Content-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n"
                "{}".format(content_length, body))

    sys.stdout.write(response)

def main():
    return run(parseArguments())

if __name__ == '__main__':
    main()
