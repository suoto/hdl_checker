# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=function-redefined, missing-docstring, protected-access

import asyncio
import logging
import os
import os.path as p
import subprocess as subp
import tempfile
import time
from multiprocessing import Event, Process, Queue
from threading import Thread

import requests
from mock import patch
from pygls import features, uris
from pygls.types import ClientCapabilities, Diagnostic, InitializeParams

from nose2.tools import such  # type: ignore

from hdl_checker.tests import disableVunit, getTestTempPath

import hdl_checker.lsp
from hdl_checker import server
from hdl_checker.utils import ON_LINUX, ON_WINDOWS, isProcessRunning, terminateProcess

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_LOG_PATH = p.join(os.environ["TOX_ENV_DIR"], "log")
SERVER_LOG_LEVEL = os.environ.get("SERVER_LOG_LEVEL", "WARNING")

HDL_CHECKER_BASE_PATH = p.abspath(p.join(p.dirname(__file__), "..", ".."))

CALL_TIMEOUT = 5

# Static shutdown message to avoid havint to create a server/client pair
LSP_SHUTDOWN = b"\r\n".join(
    [
        b"Content-Length: 102",
        b"Content-Type: application/vscode-jsonrpc; charset=utf-8",
        b"",
        b'{"id": "e7389d0d-4d3c-432d-8506-68a1b2faca48", "jsonrpc": "2.0", "met     hod": "shutdown", "params": null}',
    ]
)


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


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
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _startClient(client):
    client.start()


