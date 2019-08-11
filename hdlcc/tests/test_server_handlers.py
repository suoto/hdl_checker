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
from nose2.tools import such
from webtest import TestApp

import hdlcc
import hdlcc.handlers as handlers
from hdlcc.diagnostics import CheckerDiagnostic, DiagType, StaticCheckerDiag
from hdlcc.tests.utils import (MockBuilder, disableVunit, getTestTempPath,
                               setupTestSuport)
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

with such.A("hdlcc bottle app") as it:
    # Workaround for Python 2.x and 3.x differences
    if six.PY3:
        it.assertItemsEqual = it.assertCountEqual

    @it.has_setup
    def setup():
        setupTestSuport(TEST_TEMP_PATH)

        it.project_file = p.join(TEST_PROJECT, 'vimhdl.prj')
        it.app = TestApp(handlers.app)

    @it.has_teardown
    def teardown():
        build_folder = p.join(TEST_PROJECT, '.build')
        it.assertFalse(p.exists(build_folder))

        cache = p.join(TEST_PROJECT, '.hdlcc')
        it.assertFalse(p.exists(cache))

        it.assertFalse(p.exists('xvhdl.pb'))
        it.assertFalse(p.exists('.xvhdl.init'))

    @it.should("get diagnose info without any project")
    @disableVunit
    def test():
        reply = it.app.post_json('/get_diagnose_info')
        it.assertItemsEqual(
            reply.json['info'],
            [u'hdlcc version: %s' % hdlcc.__version__,
             u'Server PID: %d' % os.getpid(),
             u'Builder: none'])

    @it.should("get diagnose info with an existing project file")
    @disableVunit
    def test():
        reply = it.app.post(
            '/get_diagnose_info',
            {'project_file' : it.project_file})

        _logger.info("Reply is %s", reply.json['info'])

        it.assertItemsEqual(
            reply.json['info'],
            [u'hdlcc version: %s' % hdlcc.__version__,
             u'Server PID: %d' % os.getpid(),
             u'Builder: none'])

    @it.should("get diagnose info while still not found out the builder name")
    @disableVunit
    def test():
        def _getServerByProjectFile(_):
            server = mock.MagicMock()
            server.config_parser.isParsing = lambda : True
            return server

        with mock.patch('hdlcc.handlers._getServerByProjectFile',
                        _getServerByProjectFile):
            reply = it.app.post(
                '/get_diagnose_info',
                {'project_file' : it.project_file})

            it.assertItemsEqual(
                reply.json['info'],
                [u'hdlcc version: %s' % hdlcc.__version__,
                 u'Server PID: %d' % os.getpid(),
                 u'Builder: <unknown> (config file parsing is underway)'])

    @it.should("get diagnose info with a non existing project file")
    @disableVunit
    def test():
        reply = it.app.post(
            '/get_diagnose_info',
            {'project_file' : 'foo_bar.prj'})

        _logger.info("Reply is %s", reply.json['info'])
        it.assertItemsEqual(
            reply.json['info'],
            [u'hdlcc version: %s' % hdlcc.__version__,
             u'Server PID: %d' % os.getpid(),
             u'Builder: none'])

    @it.should("shutdown the server when requested")
    @disableVunit
    def test():
        # Ensure the server is active
        reply = it.app.post('/get_diagnose_info',
                            {'project_file' : 'some_project'})
        it.assertEqual(reply.status, '200 OK')

        # Send a request to shutdown the server and check if it
        # calls the terminate process method
        pids = []

        with mock.patch('hdlcc.handlers.terminateProcess', pids.append):
            reply = it.app.post('/shutdown')

        it.assertEqual(pids, [os.getpid(),])


    @it.should("rebuild the project with directory cleanup")
    @disableVunit
    def test():
        project_file = 'hello.prj'
        server = mock.MagicMock()

        servers = mock.MagicMock()
        servers.__getitem__.side_effect = {project_file: server}.__getitem__

        with mock.patch.object(hdlcc.handlers, 'servers', servers):
            data = {'project_file' : project_file}
            it.app.post('/rebuild_project', data)

        # Check the object was removed from the servers list
        servers.__delitem__.assert_called_once_with(project_file)
        # Check the original server cleaned things up
        server.clean.assert_called_once()

    @it.should("handle buffer visits")
    @disableVunit
    def test():
        project_file = 'hello.prj'
        server = mock.MagicMock()

        servers = mock.MagicMock()
        servers.__getitem__.side_effect = {project_file: server}.__getitem__

        test_path = 'some_path.vhd'

        with mock.patch.object(hdlcc.handlers, 'servers', servers):
            data = {'project_file' : project_file,
                    'path'         : test_path}
            it.app.post('/on_buffer_visit', data)

        server.onBufferVisit.assert_called_once_with(test_path)


    #  @it.should("get messages with content")
    #  def test():
    #      data = {
    #          'project_file' : it.project_file,
    #          'path'         : p.join(
    #              TEST_PROJECT, 'another_library', 'foo.vhd'),
    #          'content'      : '-- TODO: Nothing to see here'}

    #      ui_reply = it.app.post('/get_ui_messages', data)
    #      reply = it.app.post('/get_messages_by_path', data)

    #      _logger.info("UI reply: %s", ui_reply)
    #      _logger.info("Reply: %s", reply)

    #      messages = [CheckerDiagnostic.fromDict(x) for x in reply.json['messages']]

    #      it.assertIn(data['path'], [x.filename for x in messages])

    #      expected = StaticCheckerDiag(
    #          filename=data['path'],
    #          line_number=1, column_number=4,
    #          text='TODO: Nothing to see here',
    #          severity=DiagType.STYLE_INFO)

    #      it.assertIn(expected, messages)

    #  @it.should("get source dependencies")
    #  @disableVunit
    #  def test():
    #      data = {
    #          'project_file' : it.project_file,
    #          'path'         : p.join(
    #              TEST_PROJECT, 'another_library', 'foo.vhd')}

    #      for _ in range(10):
    #          ui_reply = it.app.post('/get_ui_messages', data)
    #          reply = it.app.post('/get_dependencies', data)

    #          _logger.info("UI reply: %s", ui_reply)
    #          _logger.info("Reply: %s", reply)

    #      dependencies = reply.json['dependencies']

    #      _logger.info("Dependencies: %s", ', '.join(dependencies))

    #      it.assertItemsEqual(
    #          ["ieee.std_logic_1164",
    #           "ieee.numeric_std",
    #           "basic_library.clock_divider"],
    #          dependencies)

    #  @it.should("get source build sequence")
    #  def test():
    #      data = {
    #          'project_file' : it.project_file,
    #          'path'         : p.join(
    #              TEST_PROJECT, 'another_library', 'foo.vhd')}

    #      reply = it.app.post('/get_build_sequence', data)

    #      sequence = reply.json['sequence']

    #      _logger.info("Sequence: %s", sequence)

    #      if it.BUILDER_NAME:
    #          it.assertEquals(
    #              [p.join(TEST_PROJECT, 'basic_library', 'very_common_pkg.vhd'),
    #               p.join(TEST_PROJECT, 'basic_library', 'package_with_constants.vhd'),
    #               p.join(TEST_PROJECT, 'basic_library', 'clock_divider.vhd')],
    #              sequence)
    #      else:
    #          it.assertEquals([], sequence, "%s error" % it.BUILDER_NAME)

    #  with it.having('some scatered sources'):
    #      @it.has_setup
    #      def setup():
    #          # Needs to agree with vroom test file
    #          it.dummy_test_path = p.join(os.environ['TOX_ENV_DIR'],
    #                                      'dummy_test_path')

    #          it.assertFalse(
    #              p.exists(it.dummy_test_path),
    #              "Path '%s' shouldn't exist right now" % \
    #                      p.abspath(it.dummy_test_path))

    #          os.mkdir(it.dummy_test_path)

    #          os.mkdir(p.join(it.dummy_test_path, 'path_a'))
    #          os.mkdir(p.join(it.dummy_test_path, 'path_b'))
    #          os.mkdir(p.join(it.dummy_test_path, 'v_includes'))
    #          os.mkdir(p.join(it.dummy_test_path, 'sv_includes'))
    #          # Create empty sources and some extra files as well
    #          for path in ('README.txt',         # This shouldn't be included
    #                       'nonreadable.txt',    # This shouldn't be included
    #                       p.join('path_a', 'some_source.vhd'),
    #                       p.join('path_a', 'header_out_of_place.vh'),
    #                       p.join('path_a', 'source_tb.vhd'),
    #                       p.join('path_b', 'some_source.vhd'),
    #                       p.join('path_b', 'a_verilog_source.v'),
    #                       p.join('path_b', 'a_systemverilog_source.sv'),
    #                       # Create headers for both extensions
    #                       p.join('v_includes', 'verilog_header.vh'),
    #                       p.join('sv_includes', 'systemverilog_header.svh'),
    #                       # Make the tree 'dirty' with other source types
    #                       p.join('path_a', 'not_hdl_source.log'),
    #                       p.join('path_a', 'not_hdl_source.py')):
    #              _logger.info("Writing to %s", path)
    #              open(p.join(it.dummy_test_path, path), 'w').write('')

    #      @it.has_teardown
    #      def teardown():
    #          # Create a dummy arrangement of sources
    #          if p.exists(it.dummy_test_path):
    #              _logger.info("Removing %s", repr(it.dummy_test_path))
    #              shutil.rmtree(it.dummy_test_path)

    #      @it.should("shoud be able to run simple file config generator")
    #      @mock.patch('hdlcc.config_generators.simple_finder.isFileReadable',
    #                  lambda path: 'nonreadable' not in path)
    #      def test():
    #          data = {
    #              'generator' : 'SimpleFinder',
    #              'args'      : json.dumps(tuple()),
    #              'kwargs'    : json.dumps({'paths': [it.dummy_test_path, ]})
    #          }

    #          reply = it.app.post('/run_config_generator', data)

    #          content = reply.json['content'].split('\n')

    #          _logger.info("Content:")
    #          for line in content:
    #              _logger.info(repr(line))

    #          _logger.info("OK then, will use %s",
    #                       os.environ.get('BUILDER_NAME', None))

    #          if it.BUILDER_NAME in ('msim', ):
    #              intro = [
    #                  '# Files found: 5',
    #                  '# Available builders: %s' % it.BUILDER_NAME,
    #                  'builder = %s' % it.BUILDER_NAME,

    #                  'global_build_flags[systemverilog] = +incdir+%s' % \
    #                      p.join(it.dummy_test_path, 'sv_includes'),

    #                  'global_build_flags[verilog] = +incdir+%s +incdir+%s' % \
    #                      (p.join(it.dummy_test_path, 'path_a'),
    #                       p.join(it.dummy_test_path, 'v_includes')),
    #                  '']

    #              files = [
    #                  'vhdl lib %s' % p.join(it.dummy_test_path, 'path_a',
    #                                         'some_source.vhd'),
    #                  'vhdl lib %s -2008' % p.join(it.dummy_test_path, 'path_a',
    #                                               'source_tb.vhd'),
    #                  'systemverilog lib %s' % p.join(it.dummy_test_path,
    #                                                  'path_b',
    #                                                  'a_systemverilog_source.sv'),
    #                  'verilog lib %s' % p.join(it.dummy_test_path, 'path_b',
    #                                            'a_verilog_source.v'),
    #                  'vhdl lib %s' % p.join(it.dummy_test_path, 'path_b',
    #                                         'some_source.vhd')]

    #          else:
    #              if it.BUILDER_NAME in ('ghdl', 'xvhdl'):
    #                  # Default start of the contents when a builder was found
    #                  intro = ['# Files found: 5',
    #                           '# Available builders: %s' % it.BUILDER_NAME,
    #                           'builder = %s' % it.BUILDER_NAME,
    #                           '']
    #              else:
    #                  # Fallback contents
    #                  intro = ['# Files found: 5',
    #                           '# Available builders: ',
    #                           '']

    #              files = [
    #                  'vhdl lib %s' % p.join(it.dummy_test_path, 'path_a',
    #                                         'some_source.vhd'),
    #                  'vhdl lib %s' % p.join(it.dummy_test_path, 'path_a',
    #                                         'source_tb.vhd'),
    #                  'systemverilog lib %s' % p.join(it.dummy_test_path,
    #                                                  'path_b',
    #                                                  'a_systemverilog_source.sv'),
    #                  'verilog lib %s' % p.join(it.dummy_test_path, 'path_b',
    #                                            'a_verilog_source.v'),
    #                  'vhdl lib %s' % p.join(it.dummy_test_path, 'path_b',
    #                                         'some_source.vhd')]

    #          it.assertEqual(content[:len(intro)], intro)
    #          it.assertEquals(content[len(intro):], files)

it.createTests(globals())
