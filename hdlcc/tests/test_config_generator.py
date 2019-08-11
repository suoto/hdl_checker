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

# pylint: disable=function-redefined
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

import json
import logging
import os
import os.path as p
import shutil

import six
import unittest2
from nose2.tools import such
from webtest import TestApp

import hdlcc
import hdlcc.handlers as handlers
from hdlcc.builders import AVAILABLE_BUILDERS, GHDL, XVHDL, Fallback, MSim
from hdlcc.diagnostics import CheckerDiagnostic, DiagType, StaticCheckerDiag
from hdlcc.tests.utils import (MockBuilder, disableVunit, getTestTempPath,
                               parametrizeClassWithBuilders, setupTestSuport)
from hdlcc.utils import getCachePath, removeDirIfExists

try:  # Python 3.x
    import unittest.mock as mock # pylint: disable=import-error, no-name-in-module
except ImportError:  # Python 2.x
    import mock


TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.abspath(p.join(TEST_TEMP_PATH, 'test_project'))

SERVER_LOG_LEVEL = os.environ.get('SERVER_LOG_LEVEL', 'INFO')

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

BUILDER_CLASS_MAP = {
    'msim': MSim,
    'xvhdl': XVHDL,
    'ghdl': GHDL,
    'fallback': Fallback}


@parametrizeClassWithBuilders
class TestConfigGenerator(unittest2.TestCase):
    # Create defaults so that pylint doesn't complain about non existing
    # members
    builder_name = None
    builder_path = None

    @classmethod
    def setUpClass(cls):
        setupTestSuport(TEST_TEMP_PATH)
        # Add builder path to the env
        cls.original_env = os.environ.copy()

        # Add the builder path to the environment so we can call it
        if cls.builder_path:
            _logger.info("Adding '%s' to the system path", cls.builder_path)
            cls.patch = mock.patch.dict(
                'os.environ',
                {'PATH' : os.pathsep.join([cls.builder_path, os.environ['PATH']])})
            cls.patch.start()

        builder_class = BUILDER_CLASS_MAP[cls.builder_name]
        cls.builder = builder_class(p.join(TEST_TEMP_PATH,
                                           '_%s' % cls.builder_name))
        cls.builder_class = builder_class

    @classmethod
    def tearDownClass(cls):
        if cls.builder_path:
            cls.patch.stop()

    def setUp(self):
        self.app = TestApp(handlers.app)

        # Needs to agree with vroom test file
        self.dummy_test_path = p.join(TEST_TEMP_PATH, self.builder_name, 'dummy_test_path')

        self.assertFalse(
            p.exists(self.dummy_test_path),
            "Path '%s' shouldn't exist right now" % \
                    p.abspath(self.dummy_test_path))

        os.makedirs(self.dummy_test_path)

        os.mkdir(p.join(self.dummy_test_path, 'path_a'))
        os.mkdir(p.join(self.dummy_test_path, 'path_b'))
        os.mkdir(p.join(self.dummy_test_path, 'v_includes'))
        os.mkdir(p.join(self.dummy_test_path, 'sv_includes'))
        # Create empty sources and some extra files as well
        for path in ('README.txt',         # This shouldn't be included
                     'nonreadable.txt',    # This shouldn't be included
                     p.join('path_a', 'some_source.vhd'),
                     p.join('path_a', 'header_out_of_place.vh'),
                     p.join('path_a', 'source_tb.vhd'),
                     p.join('path_b', 'some_source.vhd'),
                     p.join('path_b', 'a_verilog_source.v'),
                     p.join('path_b', 'a_systemverilog_source.sv'),
                     # Create headers for both extensions
                     p.join('v_includes', 'verilog_header.vh'),
                     p.join('sv_includes', 'systemverilog_header.svh'),
                     # Make the tree 'dirty' with other source types
                     p.join('path_a', 'not_hdl_source.log'),
                     p.join('path_a', 'not_hdl_source.py')):
            _logger.info("Writing to %s", path)
            open(p.join(self.dummy_test_path, path), 'w').write('')

    def teardown(self):
        # Create a dummy arrangement of sources
        if p.exists(self.dummy_test_path):
            _logger.info("Removing %s", repr(self.dummy_test_path))
            shutil.rmtree(self.dummy_test_path)

    @mock.patch('hdlcc.config_generators.simple_finder.isFileReadable',
                lambda path: 'nonreadable' not in path)
    def test_run_simple_config_gen(self):
        data = {
            'generator' : 'SimpleFinder',
            'args'      : json.dumps(tuple()),
            'kwargs'    : json.dumps({'paths': [self.dummy_test_path, ]})
        }

        reply = self.app.post('/run_config_generator', data)

        content = reply.json['content'].split('\n')

        _logger.info("Content:")
        for line in content:
            _logger.info(repr(line))

        if self.builder_name in ('msim', ):
            intro = [
                '# Files found: 5',
                '# Available builders: %s' % self.builder_name,
                'builder = %s' % self.builder_name,

                'global_build_flags[systemverilog] = +incdir+%s' % \
                    p.join(self.dummy_test_path, 'sv_includes'),

                'global_build_flags[verilog] = +incdir+%s +incdir+%s' % \
                    (p.join(self.dummy_test_path, 'path_a'),
                     p.join(self.dummy_test_path, 'v_includes')),
                '']

            files = [
                'vhdl lib %s' % p.join(self.dummy_test_path, 'path_a',
                                       'some_source.vhd'),
                'vhdl lib %s -2008' % p.join(self.dummy_test_path, 'path_a',
                                             'source_tb.vhd'),
                'systemverilog lib %s' % p.join(self.dummy_test_path,
                                                'path_b',
                                                'a_systemverilog_source.sv'),
                'verilog lib %s' % p.join(self.dummy_test_path, 'path_b',
                                          'a_verilog_source.v'),
                'vhdl lib %s' % p.join(self.dummy_test_path, 'path_b',
                                       'some_source.vhd')]

        else:
            if self.builder_name in ('ghdl', 'xvhdl'):
                # Default start of the contents when a builder was found
                intro = ['# Files found: 5',
                         '# Available builders: %s' % self.builder_name,
                         'builder = %s' % self.builder_name,
                         '']
            else:
                # Fallback contents
                intro = ['# Files found: 5',
                         '# Available builders: ',
                         '']

            files = [
                'vhdl lib %s' % p.join(self.dummy_test_path, 'path_a',
                                       'some_source.vhd'),
                'vhdl lib %s' % p.join(self.dummy_test_path, 'path_a',
                                       'source_tb.vhd'),
                'systemverilog lib %s' % p.join(self.dummy_test_path,
                                                'path_b',
                                                'a_systemverilog_source.sv'),
                'verilog lib %s' % p.join(self.dummy_test_path, 'path_b',
                                          'a_verilog_source.v'),
                'vhdl lib %s' % p.join(self.dummy_test_path, 'path_b',
                                       'some_source.vhd')]

        self.assertEqual(content[:len(intro)], intro)
        self.assertEquals(content[len(intro):], files)
