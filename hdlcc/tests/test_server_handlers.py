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

# pylint: disable=function-redefined, missing-docstring, protected-access

import logging
import os
import os.path as p
import shutil

from webtest import TestApp
from nose2.tools import such

import six

try:  # Python 3.x
    import unittest.mock as mock # pylint: disable=import-error, no-name-in-module
except ImportError:  # Python 2.x
    import mock

import hdlcc
import hdlcc.handlers as handlers
import hdlcc.utils as utils

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')
VIM_HDL_EXAMPLES = p.abspath(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples"))
HDLCC_SERVER_LOG_LEVEL = os.environ.get('HDLCC_SERVER_LOG_LEVEL', 'INFO')

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

with such.A("hdlcc bottle app") as it:
    # Workaround for Python 2.x and 3.x differences
    if six.PY3:
        it.assertItemsEqual = it.assertCountEqual

    @it.has_setup
    def setup():
        it.BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
        it.BUILDER_PATH = os.environ.get('BUILDER_PATH', None)
        _logger.info("Builder name: %s", it.BUILDER_NAME)
        _logger.info("Builder path: %s", it.BUILDER_PATH)
        if it.BUILDER_NAME:
            it.PROJECT_FILE = p.join(VIM_HDL_EXAMPLES, it.BUILDER_NAME + '.prj')
        else:
            it.PROJECT_FILE = None

        if it.BUILDER_PATH:
            it.patch = mock.patch.dict(
                'os.environ',
                {'PATH' : os.pathsep.join([it.BUILDER_PATH, os.environ['PATH']])})
            it.patch.start()
        it.app = TestApp(handlers.app)

    @it.has_teardown
    def teardown():
        build_folder = p.join(VIM_HDL_EXAMPLES, '.build')
        if p.exists(build_folder):
            shutil.rmtree(build_folder)

        cache = p.join(VIM_HDL_EXAMPLES, '.hdlcc')
        if p.exists(cache):
            shutil.rmtree(cache)

        if p.exists('xvhdl.pb'):
            os.remove('xvhdl.pb')
        if p.exists('.xvhdl.init'):
            os.remove('.xvhdl.init')

        if it.BUILDER_PATH:
            it.patch.stop()

    @it.should("get diagnose info without any project")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        reply = it.app.post_json('/get_diagnose_info')
        it.assertItemsEqual(
            reply.json['info'],
            [u'hdlcc version: %s' % hdlcc.__version__,
             u'Server PID: %d' % os.getpid()])

    @it.should("get diagnose info with an existing project file")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        reply = it.app.post(
            '/get_diagnose_info',
            {'project_file' : it.PROJECT_FILE})

        _logger.info("Reply is %s", reply.json['info'])

        if it.BUILDER_NAME:
            it.assertItemsEqual(
                reply.json['info'],
                [u'hdlcc version: %s' % hdlcc.__version__,
                 u'Server PID: %d' % os.getpid(),
                 u'Builder: %s' % it.BUILDER_NAME])
        else:
            it.assertItemsEqual(
                reply.json['info'],
                [u'hdlcc version: %s' % hdlcc.__version__,
                 u'Server PID: %d' % os.getpid()])

    @it.should("get diagnose info while still not found out the builder name")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        def _getServerByProjectFile(_):
            server = mock.MagicMock()
            server.builder = None
            return server
        with mock.patch('hdlcc.handlers._getServerByProjectFile',
                        _getServerByProjectFile):
            reply = it.app.post(
                '/get_diagnose_info',
                {'project_file' : it.PROJECT_FILE})
            if it.BUILDER_NAME in ('msim', 'ghdl', 'xvhdl'):
                it.assertItemsEqual(
                    reply.json['info'],
                    [u'hdlcc version: %s' % hdlcc.__version__,
                     u'Server PID: %d' % os.getpid(),
                     u'Builder: <unknown> (config file parsing is underway)'])
            else:
                it.assertItemsEqual(
                    reply.json['info'],
                    [u'hdlcc version: %s' % hdlcc.__version__,
                     u'Server PID: %d' % os.getpid()])

    @it.should("get diagnose info with a non existing project file")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        reply = it.app.post(
            '/get_diagnose_info',
            {'project_file' : 'some_project'})

        _logger.info("Reply is %s", reply.json['info'])
        it.assertItemsEqual(
            reply.json['info'],
            [u'hdlcc version: %s' % hdlcc.__version__,
             u'Server PID: %d' % os.getpid()])

    @it.should("rebuild the project with directory cleanup")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        if not it.BUILDER_NAME:
            _logger.info("Test requires a builder")
            return
        # The main reason to rebuild is when the project data is corrupt
        # Test is as follows:
        # 1) Check that a file builds OK
        # 2) Erase the target folder.
        # 3) Check the file fails to build
        # 4) Rebuild the project
        # 5) Check the file builds OK again and returns the same set of
        #    messages

        def step_01_check_file_builds_ok():
            data = {
                'project_file' : it.PROJECT_FILE,
                'path'         : p.join(
                    VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')}

            ui_reply = it.app.post('/get_ui_messages', data)
            reply = it.app.post('/get_messages_by_path', data)

            return reply.json['messages'] + ui_reply.json['ui_messages']

        def step_02_erase_target_folder():
            target_folder = p.join(VIM_HDL_EXAMPLES, '.build')
            it.assertTrue(
                p.exists(target_folder),
                "Target folder '%s' doesn't exists" % target_folder)
            shutil.rmtree(target_folder)
            it.assertFalse(
                p.exists(target_folder),
                "Target folder '%s' still exists!" % target_folder)

        def step_03_check_build_fails(ref_msgs):
            step_03_msgs = step_01_check_file_builds_ok()
            if step_03_msgs:
                _logger.info("Step 03 messages:")
                for msg in step_03_msgs:
                    _logger.info(msg)
            else:
                _logger.info("Step 03 generated no messages")

            it.assertNotEquals(step_01_msgs, step_03_msgs)

        def step_04_rebuild_project():
            data = {'project_file' : it.PROJECT_FILE}
            it.app.post('/rebuild_project', data)
            data = {
                'project_file' : it.PROJECT_FILE,
                'path'         : p.join(
                    VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd')}

        def step_05_check_messages_are_the_same(msgs):
            step_05_msgs = step_01_check_file_builds_ok()
            if step_05_msgs:
                _logger.info("Step 05 messages:")
                for msg in step_05_msgs:
                    _logger.info(msg)
            else:
                _logger.info("Step 05 generated no messages")

            it.assertEquals(msgs, step_05_msgs)

        _logger.info("Step 01")
        step_01_msgs = step_01_check_file_builds_ok()
        if step_01_msgs:
            _logger.info("Step 01 messages:")
        else:
            _logger.info("Step 01 generated no messages")

        for msg in step_01_msgs:
            _logger.info(msg)
            it.assertNotEquals(
                msg.get('error_type', None), 'E',
                "No errors should be found at this point")

        _logger.info("Step 02")
        step_02_erase_target_folder()

        _logger.info("Step 03")
        step_03_check_build_fails(step_01_msgs)

        _logger.info("Step 04")
        step_04_rebuild_project()

        _logger.info("Step 05")
        step_05_check_messages_are_the_same(step_01_msgs)

    @it.should("rebuild the project without directory cleanup")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        if it.BUILDER_NAME not in ('ghdl', 'msim', 'xvhdl'):
            _logger.info("Test requires a builder, except fallback")
            return
        # If the user doesn't knows if the project data is corrupt, he/she
        # should be able to rebuild even if everything is OK.
        # Test is as follows:
        # 1) Check that a file builds OK
        # 2) Rebuild the project
        # 3) Check the file builds OK again and returns the same set of
        #    messages

        def step_01_check_file_builds_ok():
            data = {
                'project_file' : it.PROJECT_FILE,
                'path'         : p.join(
                    VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')}
            _logger.info("Waiting for any previous process to finish")

            ui_reply = it.app.post('/get_ui_messages', data)
            reply = it.app.post('/get_messages_by_path', data)

            return reply.json['messages'] + ui_reply.json['ui_messages']

        def step_02_rebuild_project():
            data = {'project_file' : it.PROJECT_FILE}
            it.app.post('/rebuild_project', data)
            data = {
                'project_file' : it.PROJECT_FILE,
                'path'         : p.join(
                    VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd')}

        def step_03_check_messages_are_the_same(msgs):
            step_03_msgs = step_01_check_file_builds_ok()
            if step_03_msgs:
                _logger.info("Step 03 messages:")
                for msg in step_03_msgs:
                    _logger.info(msg)
            else:
                _logger.info("Step 03 generated no messages")

            it.assertEquals(msgs, step_03_msgs)

        _logger.info("Step 01")
        step_01_msgs = step_01_check_file_builds_ok()
        if step_01_msgs:
            _logger.info("Step 01 messages:")
            for msg in step_01_msgs:
                _logger.info(msg)
        else:
            _logger.info("Step 01 generated no messages")

        _logger.info("Step 02")
        step_02_rebuild_project()

        _logger.info("Step 03")
        step_03_check_messages_are_the_same(step_01_msgs)

    @it.should("shutdown the server when requested")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        # Ensure the server is active
        reply = it.app.post('/get_diagnose_info',
                            {'project_file' : 'some_project'})
        it.assertEqual(reply.status, '200 OK')

        # Send a request to shutdown the server and check if it
        # calls the terminate process method
        pids = []
        def terminateProcess(pid):
            _logger.info("Terminating PID %d", pid)
            pids.append(pid)

        with mock.patch('hdlcc.utils.terminateProcess', terminateProcess):
            reply = it.app.post('/shutdown')
            it.assertEqual(pids, [os.getpid(),])

    @it.should("handle buffer visits without crashing")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        if it.BUILDER_NAME not in ('ghdl', 'msim', 'xvhdl'):
            _logger.info("Test requires a builder, except fallback")
            return

        test_file = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')


        def build_without_buffer_visit():
            data = {'project_file' : it.PROJECT_FILE,
                    'path'         : test_file}

            _ = it.app.post('/get_messages_by_path', data)

        def build_with_buffer_visit():
            data = {'project_file' : it.PROJECT_FILE,
                    'path'         : test_file}

            _ = it.app.post('/on_buffer_visit', data)

        def build_with_buffer_leave():
            data = {'project_file' : it.PROJECT_FILE,
                    'path'         : test_file}

            _ = it.app.post('/on_buffer_leave', data)

        build_without_buffer_visit()
        build_with_buffer_leave()
        build_with_buffer_visit()

    # TODO: This test has side effects and makes other tests fail. Skip
    #       it for now
    @it.should("get messages with content")
    def test():
        data = {
            'project_file' : it.PROJECT_FILE,
            'path'         : p.join(
                VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd'),
            'content'      : '-- TODO: Nothing to see here'}

        ui_reply = it.app.post('/get_ui_messages', data)
        reply = it.app.post('/get_messages_by_path', data)

        _logger.info("UI reply: %s", ui_reply)
        _logger.info("Reply: %s", reply)

        messages = reply.json['messages']

        for message in messages:
            it.assertTrue(utils.samefile(message.pop('filename'),
                                         data['path']))

        it.assertIn(
            {"error_type"    : "W",
             "checker"       : "HDL Code Checker/static",
             "line_number"   : 1,
             "column"        : 4,
             "error_subtype" : "",
             "error_number"  : "0",
             "error_message" : "TODO: Nothing to see here"},
            messages)

    @it.should("get source dependencies")
    @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
    def test():
        data = {
            'project_file' : it.PROJECT_FILE,
            'path'         : p.join(
                VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')}

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
            'project_file' : it.PROJECT_FILE,
            'path'         : p.join(
                VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')}

        reply = it.app.post('/get_build_sequence', data)

        sequence = reply.json['sequence']

        _logger.info("Sequence: %s", sequence)

        if it.BUILDER_NAME:
            it.assertEquals(
                [p.join(VIM_HDL_EXAMPLES, 'basic_library', 'very_common_pkg.vhd'),
                 p.join(VIM_HDL_EXAMPLES, 'basic_library', 'package_with_constants.vhd'),
                 p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd')],
                sequence)
        else:
            it.assertEquals([], sequence, "%s error" % it.BUILDER_NAME)

it.createTests(globals())

