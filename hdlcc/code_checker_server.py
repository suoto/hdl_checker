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

_CI = os.environ.get("CI", None) is not None

_logger = logging.getLogger(__name__)

def _setupPaths():
    "Add our dependencies to sys.path"
    hdlcc_base_path = p.abspath(p.join(p.dirname(__file__), '..'))
    for path in (
            hdlcc_base_path,
            p.join(hdlcc_base_path, 'dependencies', 'requests'),
            p.join(hdlcc_base_path, 'dependencies', 'waitress'),
            p.join(hdlcc_base_path, 'dependencies', 'bottle')):
        path = p.abspath(path)
        if path not in sys.path:
            print "Adding '%s'" % path
            sys.path.insert(0, path)
        else:
            msg = "WARNING: '%s' was already on sys.path!" % path
            print msg
            _logger.warning(msg)

def parseArguments():
    "Argument parser for standalone hdlcc"

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--host', action='store',)
    parser.add_argument('--port', action='store',)
    parser.add_argument('--attach-to-pid', action='store', type=int)
    parser.add_argument('--log-level', action='store', )
    parser.add_argument('--log-stream', action='store', )
    parser.add_argument('--nocolor', action='store_true', default=False)

    parser.add_argument('--stdout', action='store')
    parser.add_argument('--stderr', action='store')

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
    args.color = False if args.nocolor else True

    del args.nocolor

    return args

def _attachPids(source_pid, target_pid):
    """Monitors if source_pid is alive. If not, send signal.SIGHUP to
    target_pid"""
    def _attachWrapper(): # pragma: no cover
        "PID attachment monitor"
        try:
            os.kill(source_pid, 0)
        except OSError:
            _logger.info("Process '%s' doesn't exists!", source_pid)
            if utils.onWindows():
                os.kill(target_pid, signal.SIGKILL)
            else:
                os.kill(target_pid, signal.SIGHUP)
            return
        except AttributeError:
            return

        Timer(1, _attachWrapper).start()

    _logger.debug("Setting up PID attachment from %s to %s", source_pid,
                  target_pid)

    Timer(2, _attachWrapper).start()

def _setupPipeRedirection(stdout, stderr): # pragma: no cover
    "Redirect stdout and stderr to files"
    if stdout is not None:
        sys.stdout = open(stdout, 'ab', buffering=1)
    if stderr is not None:
        sys.stderr = open(stderr, 'ab', buffering=1)

def main():
    args = parseArguments()

    _setupPipeRedirection(args.stdout, args.stderr)
    _setupPaths()

    import waitress
    # Call it again to log the paths we added
    _setupPaths()
    import hdlcc
    from hdlcc import handlers
    import hdlcc.utils as utils

    utils.setupLogging(args.log_stream, args.log_level, args.color)
    _logger.info(
        "Starting server. Our PID is %s, %s. Version string for hdlcc is '%s'",
        os.getpid(),
        "no parent PID to attach to" if args.attach_to_pid is None else \
        "our parent is %s." % args.attach_to_pid,
        hdlcc.__version__)

    if args.attach_to_pid is not None:
        _attachPids(args.attach_to_pid, os.getpid())

    handlers.app.run(host=args.host, port=args.port, threads=20,
                     server='waitress')

if __name__ == '__main__':
    main()

