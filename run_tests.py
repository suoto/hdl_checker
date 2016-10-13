#!/usr/bin/env python
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
# PYTHON_ARGCOMPLETE_OK
from __future__ import print_function

import sys
import os
import os.path as p
import argparse
import logging
import nose2
import coverage

try:  # Python 3.x
    import unittest.mock as mock # pylint: disable=import-error, no-name-in-module
except ImportError:  # Python 2.x
    import mock

try:
    import argcomplete
    _HAS_ARGCOMPLETE = True
except ImportError: # pragma: no cover
    _HAS_ARGCOMPLETE = False

_CI = os.environ.get("CI", None) is not None
_APPVEYOR = os.environ.get("APPVEYOR", None) is not None
_TRAVIS = os.environ.get("TRAVIS", None) is not None
_ON_WINDOWS = sys.platform == 'win32'
TRAVIS_PYTHON_VERSION = os.environ["TRAVIS_PYTHON_VERSION"]
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__)))

_logger = logging.getLogger(__name__)

TEST_ENVS = {}

TEST_ENVS['ghdl'] = {'BUILDER_NAME' : 'ghdl'}

if _CI or not p.exists(p.expanduser('~/.local/bin/ghdl')):
    TEST_ENVS['ghdl']['BUILDER_PATH'] = p.expanduser('~/builders/ghdl/bin/')
else:
    TEST_ENVS['ghdl']['BUILDER_PATH'] = p.expanduser('~/.local/bin/ghdl')

TEST_ENVS['msim'] = {
    'BUILDER_NAME' : 'msim',
    'BUILDER_PATH' : p.expanduser('~/builders/msim/modelsim_ase/linux/')}

TEST_ENVS['xvhdl'] = {
    'BUILDER_NAME' : 'xvhdl',
    'BUILDER_PATH' : p.expanduser('~/builders/xvhdl/bin/')}


def _noseRunner(args):
    "Runs nose2 with coverage"
    _logger.info("nose2 args: %s", repr(args))
    cov = coverage.Coverage(config_file='.coveragerc')
    cov.start()

    try:
        result = nose2.discover(exit=False, argv=args)
    finally:
        cov.stop()
        cov.save()

    return result

def _shell(cmd):
    _logger.info("$ %s", cmd)
    for line in os.popen(cmd).read().split('\n'):
        if line and not line.isspace():
            _logger.info("> %s", line)

def _clear():
    "Clears the current repo and submodules"
    for cmd in ('git clean -fdx',
                'git submodule foreach --recursive git clean -fdx'):
        _shell(cmd)

def _setupLogging(stream, level, color=True): # pragma: no cover
    "Setup logging according to the command line parameters"
    if isinstance(stream, str):
        class Stream(file):
            """
            File subclass that allows RainbowLoggingHandler to write
            with colors
            """
            def isatty(self):
                return color

        stream = Stream(stream, 'ab', buffering=1)

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

def _uploadAppveyorArtifact(path):
    "Uploads 'path' to Appveyor artifacts"
    assert _APPVEYOR, "Appveyor artifacts can only be uploaded to Appveyor"
    cmd = "appveyor PushArtifact \"%s\"" % path
    print(cmd)
    _logger.info(cmd)
    for line in os.popen(cmd).read().splitlines():
        print(line)
        _logger.info(line)

def _parseArguments():
    "Argument parser for standalone hdlcc"

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('tests', action='append', nargs='*',
                        help="Test names or files to be run")

    parser.add_argument('--msim', action='store_true',
                        help="Runs tests with ModelSim environment")

    parser.add_argument('--ghdl', action='store_true',
                        help="Runs tests with GHDL environment")

    parser.add_argument('--xvhdl', action='store_true',
                        help="Runs tests with XHDL environment")

    parser.add_argument('--fallback', action='store_true',
                        help="Runs tests for the fallback builder")

    parser.add_argument('--standalone', action='store_true',
                        help="Runs tests for standalone hdlcc")

    parser.add_argument('--fail-fast', '-F', action='store_true')

    parser.add_argument('--debugger', '-D', action='store_true')

    parser.add_argument('--verbose', '-v', action='store_true')

    parser.add_argument('--log-file', action='store',
                        default=p.abspath(p.expanduser("~/tests.log")))

    parser.add_argument('--log-level', action='store', default='INFO',
                        choices=('CRITICAL', 'DEBUG', 'ERROR', 'INFO',
                                 'WARNING',))

    parser.add_argument('--log-stream', action='store', default=sys.stdout,
                        help="File to use as log. If unset, uses stdout")

    if _HAS_ARGCOMPLETE: # pragma: no cover
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    args.log_level = str(args.log_level).upper()

    # Set the default behaviour: run all tests
    env_list = [getattr(args, x) for x in ('msim', 'ghdl', 'xvhdl', 'fallback',
                                           'standalone')]
    if True not in env_list:
        _ = [setattr(args, x, True) for x in ('msim', 'ghdl', 'xvhdl', 'fallback',
                                              'standalone')]
    test_list = []
    if args.tests:
        test_list = [source for sublist in args.tests for source in sublist]

    args.tests = []

    for test_name_or_file in test_list:
        if p.exists(test_name_or_file):
            test_name = str(test_name_or_file).replace('/', '.')
            test_name = str(test_name).replace('.py', '')
            print("Argument '%s' converted to '%s'" % (test_name_or_file,
                                                       test_name))
        else:
            test_name = test_name_or_file

        args.tests.append(test_name)

    return args

