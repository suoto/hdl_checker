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
# PYTHON_ARGCOMPLETE_OK
from __future__ import print_function

import argparse
import logging
import os
import os.path as p
import sys
from glob import glob

import coverage
import nose2

try:  # Python 3.x
    import unittest.mock as mock # pylint: disable=import-error, no-name-in-module
except ImportError:  # Python 2.x
    import mock  # type: ignore

try:
    import argcomplete
    _HAS_ARGCOMPLETE = True
except ImportError: # pragma: no cover
    _HAS_ARGCOMPLETE = False

_CI = os.environ.get("CI", None) is not None
_APPVEYOR = os.environ.get("APPVEYOR", None) is not None
_TRAVIS = os.environ.get("TRAVIS", None) is not None
_ON_WINDOWS = sys.platform == 'win32'
BASE_PATH = p.abspath(p.join(p.dirname(__file__)))

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

def _setupLogging(stream, level): # pragma: no cover
    "Setup logging according to the command line parameters"
    from rainbow_logging_handler import RainbowLoggingHandler  # pylint: disable=import-error
    rainbow_stream_handler = RainbowLoggingHandler(stream)

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
                        default=p.join(os.environ['TOX_ENV_DIR'], 'log',
                                       'tests.log'))

    parser.add_argument('--log-level', action='store', default='INFO',
                        choices=('CRITICAL', 'DEBUG', 'ERROR', 'INFO',
                                 'WARNING',))

    parser.add_argument('--log-to-stdout', action='store_true')

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

    if args.log_level:
        argv += ['--log-level', args.log_level]

    return argv

def _getDefaultTestByEnv(env):
    if env in ('msim', 'ghdl', 'xvhdl'):
        return ('hdlcc.tests.test_builders',
                'hdlcc.tests.test_hdlcc_base',
                'hdlcc.tests.test_persistence',
                'hdlcc.tests.test_server_handlers',
                'hdlcc.tests.test_standalone')
    if env == 'standalone':
        return ('hdlcc.tests.test_config_parser',
                'hdlcc.tests.test_static_check')
    if env == 'fallback':
        return ('hdlcc.tests.test_lsp',
                'hdlcc.tests.test_server',
                'hdlcc.tests.test_builders',
                'hdlcc.tests.test_vhdl_parser',
                'hdlcc.tests.test_verilog_parser',
                'hdlcc.tests.test_hdlcc_base',
                'hdlcc.tests.test_server_handlers',
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

    test_env = os.environ.copy()

    if env in TEST_ENVS:
        test_env.update(TEST_ENVS[env])

    test_env.update({'SERVER_LOG_LEVEL' : args.log_level})

    _logger.info("nose2 args: %s", nose_args)

    with mock.patch.dict('os.environ', test_env):
        successful = nose2.discover(exit=False,
                                    argv=nose_args).result.wasSuccessful()

    return successful

def _setupPaths():
    "Add our dependencies to sys.path"
    # Pluggy is not standard...
    sys.path.insert(0, p.join(BASE_PATH, 'dependencies', 'pluggy', 'src'))

    for path in glob(p.join(BASE_PATH, 'dependencies', '*')):
        assert p.exists(path), "Path '{}' doesn't exist".format(path)
        path = p.abspath(path)
        if path not in sys.path:
            print("Inserting %s" % path)
            sys.path.insert(0, path)
        else:
            _logger.debug("Path '%s' was already on sys.path!", path)

def main():
    args = _parseArguments()
    if args.log_to_stdout:
        _setupLogging(sys.stdout, args.log_level)

    _setupPaths()
    #  _clear()

    _logger.info("Arguments: %s", args)

    logging.getLogger('nose2').setLevel(logging.FATAL)
    logging.getLogger('vunit').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.WARNING)
    file_handler = logging.FileHandler(args.log_file)
    #  log_format = "[%(asctime)s] %(levelname)-8s || %(name)-30s || %(message)s"
    log_format = '%(levelname)-7s | %(asctime)s | ' + \
        '%(name)s @ %(funcName)s():%(lineno)d |\t%(message)s'
    file_handler.formatter = logging.Formatter(log_format, datefmt='%H:%M:%S')
    logging.root.addHandler(file_handler)
    logging.root.setLevel(args.log_level)

    print("Environment info:")
    print(" - CI:       %s" % _CI)
    print(" - APPVEYOR: %s" % _APPVEYOR)
    print(" - TRAVIS:   %s" % _TRAVIS)
    print(" - LOG:      %s" % args.log_file)

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
    #  for cmd in ('coverage combine',
    #              'coverage html'):
    #      _shell(cmd)

    if not passed:
        _logger.warning("Some tests failed!")
        print("Some tests failed!")

    return 0 if passed else 1

if __name__ == '__main__':
    sys.exit(main())
