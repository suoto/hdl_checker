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

# pylint: disable=function-redefined, missing-docstring, protected-access

import json
import logging
import os
import os.path as p
import subprocess as subp
import tempfile
import time
from multiprocessing import Process, Queue
from threading import Thread

import mock
from nose2.tools import such
from pyls import uris
from pyls.python_ls import start_io_lang_server

import hdlcc
import hdlcc.lsp
import requests
from hdlcc.tests.utils import disableVunit, removeCacheData
from hdlcc.utils import isProcessRunning, onWindows, terminateProcess

such.unittest.TestCase.maxDiff = None

_logger = logging.getLogger(__name__)

TEST_LOG_PATH = p.join(os.environ['TOX_ENV_DIR'], 'log')
TEST_TMP_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
SERVER_LOG_LEVEL = os.environ.get('SERVER_LOG_LEVEL', 'WARNING')
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

JSONRPC_VERSION = '2.0'
CALL_TIMEOUT = 5

def doNothing(queue):
    _logger.debug("I'm ready")
    queue.get()
    _logger.debug("Ok, done")

def _getUnusedLocalhostPort():
    """
    These were "Borrowed" from YCM.
    See https://github.com/Valloric/YouCompleteMe
    """
    import socket
    sock = socket.socket()
    # This tells the OS to give us any free port in the range [1024 - 65535]
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _startClient(client):
    client.start()

class _ClientServer(object):  # pylint: disable=useless-object-inheritance,too-few-public-methods
    """ A class to setup a client/server pair """
    def __init__(self):
        # Client to Server pipe
        csr, csw = os.pipe()
        # Server to client pipe
        scr, scw = os.pipe()

        removeCacheData()

        self.server_thread = Thread(target=start_io_lang_server,
                                    args=(os.fdopen(csr, 'rb'),
                                          os.fdopen(scw, 'wb'),
                                          False,
                                          hdlcc.lsp.HdlccLanguageServer))

        self.server_thread.daemon = True
        self.server_thread.start()

        self.client = hdlcc.lsp.HdlccLanguageServer(os.fdopen(scr, 'rb'),
                                                    os.fdopen(csw, 'wb'),
                                                    start_io_lang_server)

        self.client_thread = Thread(target=_startClient, args=[self.client])
        self.client_thread.daemon = True
        self.client_thread.start()


