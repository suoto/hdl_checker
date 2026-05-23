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
from threading import Thread

from mock import patch
from pygls import features, uris
from pygls.types import ClientCapabilities, Diagnostic, InitializeParams

from nose2.tools import such  # type: ignore

from hdl_checker.tests import disableVunit, getTestTempPath

import hdl_checker
import hdl_checker.lsp
from hdl_checker import server
from hdl_checker.utils import ON_LINUX, ON_WINDOWS

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


class _ClientServer(
    object
):  # pylint: disable=useless-object-inheritance,too-few-public-methods
    """ A class to setup a client/server pair """

    def __init__(self):
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
        self.server.thread_id = server_thread.ident  # type: ignore[attr-defined]

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

        # Wait for client transport to be ready before returning
        for _ in range(50):
            if self.client.lsp.transport is not None:  # type: ignore[attr-defined]
                break
            time.sleep(0.1)


such.unittest.TestCase.maxDiff = None

with such.A("hdl_checker server") as it:

    _SERVER_BASE_CMD = [
        "coverage",
        "run",
        p.join(HDL_CHECKER_BASE_PATH, "hdl_checker", "server.py"),
        "--log-level",
        SERVER_LOG_LEVEL,
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
                server.argparse._sys, "argv", [p.abspath(server.__file__), "--version"]  # type: ignore[attr-defined]
            ):
                server.parseArguments()

        sys.stdout.write.assert_called_with(version + "\n")
        sys.exit.assert_called_with(0)

    with it.having("LSP server"):

        @it.should("initialize with no project file")  # type: ignore
        @disableVunit
        def test():  # type: ignore[no-redef]
            client_server = _ClientServer()
            response = client_server.client.lsp.send_request(  # type: ignore[attr-defined]
                features.INITIALIZE,
                InitializeParams(
                    process_id=1234,
                    capabilities=ClientCapabilities(),
                    root_uri=uris.from_fs_path(TEST_TEMP_PATH) or "",
                ),
            ).result(timeout=CALL_TIMEOUT)

            _logger.debug("Response: %s", response)
            it.assertEqual(response.capabilities.textDocumentSync, 2)
            it.assertEqual(response.capabilities.hoverProvider, True)

            shutdown_response = client_server.client.lsp.send_request(  # type: ignore[attr-defined]
                features.SHUTDOWN
            ).result(2)
            client_server.client.lsp.notify(features.EXIT)  # type: ignore[attr-defined]
            it.assertIsNone(shutdown_response)

        @it.should("log to temporary files if files aren't specified")  # type: ignore
        @disableVunit
        def test():  # type: ignore[no-redef]
            from hdl_checker import server

            with patch.object(
                server.argparse._sys, "argv", [p.abspath(server.__file__)]  # type: ignore[attr-defined]
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
                    "stderr log should not be {}".format(args.stderr),
                )

    with it.having("LSP server executable"):

        def assertCommandPrints(cmd, stdout, **kwargs):
            _logger.debug("Running command: %s", cmd)
            output = subp.check_output(cmd, **kwargs).decode().strip()
            it.assertEqual(output, stdout)

        @it.should("report version correctly")
        def test():  # type: ignore[no-redef]
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
            "start server and setting stderr"
        )
        def test():  # type: ignore[no-redef]
            startServerWrapper(
                [
                    "hdl_checker",
                    "--stderr",
                    p.join(TEST_LOG_PATH, "hdl_checker_stderr.log"),
                ]
            )

        @it.should("start server")  # type: ignore
        def test():  # type: ignore[no-redef]
            startServerWrapper(["hdl_checker"])

        @it.should("log to temporary files if files aren't specified")  # type: ignore
        @disableVunit
        def test():  # type: ignore[no-redef]
            from hdl_checker import server

            with patch.object(
                server.argparse._sys, "argv", [p.abspath(server.__file__)]  # type: ignore[attr-defined]
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
        def test():  # type: ignore[no-redef]
            from hdl_checker import server

            with patch.object(
                server.argparse._sys,  # type: ignore[attr-defined]
                "argv",
                [p.abspath(server.__file__), "--log-stream", "NONE"],
            ):
                args = server.parseArguments()

            it.assertIsNone(args.log_stream)

        @it.should("disable writing to stderr when passing --stderr NONE")  # type: ignore
        @disableVunit
        def test():  # type: ignore[no-redef]
            from hdl_checker import server

            with patch.object(
                server.argparse._sys,  # type: ignore[attr-defined]
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
        {"stderr": "stderr", "log_stream": None, "attach_to_pid": None},
    )

    server.run(args)

    redirection.assert_called_once_with("stderr")
    binary_stdio.assert_called_once()
    start_server.assert_called_once_with(stdin="stdin", stdout="stdout")


it.createTests(globals())
