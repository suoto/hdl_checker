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
import subprocess as subp
import shutil
import time

from multiprocessing import Queue, Process
from nose2.tools import such

import mock

import requests
import hdlcc
import hdlcc.handlers as handlers
import hdlcc.utils as utils

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')
VIM_HDL_EXAMPLES = p.abspath(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples"))
GRLIB_PATH = p.abspath(p.join(TEST_SUPPORT_PATH, "grlib"))
HDLCC_SERVER_LOG_LEVEL = os.environ.get('HDLCC_SERVER_LOG_LEVEL', 'INFO')

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

def doNothing(queue):
    _logger.debug("I'm ready")
    queue.get()
    _logger.debug("Ok, done")

with such.A("hdlcc server") as it:
    def startCodeCheckerServer():
        hdlcc_server_fname = p.join(HDLCC_BASE_PATH, 'hdlcc',
                                    'hdlcc_server.py')

        it._host = '127.0.0.1'
        it._port = '50000'
        it._url = 'http://{0}:{1}'.format(it._host, it._port)
        cmd = ['coverage', 'run',
               hdlcc_server_fname,
               '--host', it._host, '--port', it._port,
               '--log-level', HDLCC_SERVER_LOG_LEVEL,
               #  '--attach-to-pid', str(os.getpid()),
               '--stdout', 'hdlcc-stdout.log',
               '--stderr', 'hdlcc-stderr.log',
               '--log-stream', 'hdlcc.log',]

        _logger.info("Starting hdlcc server with '%s'", " ".join(cmd))

        it._server = subp.Popen(cmd, env=os.environ.copy())
        time.sleep(1)

    def startCodeCheckerServerAttachedToPid(pid):
        hdlcc_server_fname = p.join(HDLCC_BASE_PATH, 'hdlcc',
                                    'hdlcc_server.py')

        it._url = 'http://{0}:{1}'.format(it._host, it._port)
        cmd = ['coverage', 'run',
               hdlcc_server_fname,
               '--log-level', HDLCC_SERVER_LOG_LEVEL,
               '--attach-to-pid', str(pid),
               '--stdout', 'hdlcc-stdout.log',
               '--stderr', 'hdlcc-stderr.log',
               '--log-stream', 'hdlcc.log',]

        _logger.info("Starting hdlcc server with '%s'", " ".join(cmd))

        it._server = subp.Popen(cmd, env=os.environ.copy())

        waitForServer()

    def waitForServer():
        # Wait until the server is up and replying
        for i in range(30):
            try:
                reply = requests.post(it._url + '/get_diagnose_info')
                if reply.ok:
                    _logger.info("Server replied OK after %d attempts", i)
                    return
            except requests.ConnectionError:
                pass
            time.sleep(1)

        assert False, "Server is not replying after 30s"

    def waitUntilBuildFinishes(data):
        _logger.info("Waiting for 30s until build is finished")
        for i in range(30):
            #  time.sleep(1)
            _logger.info("Elapsed %ds", i)
            _ = requests.post(it._url + '/get_messages_by_path', data)
            ui_messages = requests.post(it._url + '/get_ui_messages', data)
            _logger.debug("==> %s", ui_messages.json)
            if ui_messages.json['ui_messages'] == []:
                _logger.info("Ok, done")
                return

        assert False, "Server is still building after 30s"

    @it.has_teardown
    def teardown():
        it._server.terminate()
        utils.terminateProcess(it._server.pid)

    @it.should("shutdown the server when requested")
    @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
    def test():
        startCodeCheckerServer()
        # Ensure the server is active
        reply = requests.post(it._url + '/get_diagnose_info',
                              data={'project_file' : 'some_project'})
        it.assertTrue(reply.ok)

        # Send a request to the shutdown addr
        with it.assertRaises(requests.ConnectionError):
            reply = requests.post(it._url + '/shutdown')

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
            requests.post(it._url + '/get_diagnose_info')

it.createTests(globals())