with such.A("hdlcc server") as it:

    _SERVER_BASE_CMD = [
        'coverage', 'run', p.join(HDLCC_BASE_PATH, 'hdlcc', 'server.py'),
        '--log-level', SERVER_LOG_LEVEL,
        '--stdout', p.join(TEST_LOG_PATH, 'hdlcc-stdout.log'),
        '--stderr', p.join(TEST_LOG_PATH, 'hdlcc-stderr.log'),
        '--log-stream', p.join(TEST_LOG_PATH, 'tests.log')]

    with it.having('http server'):
        def startCodeCheckerServer():
            it._host = '127.0.0.1'
            it._port = str(_getUnusedLocalhostPort())
            it._url = 'http://{0}:{1}'.format(it._host, it._port)

            cmd = list(_SERVER_BASE_CMD) + \
                    ['--host', it._host,
                     '--port', str(it._port)]

            _logger.info("Starting hdlcc server with '%s'", " ".join(cmd))

            stdout_r, stdout_w = os.pipe()
            stderr_r, stderr_w = os.pipe()

            it.stdout = os.fdopen(stdout_r, 'rb')
            it.stderr = os.fdopen(stderr_r, 'rb')

            it._server = subp.Popen(cmd, env=os.environ.copy(),
                                    stdout=os.fdopen(stdout_w, 'wb'),
                                    stderr=os.fdopen(stderr_w, 'wb'))
            waitForServer()

        def startCodeCheckerServerAttachedToPid(pid):
            it._url = 'http://{0}:{1}'.format(it._host, it._port)

            cmd = list(_SERVER_BASE_CMD) + \
                    ['--host', it._host,
                     '--port', str(it._port),
                     '--attach-to-pid', str(pid)]

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
                time.sleep(0.1)

            _logger.error("Server is not replying")
            _logger.error("stderr: %s", it.stderr.read())
            it._server.terminate()
            terminateProcess(it._server.pid)
            assert False, "Server is not replying"

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
            terminateProcess(it._server.pid)

        @it.should("start and respond a request")
        @disableVunit
        def test():
            startCodeCheckerServer()
            # Ensure the server is active
            reply = requests.post(it._url + '/get_diagnose_info',
                                  data={'project_file' : 'some_project'})
            it.assertTrue(reply.ok)

        @it.should("shutdown the server when requested")
        @disableVunit
        def test():
            # Send a request to the shutdown addr
            with it.assertRaises(requests.ConnectionError):
                reply = requests.post(it._url + '/shutdown')
                it.assertFalse(reply.ok)

            it._server.terminate()
            terminateProcess(it._server.pid)

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

            if isProcessRunning(proc.pid):
                _logger.warning("Dummy process %d was still running", proc.pid)
                proc.terminate()
                time.sleep(1)
                it.assertFalse(isProcessRunning(proc.pid),
                               "Process %d is still running after terminating "
                               "it!" % proc.pid)

            time.sleep(1)
            _logger.info("Server should have died by now")

            with it.assertRaises(requests.ConnectionError):
                requests.post(it._url + '/get_diagnose_info')

    with it.having('LSP server'):
        @it.should("initialize with no project file")
        @disableVunit
        def test():
            client_server = _ClientServer()
            response = client_server.client._endpoint.request(
                'initialize',
                {'rootPath': uris.from_fs_path(TEST_TMP_PATH),
                 'initializationOptions': {}}).result(timeout=CALL_TIMEOUT)

            _logger.debug("Response: %s", response)
            it.assertEqual(response, {'capabilities': {'textDocumentSync': 1}})

        @it.should("show message with reason for failing to start")
        @disableVunit
        def test():

            def start_io_lang_server(*_):
                assert False, 'Expected fail to trigger the test'

            args = type('args', (object, ),
                        {'lsp': True,
                         'log_level': SERVER_LOG_LEVEL,
                         'stderr': p.join(TEST_LOG_PATH, 'hdlcc-stderr.log'),
                         'log_stream': p.join(TEST_LOG_PATH, 'tests.log'),
                         'color': None,
                         'attach_to_pid': None})

            # Python 2 won't allow to mock sys.stdout.write directly
            import sys
            stdout = mock.MagicMock(spec=sys.stdout)
            stdout.write = mock.MagicMock(spec=sys.stdout.write)

            with mock.patch('hdlcc.server.start_io_lang_server', start_io_lang_server):
                with mock.patch('hdlcc.server.sys.stdout', stdout):
                    with it.assertRaises(AssertionError):
                        hdlcc.server.run(args)

            # Build up the expected response
            body = json.dumps({
                "method": "window/showMessage",
                "jsonrpc": JSONRPC_VERSION,
                "params": {
                    "message":
                        "Unable to start HDLCC LSP server: "
                        "\'AssertionError(\'Expected fail to trigger the test\')\'! "
                        "Check " + p.abspath(args.stderr) + " for more info",
                    "type": 1}})

            response = ("Content-Length: {}\r\n"
                        "Content-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n"
                        "{}".format(len(body), body))

            stdout.write.assert_called_once_with(response)

    with it.having('LSP server executable'):
        def assertCommandPrints(cmd, stdout, **kwargs):
            _logger.debug("Running command: %s", cmd)
            output = subp.check_output(cmd, **kwargs).decode().strip()
            it.assertEqual(output, stdout)

        @it.should("report version correctly")
        def test():
            assertCommandPrints(['hdlcc', '--version'], hdlcc.__version__)

        def startServerWrapper(cmd):
            log_file = tempfile.mktemp()

            actual_cmd = cmd + ['--nocolor', '--log-stream', log_file]

            _logger.info("Actual command: %s", actual_cmd)

            server = subp.Popen(actual_cmd, stdin=subp.PIPE, stdout=subp.PIPE,
                                stderr=subp.PIPE)

            # Close stdin so the server exits
            stdout, stderr = server.communicate('')

            it.assertEqual(stdout, b'',
                           "stdout should be empty but got\n{}".format(stdout))

            it.assertEqual(stderr, b'',
                           "stderr should be empty but got\n{}".format(stdout))

            # On Windows the Popen PID and the *actual* PID don't always match
            # for some reason. Since we're not testing this, just skip the
            # first line
            log_content = open(log_file, 'rb').read().decode().split('\n')

            expected = [
                "Starting server. Our PID is {}, no parent PID to attach to. "
                "Version string for hdlcc is '{}'".format(
                    server.pid, hdlcc.__version__),
                "Starting HdlccLanguageServer IO language server",
                "No configuration file given, using fallback",
                "Using Fallback builder",
                "Selected builder is 'fallback'",
                "No configuration file given, using fallback",
                ""]

            _logger.info("Log content: %s", log_content)

            if onWindows():
                log_content = log_content[1:]
                expected = expected[1:]

            it.assertEqual(log_content, expected)

            os.remove(log_file)


        @it.should("start server given the --lsp flag and setting stderr")
        def test():
            startServerWrapper(['hdlcc', '--lsp',
                                '--stderr', p.join(TEST_LOG_PATH, 'hdlcc_stderr.log')])

        @it.should("start server given the --lsp flag")
        def test():
            startServerWrapper(['hdlcc', '--lsp', ])

it.createTests(globals())
