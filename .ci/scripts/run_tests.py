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
# PYTHON_ARGCOMPLETE_OK
from __future__ import print_function

import argparse
import logging
import os
import os.path as p
import sys

import coverage  # type: ignore

import nose2  # type: ignore

try:  # Python 3.x
    import unittest.mock as mock  # pylint: disable=import-error, no-name-in-module
except ImportError:  # Python 2.x
    import mock  # type: ignore

try:
    import argcomplete  # type: ignore

    _HAS_ARGCOMPLETE = True
except ImportError:  # pragma: no cover
    _HAS_ARGCOMPLETE = False

_CI = os.environ.get("CI", None) is not None
_APPVEYOR = os.environ.get("APPVEYOR", None) is not None
_TRAVIS = os.environ.get("TRAVIS", None) is not None
_ON_WINDOWS = sys.platform == "win32"
BASE_PATH = p.abspath(p.join(p.dirname(__file__)))

_logger = logging.getLogger(__name__)


def _shell(cmd):
    """
    Run a shell command.

    Args:
        cmd: (str): write your description
    """
    _logger.info("$ %s", cmd)
    for line in os.popen(cmd).read().split("\n"):
        if line and not line.isspace():
            _logger.info("> %s", line)


def _clear():
    "Clears the current repo and submodules"
    for cmd in ("git clean -fdx", "git submodule foreach --recursive git clean -fdx"):
        _shell(cmd)


def _setupLogging(stream, level):  # pragma: no cover
    "Setup logging according to the command line parameters"
    color = False

    if stream is sys.stdout:

        class Stream(object):
            def isatty(self):
                """
                Return true if this isatty

                Args:
                    self: (todo): write your description
                """
                return True

            def write(self, *args, **kwargs):
                """
                Write data to sys.

                Args:
                    self: (todo): write your description
                """
                return sys.stdout.write(*args, **kwargs)

        _stream = Stream()
    else:
        _stream = stream

    color = False
    try:
        color = _stream.isatty()
    except AttributeError:
        pass

    if color:
        try:
            from rainbow_logging_handler import (  # type: ignore
                RainbowLoggingHandler,
            )

            color = True
        except ImportError:
            color = False

    formatter = logging.Formatter(
        "%(levelname)-8s | %(asctime)s | %(threadName)s | "
        + "%(name)s @ %(funcName)s():%(lineno)d "
        + "|\t%(message)s",
        datefmt="%H:%M:%S",
    )

    if color:
        #  RainbowLoggingHandler._fmt = '[%(asctime)s] %(threadName)s %(name)s %(funcName)s():%(lineno)d\t%(message)s'
        rainbow_stream_handler = RainbowLoggingHandler(_stream)
        rainbow_stream_handler.setFormatter(formatter)

        logging.root.addHandler(rainbow_stream_handler)
        logging.root.setLevel(level)
    else:
        handler = logging.StreamHandler(_stream)
        handler.formatter = formatter

        logging.root.addHandler(handler)
        logging.root.setLevel(level)


def _parseArguments():
    """
    Parse command line arguments.

    Args:
    """
    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument(
        "tests", action="append", nargs="*", help="Test names or files to be run"
    )
    parser.add_argument("--fail-fast", "-F", action="store_true")

    parser.add_argument("--debugger", "-D", action="store_true")

    parser.add_argument(
        "--verbose", "-v", action="append_const", const="-v", default=[]
    )

    parser.add_argument(
        "--log-file",
        action="store",
        default=p.join(os.environ["TOX_ENV_DIR"], "log", "tests.log"),
    )

    parser.add_argument(
        "--log-level",
        action="store",
        default="INFO",
        choices=("CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING"),
    )

    parser.add_argument("--log-to-stdout", action="store_true")

    if _HAS_ARGCOMPLETE:  # pragma: no cover
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    args.log_level = str(args.log_level).upper()

    if args.tests:
        test_list = [source for sublist in args.tests for source in sublist]

    args.tests = []

    for test_name_or_file in test_list:
        if p.exists(test_name_or_file):
            test_name = str(test_name_or_file).replace("/", ".")
            test_name = str(test_name).replace(".py", "")
            print("Argument '%s' converted to '%s'" % (test_name_or_file, test_name))
        else:
            test_name = test_name_or_file

        args.tests.append(test_name)

    return args


def _getNoseCommandLineArgs(args):
    """
    Get command line arguments.

    Args:
    """
    argv = []

    argv += args.verbose
    if args.debugger:
        argv += ["--debugger"]
    if args.fail_fast:
        argv += [
            "--fail-fast",
        ]
        # Need at least 2 verbose levels for this to work!
        argv += ["--verbose"] * (2 - len(args.verbose))
    if not args.log_to_stdout:
        argv += ["--log-capture"]

    return argv


def runTestsForEnv(args):
    """
    Run nose command.

    Args:
    """
    nose_base_args = _getNoseCommandLineArgs(args)
    nose_args = list(nose_base_args)

    if args.tests:
        nose_args += args.tests

    test_env = os.environ.copy()

    test_env.update({"SERVER_LOG_LEVEL": args.log_level})

    home = p.join(os.environ["TOX_ENV_DIR"], "tmp", "home")
    os.makedirs(home)

    if not _ON_WINDOWS:
        test_env.update({"HOME": home})
    else:
        test_env.update({"LOCALAPPDATA": home})

    _logger.info("nose2 args: %s", nose_args)

    with mock.patch.dict("os.environ", test_env):
        successful = nose2.discover(exit=False, argv=nose_args).result.wasSuccessful()

    return successful


def main():
    """
    The main function.

    Args:
    """
    args = _parseArguments()
    if args.log_to_stdout:
        _setupLogging(sys.stdout, args.log_level)

    _logger.info("Arguments: %s", args)

    logging.getLogger("nose2").setLevel(logging.FATAL)
    logging.getLogger("vunit").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.WARNING)

    logging.getLogger("pygls").setLevel(logging.INFO)
    logging.getLogger("pygls.protocol").setLevel(logging.INFO)
    logging.getLogger("pygls.server").setLevel(logging.INFO)
    logging.getLogger("pygls.feature_manager").setLevel(logging.INFO)

    file_handler = logging.FileHandler(args.log_file)
    log_format = (
        "%(levelname)-7s | %(asctime)s | "
        + "%(name)s @ %(funcName)s():%(lineno)d %(threadName)s |\t%(message)s"
    )
    file_handler.formatter = logging.Formatter(log_format, datefmt="%H:%M:%S")
    logging.root.addHandler(file_handler)
    logging.root.setLevel(args.log_level)

    cov = coverage.Coverage(config_file=".coveragerc")
    cov.start()

    passed = runTestsForEnv(args)

    cov.stop()
    cov.save()

    if not passed:
        _logger.warning("Some tests failed!")
        print("Some tests failed!")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