class _ClientServer(
    object
):  # pylint: disable=useless-object-inheritance,too-few-public-methods
    """ A class to setup a client/server pair """

    def __init__(self):
        #  # Client to Server pipe
        #  csr, csw = os.pipe()
        #  # Server to client pipe
        #  scr, scw = os.pipe()

        #  self.server_thread = Thread(
        #      target=start_io_lang_server,
        #      args=(
        #          os.fdopen(csr, "rb"),
        #          os.fdopen(scw, "wb"),
        #          False,
        #          hdl_checker.lsp.HdlCheckerLanguageServer,
        #      ),
        #  )

        #  self.server_thread.daemon = True
        #  self.server_thread.start()

        #  # Object being tested is the server thread. Avoid both objects
        #  # competing for the same cache by using the raw Python language server
        #  self.client = PythonLanguageServer(
        #      os.fdopen(scr, "rb"), os.fdopen(csw, "wb"), start_io_lang_server
        #  )

        #  self.client_thread = Thread(target=_startClient, args=[self.client])
        #  self.client_thread.daemon = True
        #  self.client_thread.start()

        # Client to Server pipe
        csr, csw = os.pipe()
        # Server to client pipe
        scr, scw = os.pipe()

        self.server = hdl_checker.lsp.HdlCheckerLanguageServer()
        hdl_checker.lsp.setupLanguageServerFeatures(self.server)
        self.server.show_message = lambda *args, **kwargs: _logger.fatal(
            "%s, %s", args, kwargs
        )

        server_thread = Thread(
            target=self.server.start_io,
            args=(os.fdopen(csr, "rb"), os.fdopen(scw, "wb")),
        )

        server_thread.daemon = True
        server_thread.start()

        # Add thread id to the server (just for testing)
        self.server.thread_id = server_thread.ident

        # Setup client
        self.client = hdl_checker.lsp.HdlCheckerLanguageServer(asyncio.new_event_loop())
        self.client_diagnostics = []

        @self.client.feature(features.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
        def dbg_publish(diag: Diagnostic):
            _logger.info("Client received diagnostic: %s", diag)
            self.client_diagnostics.append(diag)

        client_thread = Thread(
            target=self.client.start_io,
            args=(os.fdopen(scr, "rb"), os.fdopen(csw, "wb")),
        )

        client_thread.daemon = True
        client_thread.start()


such.unittest.TestCase.maxDiff = None

with such.A("hdl_checker server") as it:

    _SERVER_BASE_CMD = [
        "coverage",
        "run",
        p.join(HDL_CHECKER_BASE_PATH, "hdl_checker", "server.py"),
        "--log-level",
        SERVER_LOG_LEVEL,
        "--stdout",
        p.join(TEST_LOG_PATH, "hdl_checker-stdout.log"),
        "--stderr",
        p.join(TEST_LOG_PATH, "hdl_checker-stderr.log"),
        "--log-stream",
        p.join(TEST_LOG_PATH, "tests.log"),
    ]

    @it.should("return hdl_checker version")
    @disableVunit
    def test():
        from hdl_checker import server
        from hdl_checker import __version__ as version

        with patch.object(server, "sys") as sys:
            with patch.object(
                server.argparse._sys, "argv", [p.abspath(server.__file__), "--version"]
            ):
                server.parseArguments()

        sys.stdout.write.assert_called_with(version + "\n")
        sys.exit.assert_called_with(0)

    with it.having("http server"):

        def startCodeCheckerServer():
            it._host = "127.0.0.1"
            it._port = str(_getUnusedLocalhostPort())
            it._url = "http://{0}:{1}".format(it._host, it._port)

            cmd = list(_SERVER_BASE_CMD) + ["--host", it._host, "--port", str(it._port)]

            _logger.info("Starting hdl_checker server with '%s'", " ".join(cmd))

            stdout_r, stdout_w = os.pipe()
            stderr_r, stderr_w = os.pipe()

            it.stdout = os.fdopen(stdout_r, "rb")
            it.stderr = os.fdopen(stderr_r, "rb")

            it._server = subp.Popen(
                cmd,
                env=os.environ.copy(),
                stdout=os.fdopen(stdout_w, "wb"),
                stderr=os.fdopen(stderr_w, "wb"),
            )
            waitForServer()

        def startServerAttachedToPid(pid):
            it._url = "http://{0}:{1}".format(it._host, it._port)

            cmd = list(_SERVER_BASE_CMD) + [
                "--host",
                it._host,
                "--port",
                str(it._port),
                "--attach-to-pid",
                str(pid),
            ]

            _logger.info("Starting hdl_checker server with '%s'", " ".join(cmd))

            it._server = subp.Popen(cmd, env=os.environ.copy())
            waitForServer()

        def waitForServer():
            event = Event()

            def wait():
                # Wait until the server is up and replying
                start = time.time()
                while not event.is_set():
                    try:
                        reply = requests.post(it._url + "/get_diagnose_info")
                        if reply.ok:
                            _logger.info(
                                "Server replied OK after %.1fs", time.time() - start
                            )
                            event.set()
                            return
                    except requests.ConnectionError:
                        pass
                    except:
                        _logger.exception(
                            "Exception while waiting for server to respond"
                        )
                        raise

                    time.sleep(0.5)

                _logger.info("Exiting wait thread")

            Thread(target=wait).start()
            # Wait 10s for the server to start responding
            event.wait(timeout=10)

            if event.is_set():
                return

            # Set the event from here to force the wait thread to exit
            event.set()

            _logger.error("Server is not replying")

            it._server.terminate()
            terminateProcess(it._server.pid)

            _logger.error("stderr: %s", it.stderr.read())

            it.fail("Server is not responding")

        def waitUntilBuildFinishes(data):
            _logger.info("Waiting for 30s until build is finished")
            for i in range(30):
                #  time.sleep(1)
                _logger.info("Elapsed %ds", i)
                _ = requests.post(it._url + "/get_messages_by_path", data)
                ui_messages = requests.post(it._url + "/get_ui_messages", data)
                _logger.debug("==> %s", ui_messages.json)
                if ui_messages.json["ui_messages"] == []:
                    _logger.info("Ok, done")
                    return

            assert False, "Server is still building after 30s"

        @it.has_teardown
        def teardown():
            it._server.terminate()
            terminateProcess(it._server.pid)

        @it.should("start and respond a request")  # type: ignore
        @disableVunit
        def test():
            startCodeCheckerServer()
            some_project = _path("some_project")
            open(some_project, "w").write("")
            # Ensure the server is active
            reply = requests.post(
                it._url + "/get_diagnose_info", data={"project_file": some_project}
            )
            it.assertTrue(reply.ok, "Reply was not OK: {}".format(reply))

        @it.should("shutdown the server when requested")  # type: ignore
        @disableVunit
        def test():
            # Send a request to the shutdown addr
            with it.assertRaises(requests.ConnectionError):
                reply = requests.post(it._url + "/shutdown")
                it.assertFalse(reply.ok)

            it._server.terminate()
            terminateProcess(it._server.pid)

        @it.should(  # type: ignore
            "terminate when the parent PID is not running anymore"
        )
        def test():

            queue = Queue()

            proc = Process(target=doNothing, args=(queue,))
            proc.start()

            _logger.info("Started dummy process with PID %d", proc.pid)
            startServerAttachedToPid(proc.pid)
            time.sleep(3)
            _logger.info("Allowing the dummy process to finish")
            queue.put(1)
            proc.join()

            if isProcessRunning(proc.pid):
                _logger.warning("Dummy process %d was still running", proc.pid)
                proc.terminate()
                time.sleep(1)
                it.assertFalse(
                    isProcessRunning(proc.pid),
                    "Process %d is still running after terminating " "it!" % proc.pid,
                )

            time.sleep(1)
            _logger.info("Server should have died by now")

            with it.assertRaises(requests.ConnectionError):
                requests.post(it._url + "/get_diagnose_info")

    with it.having("LSP server"):

        @it.should("initialize with no project file")  # type: ignore
        @disableVunit
        def test():
            client_server = _ClientServer()
            response = client_server.client.lsp.send_request(
                features.INITIALIZE,
                InitializeParams(
                    process_id=1234,
                    capabilities=ClientCapabilities(),
                    root_uri=uris.from_fs_path(TEST_TEMP_PATH),
                ),
            ).result(timeout=CALL_TIMEOUT)

            _logger.debug("Response: %s", response)
            it.assertEqual(response.capabilities.textDocumentSync, 2)
            it.assertEqual(response.capabilities.hoverProvider, True)

            shutdown_response = client_server.client.lsp.send_request(
                features.SHUTDOWN
            ).result(2)
            client_server.client.lsp.notify(features.EXIT)
            it.assertIsNone(shutdown_response)

        @it.should("log to temporary files if files aren't specified")  # type: ignore
        @disableVunit
        def test():
            from hdl_checker import server

            with patch.object(
                server.argparse._sys, "argv", [p.abspath(server.__file__)]
            ):
                args = server.parseArguments()

            it.assertIs(args.log_stream, server.sys.stdout)

            if ON_LINUX:
                it.assertEqual(
                    p.basename(args.stderr),
                    "hdl_checker_stderr_pid{}.log".format(os.getpid()),
                )
            else:
                it.assertTrue(
                    p.basename(args.stderr).startswith("hdl_checker_stderr_pid"),
                    "stderr log should not be {}".format(args.stderr),
                )

    with it.having("LSP server executable"):

        def assertCommandPrints(cmd, stdout, **kwargs):
            _logger.debug("Running command: %s", cmd)
            output = subp.check_output(cmd, **kwargs).decode().strip()
            it.assertEqual(output, stdout)

        @it.should("report version correctly")
        def test():
            assertCommandPrints(["hdl_checker", "--version"], hdl_checker.__version__)

        def startServerWrapper(cmd):
            log_file = tempfile.mktemp()

            actual_cmd = cmd + ["--log-stream", log_file]

            _logger.info("Actual command: %s", actual_cmd)

            proc = subp.Popen(
                actual_cmd, stdin=subp.PIPE, stdout=subp.PIPE, stderr=subp.PIPE
            )

            stdout, stderr = proc.communicate(LSP_SHUTDOWN, timeout=2)

            it.assertEqual(
                stdout, b"", "stdout should be empty but got\n{}".format(stdout)
            )

            it.assertEqual(
                stderr, b"", "stderr should be empty but got\n{}".format(stderr)
            )

            # On Windows the Popen PID and the *actual* PID don't always match
            # for some reason. Since we're not testing this, just skip the
            # first line
            log_content = open(log_file, "rb").read().decode().split("\n")

            expected = [
                "Starting server. Our PID is {}, no parent PID to attach to. "
                "Version string for hdl_checker is '{}'".format(
                    proc.pid, hdl_checker.__version__
                ),
                #  "Starting HdlCheckerLanguageServer IO language server",
            ]

            _logger.info(
                "Log content:\n-----\n%s\n-----\n",
                "\n".join(("> %s" % line for line in log_content)),
            )

            if ON_WINDOWS:
                log_content = log_content[1:]
                expected = expected[1:]

            for line in expected:
                it.assertIn(line, "\n".join(log_content))

            os.remove(log_file)

        @it.should(  # type: ignore
            "start server given the --lsp flag and setting stderr"
        )
        def test():
            startServerWrapper(
                [
                    "hdl_checker",
                    "--lsp",
                    "--stderr",
                    p.join(TEST_LOG_PATH, "hdl_checker_stderr.log"),
                ]
            )

        @it.should("start server given the --lsp flag")  # type: ignore
        def test():
            startServerWrapper(["hdl_checker", "--lsp"])

        @it.should("log to temporary files if files aren't specified")  # type: ignore
        @disableVunit
        def test():
            from hdl_checker import server

            with patch.object(
                server.argparse._sys, "argv", [p.abspath(server.__file__), "--lsp"]
            ):
                args = server.parseArguments()

            if ON_LINUX:
                it.assertEqual(
                    p.basename(args.log_stream),
                    "hdl_checker_log_pid{}.log".format(os.getpid()),
                )

                it.assertEqual(
                    p.basename(args.stderr),
                    "hdl_checker_stderr_pid{}.log".format(os.getpid()),
                )
            else:
                it.assertTrue(
                    p.basename(args.log_stream).startswith("hdl_checker_log_pid"),
                    "log file should not be {}".format(args.stderr),
                )
                it.assertTrue(
                    p.basename(args.stderr).startswith("hdl_checker_stderr_pid"),
                    "stderr file should not be {}".format(args.stderr),
                )

        @it.should("disable writing to log when passing --log-stream NONE")  # type: ignore
        @disableVunit
        def test():
            from hdl_checker import server

            # Check it works with LSP
            with patch.object(
                server.argparse._sys,
                "argv",
                [p.abspath(server.__file__), "--lsp", "--log-stream", "NONE"],
            ):
                args = server.parseArguments()

            it.assertIsNone(args.log_stream)

            # Check it works with HTTP server
            with patch.object(
                server.argparse._sys,
                "argv",
                [p.abspath(server.__file__), "--log-stream", "NONE"],
            ):
                args = server.parseArguments()

            it.assertIsNone(args.log_stream)

        @it.should("disable writing to stderr when passing --stderr NONE")  # type: ignore
        @disableVunit
        def test():
            from hdl_checker import server

            # Check it works with LSP
            with patch.object(
                server.argparse._sys,
                "argv",
                [p.abspath(server.__file__), "--lsp", "--stderr", "NONE"],
            ):
                args = server.parseArguments()

            it.assertIsNone(args.stderr)

            # Check it works with HTTP server
            with patch.object(
                server.argparse._sys,
                "argv",
                [p.abspath(server.__file__), "--stderr", "NONE"],
            ):
                args = server.parseArguments()

            it.assertIsNone(args.stderr)


@patch("hdl_checker.lsp.HdlCheckerLanguageServer.start_io")
@patch("hdl_checker.server._binaryStdio", return_value=("stdin", "stdout"))
@patch("hdl_checker.server._setupPipeRedirection")
def test_StartLsp(redirection, binary_stdio, start_server):
    args = type(
        "args",
        (object,),
        {"lsp": True, "stderr": "stderr", "log_stream": None, "attach_to_pid": None},
    )

    server.run(args)

    redirection.assert_called_once_with(None, "stderr")
    binary_stdio.assert_called_once()
    start_server.assert_called_once_with(stdin="stdin", stdout="stdout")


it.createTests(globals())
