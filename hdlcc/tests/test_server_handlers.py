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

import logging
import os
import os.path as p

import six
from nose2.tools import such
from webtest import TestApp

import hdlcc
import hdlcc.handlers as handlers
from hdlcc.diagnostics import (CheckerDiagnostic, DiagType, ObjectIsNeverUsed,
                               StaticCheckerDiag)
from hdlcc.tests.utils import disableVunit, getTestTempPath, setupTestSuport
from hdlcc.utils import removeIfExists

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
        it.assertFalse(p.exists('.xvhdl.init'))

        removeIfExists('xvhdl.pb')

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
            server.config_parser.isParsing = lambda: True
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


    @it.should("get messages with content")
    def test():
        data = {
            'project_file' : it.project_file,
            'path'         : p.join(
                TEST_PROJECT, 'another_library', 'foo.vhd'),
            'content'      : '-- TODO: Nothing to see here'}

        ui_reply = it.app.post('/get_ui_messages', data)
        reply = it.app.post('/get_messages_by_path', data)

        _logger.info("UI reply: %s", ui_reply)
        _logger.info("Reply: %s", reply)

        messages = [CheckerDiagnostic.fromDict(x) for x in reply.json['messages']]

        it.assertIn(data['path'], [x.filename for x in messages])

        expected = StaticCheckerDiag(
            filename=data['path'],
            line_number=1, column_number=4,
            text='TODO: Nothing to see here',
            severity=DiagType.STYLE_INFO)

        it.assertIn(expected, messages)

    @it.should("get messages by path")
    def test():
        filename = p.join(TEST_PROJECT, 'basic_library', 'clock_divider.vhd')
        data = {
            'project_file' : it.project_file,
            'path'         : filename}

        ui_reply = it.app.post('/get_ui_messages', data)
        reply = it.app.post('/get_messages_by_path', data)

        _logger.info("UI reply: %s", ui_reply)
        _logger.info("Reply: %s", reply)

        messages = [CheckerDiagnostic.fromDict(x) for x in reply.json['messages']]

        it.assertItemsEqual(
            messages,
            [ObjectIsNeverUsed(filename=filename, line_number=27,
                               column_number=12, object_type='signal',
                               object_name='clk_enable_unused'),])

    @it.should("get source dependencies")
    @disableVunit
    def test():
        data = {
            'project_file' : it.project_file,
            'path'         : p.join(
                TEST_PROJECT, 'another_library', 'foo.vhd')}

        for _ in range(10):
            ui_reply = it.app.post('/get_ui_messages', data)
            reply = it.app.post('/get_dependencies', data)

            _logger.info("UI reply: %s", ui_reply)
            _logger.info("Reply: %s", reply)

        dependencies = reply.json['dependencies']

        _logger.info("Dependencies: %s", ', '.join(dependencies))

        it.assertItemsEqual(
            ["ieee.std_logic_1164",
             "ieee.numeric_std",
             "basic_library.clock_divider"],
            dependencies)

    @it.should("get source build sequence")
    def test():
        data = {
            'project_file' : it.project_file,
            'path'         : p.join(
                TEST_PROJECT, 'another_library', 'foo.vhd')}

        reply = it.app.post('/get_build_sequence', data)

        sequence = reply.json['sequence']

        _logger.info("Sequence: %s", sequence)

        it.assertItemsEqual(
            [p.join(TEST_PROJECT, 'basic_library', 'very_common_pkg.vhd'),
             p.join(TEST_PROJECT, 'basic_library', 'package_with_constants.vhd'),
             p.join(TEST_PROJECT, 'basic_library', 'clock_divider.vhd')],
            sequence)


it.createTests(globals())
