#!/usr/bin/env python
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
"HDL Code Checker server launcher"

# PYTHON_ARGCOMPLETE_OK

import sys
import os
import os.path as p
import logging
import argparse
import signal
from threading import Timer

_logger = logging.getLogger(__name__)

def _setupPaths():
    hdlcc_base_path = p.abspath(p.join(p.dirname(__file__), '..'))
    for path in (
            p.join(hdlcc_base_path, 'dependencies', 'requests'),
            p.join(hdlcc_base_path, 'dependencies', 'waitress'),
            p.join(hdlcc_base_path, 'dependencies', 'bottle')):
        if path not in sys.path:
            sys.path.insert(0, path)
        else:
            _logger.warning("Path '%s' was already on sys.path!", path)

def _setupLogging(stream, level):
    if type(stream) is str:
        stream = open(stream, 'a')

    sys.path.insert(0, p.join('.ci', 'rainbow_logging_handler'))

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

def parseArguments():
    "Argument parser for standalone hdlcc"

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--host', action='store',)
    parser.add_argument('--port', action='store',)
    parser.add_argument('--log-level', action='store', )
    parser.add_argument('--log-stream', action='store', )
    parser.add_argument('--parent-pid', action='store', )

    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError: # pragma: no cover
        pass

    args = parser.parse_args()

    args.host = args.host or 'localhost'
    args.port = args.port or 50000
    args.log_level = args.log_level or logging.INFO
    args.log_stream = args.log_stream or sys.stdout

    return args

def _attachPids(source_pid, target_pid):
    def _attachWrapper():
        try:
            os.kill(source_pid, 0)
        except OSError:
            _logger.info("Process '%s' doesn't exists!", source_pid)
            os.kill(target_pid, signal.SIGHUP)

        Timer(1, _attachWrapper).start()

    _logger.debug("Setting up PID attachment from %s to %s", source_pid,
                  target_pid)

    Timer(3, _attachWrapper).start()

def main():
    args = parseArguments()
    _setupPaths()
    import waitress
    _setupLogging(args.log_stream, args.log_level)
    import hdlcc
    from hdlcc.server import handlers
    _logger.info("Starting server. "
                 "Our PID is %s, our parent is %s. "
                 "Version of hdlcc is '%s'",
                 os.getpid(), os.getppid(), hdlcc.__version__)
    _attachPids(os.getppid(), os.getpid())
    waitress.serve(handlers.app, host=args.host, port=args.port, threads=20)

if __name__ == '__main__':
    main()

