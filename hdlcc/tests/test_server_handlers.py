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

import sys
import logging
import os
import os.path as p
import subprocess as subp
import time
from multiprocessing import Queue, Process
import shutil
import requests
from nose2.tools import such

import hdlcc
import hdlcc.utils as utils

BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = os.environ.get('BUILDER_PATH', p.expanduser("~/builders/ghdl/bin/"))

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')
VIM_HDL_EXAMPLES_PATH = p.abspath(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples"))

if BUILDER_NAME is not None:
    PROJECT_FILE = p.join(VIM_HDL_EXAMPLES_PATH, BUILDER_NAME + '.prj')
else:
    PROJECT_FILE = None

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

def doNothing(queue):
    _logger.debug("I'm ready")
    queue.get()
    _logger.debug("Ok, done")

with such.A("hdlcc server") as it:

    def waitForServer():
        # Wait until the server is up and replying
        for i in range(30):
            _logger.info("Elapsed %ds", i)
            try:
                reply = requests.post('http://127.0.0.1:50000/get_diagnose_info')
                if reply.ok:
                    return
            except requests.ConnectionError:
                pass
            time.sleep(1)

        assert False, "Server is not replying after 30s"

    def waitUntilBuildFinishes(data):
        _logger.info("Waiting for 30s until build is finished")
        for i in range(30):
            time.sleep(1)
            _logger.info("Elapsed %ds", i)
            _ = requests.post(it._url + '/get_messages_by_path',
                              timeout=10, data=data)
            ui_messages = requests.post(it._url + '/get_ui_messages',
                                        timeout=10, data=data)
            _logger.debug("==> %s", ui_messages.json())
            if ui_messages.json()['ui_messages'] == []:
                _logger.info("Ok, done")
                return

        assert False, "Server is still building after 30s"

    @it.has_setup
    def setup():
        # Force disabling VUnit
        it._HAS_VUNIT = hdlcc.config_parser._HAS_VUNIT
        hdlcc.config_parser._HAS_VUNIT = False

    @it.has_teardown
    def teardown():
        # Re enable VUnit if it was available
        hdlcc.config_parser._HAS_VUNIT = it._HAS_VUNIT

    with it.having("no PID attachment"):
        def setupPaths():
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

        def startCodeCheckerServer():
            hdlcc_server_fname = p.join(HDLCC_BASE_PATH, 'hdlcc',
                                        'code_checker_server.py')

            it._host = '127.0.0.1'
            it._port = '50000'
            it._url = 'http://{0}:{1}'.format(it._host, it._port)
            cmd = ['coverage', 'run',
                   hdlcc_server_fname,
                   '--host', it._host, '--port', it._port,
                   '--log-level', 'ERROR',
                   '--attach-to-pid', str(os.getpid()),
                  ]

            # Setup redirection if running on CI server
            if utils.onCI():
                cmd += ['--stdout', 'hdlcc-stdout.log',
                        '--stderr', 'hdlcc-stderr.log',
                        '--log-stream', 'hdlcc.log',]

            _logger.info("Starting hdlcc server with '%s'", " ".join(cmd))

            it._server = subp.Popen(cmd, env=os.environ.copy())

            time.sleep(2)

        @it.has_setup
        def setup():
            _logger.info("Builder name: %s", BUILDER_NAME)
            _logger.info("Builder path: %s", BUILDER_PATH)
            utils.addToPath(BUILDER_PATH)
            setupPaths()
            startCodeCheckerServer()

        @it.has_teardown
        def teardown():
            #  if it._server.poll() is not None:
            #      _logger.info("Server was alive, terminating it")
            #      it._server.terminate()
            #      os.kill(it._server.pid, 9)
            it._server.terminate()
            utils.terminateProcess(it._server.pid)
            utils.removeFromPath(BUILDER_PATH)
            time.sleep(2)

        @it.should("get diagnose info without any project")
        def test():
            reply = requests.post(it._url + '/get_diagnose_info', timeout=10)
            info = reply.json()['info']
            _logger.info(reply.text)
            it.assertIn(u'hdlcc version: %s' % hdlcc.__version__, info)

        @it.should("get diagnose info with an existing project file before it has "
                   "parsed the configuration file")
        def test():
            reply = requests.post(it._url + '/get_diagnose_info', timeout=10,
                                  data={'project_file' : PROJECT_FILE})
            info = reply.json()['info']
            _logger.info(reply.text)
            for expected in (
                    u'hdlcc version: %s' % hdlcc.__version__,
                    u'Builder: <unknown> (config file parsing is underway)'):
                it.assertIn(expected, info)

        @it.should("get diagnose info with a non existing project file")
        def test():
            reply = requests.post(it._url + '/get_diagnose_info', timeout=10,
                                  data={'project_file' : 'some_project'})
            info = reply.json()['info']
            _logger.info(reply.text)
            it.assertIn(u'hdlcc version: %s' % hdlcc.__version__, info)

        @it.should("get UI warning when getting messages before project build "
                   "has finished")
        def test():
            data = {
                'project_file' : PROJECT_FILE,
                'path'         : p.join(
                    VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')}

            ui_messages = requests.post(it._url + '/get_ui_messages', timeout=10,
                                        data=data)

            build_messages = requests.post(it._url + '/get_messages_by_path',
                                           timeout=10, data=data)

            _logger.info(build_messages.text)
            if build_messages.json()['messages']:
                _logger.info("Messages:")
                for message in build_messages.json()['messages']:
                    _logger.info(message)
            else:
                _logger.warning("OMG! No message to log!")

            # async_fifo_tb has changed; this is no longer valid
            #  it.assertEquals(
            #      build_messages.json(),
            #      {u'messages': [
            #          {u'checker'       : u'HDL Code Checker/static',
            #           u'column'        : 14,
            #           u'error_message' : u"constant 'ADDR_WIDTH' is never used",
            #           u'error_number'  : u'0',
            #           u'error_subtype' : u'Style',
            #           u'error_type'    : u'W',
            #           u'filename'      : None,
            #           u'line_number'   : 29}]})

            ui_messages = requests.post(it._url + '/get_ui_messages', timeout=10,
                                        data=data)

            _logger.info(ui_messages.text)
            it.assertEquals(
                ui_messages.json(),
                {'ui_messages': [['warning', "Project hasn't finished building, "
                                             "try again after it finishes."]]})

            waitUntilBuildFinishes(data)

        @it.should("rebuild the project with directory cleanup")
        def test():
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
                    'project_file' : PROJECT_FILE,
                    'path'         : p.join(
                        VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')}

                ui_reply = requests.post(it._url + '/get_ui_messages', timeout=10,
                                         data=data)

                reply = requests.post(it._url + '/get_messages_by_path',
                                      timeout=10, data=data)

                return reply.json()['messages'] + ui_reply.json()['ui_messages']

            def step_02_erase_target_folder():
                target_folder = p.join(VIM_HDL_EXAMPLES_PATH, '.build')
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
                data = {'project_file' : PROJECT_FILE}
                requests.post(it._url + '/rebuild_project', timeout=10,
                              data=data)
                waitForServer()
                data = {
                    'project_file' : PROJECT_FILE,
                    'path'         : p.join(
                        VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd')}
                waitForServer()
                waitUntilBuildFinishes(data)

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
                for msg in step_01_msgs:
                    _logger.info(msg)
            else:
                _logger.info("Step 01 generated no messages")

            _logger.info("Step 02")
            step_02_erase_target_folder()

            _logger.info("Step 03")
            step_03_check_build_fails(step_01_msgs)

            _logger.info("Step 04")
            step_04_rebuild_project()

            _logger.info("Step 05")
            step_05_check_messages_are_the_same(step_01_msgs)

        @it.should("rebuild the project without directory cleanup")
        def test():
            # If the user doesn't knows if the project data is corrupt, he/she
            # should be able to rebuild even if everything is OK.
            # Test is as follows:
            # 1) Check that a file builds OK
            # 2) Rebuild the project
            # 3) Check the file builds OK again and returns the same set of
            #    messages

            def step_01_check_file_builds_ok():
                data = {
                    'project_file' : PROJECT_FILE,
                    'path'         : p.join(
                        VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')}
                _logger.info("Waiting for any previous process to finish")
                waitUntilBuildFinishes(data)

                ui_reply = requests.post(it._url + '/get_ui_messages', timeout=10,
                                         data=data)

                reply = requests.post(it._url + '/get_messages_by_path',
                                      timeout=10, data=data)

                return reply.json()['messages'] + ui_reply.json()['ui_messages']

            def step_02_rebuild_project():
                data = {'project_file' : PROJECT_FILE}
                requests.post(it._url + '/rebuild_project', timeout=10,
                              data=data)
                waitForServer()
                data = {
                    'project_file' : PROJECT_FILE,
                    'path'         : p.join(
                        VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd')}
                waitUntilBuildFinishes(data)

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
        def test():
            # Ensure the server is active
            reply = requests.post(it._url + '/get_diagnose_info', timeout=10,
                                  data={'project_file' : 'some_project'})
            it.assertTrue(reply.ok)

            # Send a request to the shutdown addr
            with it.assertRaises(requests.ConnectionError):
                reply = requests.post(it._url + '/shutdown', timeout=10)

            # Ensure the server no longer active
            with it.assertRaises(requests.ConnectionError):
                reply = requests.post(it._url + '/get_diagnose_info', timeout=10,
                                      data={'project_file' : 'some_project'})

    with it.having("PID attachment"):
        def startCodeCheckerServerAttachedToPid(pid):
            hdlcc_server_fname = p.join(HDLCC_BASE_PATH, 'hdlcc',
                                        'code_checker_server.py')

            it._url = 'http://{0}:{1}'.format(it._host, it._port)
            cmd = ['coverage', 'run',
                   hdlcc_server_fname,
                   '--log-level', 'ERROR',
                   '--attach-to-pid', str(pid),
                  ]

            # Setup redirection if running on CI server
            if utils.onCI():
                cmd += ['--stdout', 'hdlcc-stdout.log',
                        '--stderr', 'hdlcc-stderr.log',
                        '--log-stream', 'hdlcc.log',]

            _logger.info("Starting hdlcc server with '%s'", " ".join(cmd))

            it._server = subp.Popen(cmd, env=os.environ.copy())

            waitForServer()

        @it.has_teardown
        def teardown():
            it._server.terminate()
            utils.terminateProcess(it._server.pid)

        @it.should("terminate when the parent PID is not running anymore")
        def test():

            queue = Queue()

            proc = Process(target=doNothing, args=(queue, ))
            proc.start()

            _logger.info("Started dummy process with PID %d", proc.pid)
            startCodeCheckerServerAttachedToPid(proc.pid)
            time.sleep(3)
            _logger.info("Allowing the dummy process to finish")
            queue.put(1)
            proc.join()

            if utils.isProcessRunning(proc.pid):
                _logger.warning("Dummy process %d was still running", proc.pid)
                proc.terminate()
                time.sleep(1)
                it.assertFalse(utils.isProcessRunning(proc.pid),
                               "Process %d is still running after terminating "
                               "it!" % proc.pid)

            time.sleep(1)
            _logger.info("Server should have died by now")

            with it.assertRaises(requests.ConnectionError):
                requests.post('http://127.0.0.1:50000/get_diagnose_info', timeout=10)


if BUILDER_NAME is not None:
    it.createTests(globals())

