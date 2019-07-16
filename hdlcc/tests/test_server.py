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
import time

from multiprocessing import Queue, Process
from threading import Thread
import json

from nose2.tools import such

import mock

import requests
import hdlcc.utils as utils
from hdlcc.tests.mocks import disableVunit

_logger = logging.getLogger(__name__)

TEST_LOG_PATH = p.join(os.environ['TOX_ENV_DIR'], 'log')
TEST_TMP_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
SERVER_LOG_LEVEL = os.environ.get('SERVER_LOG_LEVEL', 'WARNING')
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

JSONRPC_VERSION = '2.0'
CALL_TIMEOUT = 2

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
        from pyls.python_ls import start_io_lang_server
        import hdlcc
        import hdlcc.lsp
        # Client to Server pipe
        csr, csw = os.pipe()
        # Server to client pipe
        scr, scw = os.pipe()

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

            it._server = subp.Popen(cmd, env=os.environ.copy())
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
            it._server.terminate()
            utils.terminateProcess(it._server.pid)
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
            utils.terminateProcess(it._server.pid)

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

    with it.having('LSP server'):
        @it.has_setup
        def setup():
            import hdlcc
            from hdlcc.utils import patchPyls
            patchPyls()

        @it.should("initialize with no project file")
        @disableVunit
        def test():
            from pyls import uris

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
            import hdlcc

            def startServer(*args):
                assert False

            args = type('args', (object, ),
                        {'lsp': True,
                         'log_level': SERVER_LOG_LEVEL,
                         'stderr': p.join(TEST_LOG_PATH, 'hdlcc-stderr.log'),
                         'log_stream': p.join(TEST_LOG_PATH, 'tests.log')})

            # Python 2 won't allow to mock sys.stdout.write directly
            import sys
            stdout = mock.MagicMock(spec=sys.stdout)
            stdout.write = mock.MagicMock(spec=sys.stdout.write)

            with mock.patch('hdlcc.server.startServer', startServer):
                with mock.patch('hdlcc.server.sys.stdout', stdout):
                    with it.assertRaises(AssertionError):
                        hdlcc.server.main(args)

            # Build up the expected response
            body = json.dumps({
                "method": "window/showMessage",
                "jsonrpc": JSONRPC_VERSION,
                "params": {
                    "message":
                        "Unable to start HDLCC LSP server: "
                        "\'AssertionError()\'! Check " + p.abspath(args.stderr) +
                        " for more info",
                    "type": 1}})

            response = ("Content-Length: {}\r\n"
                        "Content-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n"
                        "{}".format(len(body), body))

            stdout.write.assert_called_once_with(response)

it.createTests(globals())