def _getNoseCommandLineArgs(args):
    argv = [sys.argv[0]]
    if args.verbose:
        argv += ['--verbose']
    if args.debugger:
        argv += ['--debugger']
    if args.fail_fast:
        argv += ['--fail-fast']

    return argv

def _getDefaultTestByEnv(env):
    if env in ('msim', 'ghdl', 'xvhdl'):
        return ('hdlcc.tests.test_builders',
                'hdlcc.tests.test_hdlcc_base',
                'hdlcc.tests.test_persistency',
                'hdlcc.tests.test_server_handlers',
                'hdlcc.tests.test_standalone')
    elif env == 'standalone':
        return ('hdlcc.tests.test_config_parser',
                'hdlcc.tests.test_static_check')
    elif env == 'fallback':
        return ('hdlcc.tests.test_builders',
                'hdlcc.tests.test_vhdl_parser',
                'hdlcc.tests.test_verilog_parser',
                'hdlcc.tests.test_hdlcc_base',
                'hdlcc.tests.test_server_handlers',
                'hdlcc.tests.test_hdlcc_server',
                'hdlcc.tests.test_standalone',
                'hdlcc.tests.test_misc')
    assert False

def runTestsForEnv(env, args):
    nose_base_args = _getNoseCommandLineArgs(args)
    nose_args = list(nose_base_args)

    if args.tests:
        nose_args += args.tests
    else:
        nose_args += _getDefaultTestByEnv(env)

    if env in TEST_ENVS and not _ON_WINDOWS:
        test_env = TEST_ENVS[env]
        test_env.update(
            {'HDLCC_SERVER_LOG_LEVEL' : args.log_level})

        patch = mock.patch.dict('os.environ', test_env)
    else:
        patch = mock.patch.dict(
            'os.environ',
            {'HDLCC_SERVER_LOG_LEVEL' : args.log_level})

    patch.start()
    tests = nose2.discover(exit=False, argv=nose_args)
    patch.stop()

    return tests.result.wasSuccessful()

def _setupPaths():
    "Add our dependencies to sys.path"
    for path in (
            p.join(HDLCC_BASE_PATH, 'dependencies', 'bottle'),
            p.join(HDLCC_BASE_PATH, 'dependencies', 'requests'),
        ):
        path = p.abspath(path)
        if path not in sys.path:
            _logger.info("Adding '%s'", path)
            sys.path.insert(0, path)
        else:
            _logger.warning("WARNING: '%s' was already on sys.path!", path)

def main():
    args = _parseArguments()
    _setupLogging(args.log_stream, args.log_level)
    _setupPaths()
    #  _clear()

    _logger.info("Arguments: %s", args)

    logging.getLogger('nose2').setLevel(logging.FATAL)
    logging.getLogger('vunit').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.WARNING)
    file_handler = logging.FileHandler(args.log_file)
    log_format = "[%(asctime)s] %(levelname)-8s || %(name)-30s || %(message)s"
    file_handler.formatter = logging.Formatter(log_format)
    logging.root.addHandler(file_handler)

    _logger.info("Environment info:")
    _logger.info(" - CI:       %s", _CI)
    _logger.info(" - APPVEYOR: %s", _APPVEYOR)
    _logger.info(" - TRAVIS:   %s", _TRAVIS)
    _logger.info(" - LOG:      %s", args.log_file)

    cov = coverage.Coverage(config_file='.coveragerc')
    cov.start()

    passed = True
    for env in ('ghdl', 'msim', 'xvhdl', 'fallback', 'standalone'):
        if getattr(args, env):
            _logger.info("Running env '%s'", env)

            if not runTestsForEnv(env, args):
                if passed:
                    _logger.warning("Some tests failed while running '%s'", env)
                passed = False

            if not passed and args.fail_fast:
                break
        else:
            _logger.info("Skipping env '%s'", env)

    cov.stop()
    cov.save()
    for cmd in ('coverage combine',
                'coverage html'):
        _shell(cmd)

    if not passed:
        _logger.warning("Some tests failed!")
        print("Some tests failed!")

    return 0 if passed else 1

if __name__ == '__main__':
    print("TRAVIS_PYTHON_VERSION: %s" % TRAVIS_PYTHON_VERSION)
    sys.exit(main())
