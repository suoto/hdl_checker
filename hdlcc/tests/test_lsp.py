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

# pylint: disable=missing-docstring
# pylint: disable=wrong-import-position
# pylint: disable=no-self-use
# pylint: disable=protected-access
# pylint: disable=function-redefined

import logging
import os
import os.path as p
import time
from threading import Event, Timer

import mock
import parameterized  # type: ignore
import pyls  # type: ignore
import six
import unittest2  # type: ignore
from pyls import lsp as defines
from pyls import uris
from pyls.workspace import Workspace  # type: ignore
from pyls_jsonrpc.streams import JsonRpcStreamReader  # type: ignore

from nose2.tools import such  # type: ignore

from hdlcc.tests.utils import (  # isort:skip
    assertCountEqual,
    getTestTempPath,
    setupTestSuport,
)


# Debouncing will hurt testing since it won't actually call the debounced
# function if we call it too quickly.
def _debounce(interval_s, keyed_by=None):  # pylint: disable=unused-argument
    def wrapper(func):
        def debounced(*args, **kwargs):
            result = func(*args, **kwargs)
            _logger.info("%s(%s, %s) returned %s", func.__name__, args, kwargs, result)
            return result

        return debounced

    return wrapper


# Mock debounce before it's applied
pyls._utils.debounce = _debounce

from hdlcc import lsp  # isort:skip
from hdlcc.diagnostics import CheckerDiagnostic, DiagType  # isort:skip
from hdlcc.utils import onWindows  # isort:skip

_logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"
LSP_MSG_TEMPLATE = {"jsonrpc": JSONRPC_VERSION, "id": 1, "processId": None}

LSP_MSG_EMPTY_RESPONSE = {"jsonrpc": JSONRPC_VERSION, "id": 1, "result": None}

MOCK_WAIT_TIMEOUT = 5

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

if onWindows():
    TEST_PROJECT = TEST_PROJECT.lower()


class TestCheckerDiagToLspDict(unittest2.TestCase):
    @parameterized.parameterized.expand(
        [
            (DiagType.INFO, defines.DiagnosticSeverity.Hint),
            (DiagType.STYLE_INFO, defines.DiagnosticSeverity.Hint),
            (DiagType.STYLE_WARNING, defines.DiagnosticSeverity.Information),
            (DiagType.STYLE_ERROR, defines.DiagnosticSeverity.Information),
            (DiagType.WARNING, defines.DiagnosticSeverity.Warning),
            (DiagType.ERROR, defines.DiagnosticSeverity.Error),
            (DiagType.NONE, defines.DiagnosticSeverity.Error),
        ]
    )
    def test_converting_to_lsp(self, diag_type, severity):
        _logger.info("Running %s and %s", diag_type, severity)

        diag = CheckerDiagnostic(
            checker="hdlcc test",
            text="some diag",
            filename="filename",
            line_number=1,
            column_number=1,
            error_code="error code",
            severity=diag_type,
        )

        self.assertEqual(
            lsp.checkerDiagToLspDict(diag),
            {
                "source": "hdlcc test",
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 0},
                },
                "message": "some diag",
                "severity": severity,
                "code": "error code",
            },
        )

    def test_workspace_notify(self):
        workspace = mock.MagicMock(spec=Workspace)

        server = lsp.HdlCodeCheckerServer(workspace, root_path=None)

        server._handleUiInfo("some info")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            "some info", defines.MessageType.Info
        )
        workspace.show_message.reset_mock()

        server._handleUiWarning("some warning")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            "some warning", defines.MessageType.Warning
        )
        workspace.show_message.reset_mock()

        server._handleUiError("some error")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            "some error", defines.MessageType.Error
        )


with such.A("LSP server") as it:
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    def _initializeServer(server, params=None):
        it.assertEqual(
            server.m_initialize(**(params or {})),
            {"capabilities": {"textDocumentSync": 1}},
        )

        it.assertEqual(server.m_initialized(), None)

    def startLspServer():
        _logger.debug("Creating server")
        tx_r, tx_w = os.pipe()
        it.tx = JsonRpcStreamReader(os.fdopen(tx_r, "rb"))

        it.rx = mock.MagicMock()
        it.rx.closed = False

        it.server = lsp.HdlccLanguageServer(it.rx, os.fdopen(tx_w, "wb"))

    def stopLspServer():
        _logger.debug("Shutting down server")
        msg = LSP_MSG_TEMPLATE.copy()
        msg.update({"method": "exit"})
        it.server._endpoint.consume(msg)

        # Close the pipe from the server to stdout and empty any pending
        # messages
        it.tx.close()
        it.tx.listen(_logger.fatal)

        del it.server

    def _waitOnMockCall(meth):
        event = Event()

        timer = Timer(MOCK_WAIT_TIMEOUT, event.set)
        timer.start()

        result = []
        while not event.isSet():
            if meth.mock_calls:
                result = meth.mock_calls[0]
                timer.cancel()
                break

            time.sleep(0.1)

        if event.isSet():
            it.fail("Timeout waiting for %s" % meth)

        return result

    def checkLintFileOnOpen(source):
        return checkLintFileOnMethod(source, "m_text_document__did_open")

    def checkLintFileOnSave(source):
        return checkLintFileOnMethod(source, "m_text_document__did_save")

    def checkLintFileOnMethod(source, method):
        with mock.patch.object(it.server.workspace, "publish_diagnostics"):
            _logger.info("Sending %s request", method)
            getattr(it.server, method)(
                textDocument={"uri": uris.from_fs_path(source), "text": None}
            )

            call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
            doc_uri, diagnostics = call[1]
            _logger.info("doc_uri: %s", doc_uri)
            _logger.info("diagnostics: %s", diagnostics)

            it.assertEqual(doc_uri, uris.from_fs_path(source))
            return diagnostics

    @it.has_setup
    def setup():
        setupTestSuport(TEST_TEMP_PATH)

    with it.having("no project file"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        @it.should("respond capabilities upon initialization")
        def test():
            _initializeServer(
                it.server, params={"rootUri": uris.from_fs_path(TEST_PROJECT)}
            )

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "another_library", "foo.vhd")

            it.assertCountEqual(
                checkLintFileOnOpen(source),
                [
                    {
                        "source": "HDL Code Checker/static",
                        "range": {
                            "start": {"line": 28, "character": 11},
                            "end": {"line": 28, "character": 11},
                        },
                        "message": "Signal 'neat_signal' is never used",
                        "severity": defines.DiagnosticSeverity.Information,
                    }
                ],
            )

        @it.should("not lint file outside workspace")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")
            with it.assertRaises(AssertionError):
                checkLintFileOnSave(source)

    with it.having("an existing and valid old style project file"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        @it.should("respond capabilities upon initialization")  # type: ignore
        def test():
            _initializeServer(
                it.server,
                params={
                    "rootUri": uris.from_fs_path(TEST_PROJECT),
                    "initializationOptions": {"project_file": "vimhdl.prj"},
                },
            )

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

            it.assertCountEqual(checkLintFileOnOpen(source), [])

    with it.having("an existing and valid JSON config file"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        @it.should("respond capabilities upon initialization")  # type: ignore
        def test():
            _initializeServer(
                it.server,
                params={
                    "rootUri": uris.from_fs_path(TEST_PROJECT),
                    "initializationOptions": {"project_file": "config.json"},
                },
            )
            it.assertTrue(it.server._checker.database._paths)

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
            it.assertCountEqual(checkLintFileOnOpen(source), [])

        #  @it.should("clean up if the project file has been modified") # type: ignore
        #  def test():
        #      source = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

        #      og_timestamp = p.getmtime(it.server._checker.project_file)

        #      content = open(it.server._checker.project_file).read()
        #      open(it.server._checker.project_file, "a").write("\n# foo")
        #      curr_ts = p.getmtime(it.server._checker.project_file)

        #      _logger.info(
        #          "Original timestamp: %s, current timestamp: %s", og_timestamp, curr_ts
        #      )

        #      it.assertNotEqual(og_timestamp, curr_ts, "Timestamps are still equal??")

        #      with mock.patch.object(it.server.workspace, "publish_diagnostics"):
        #          with mock.patch.object(it.server._checker, "clean") as clean:

        #              _logger.info("Sending m_text_document__did_save request")
        #              it.server.m_text_document__did_save(
        #                  textDocument={"uri": uris.from_fs_path(source), "text": None}
        #              )

        #              call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
        #              doc_uri, diagnostics = call[1]
        #              _logger.info("doc_uri: %s", doc_uri)
        #              _logger.info("diagnostics: %s", diagnostics)

        #              clean.assert_called_once()

        #      # Restore the original content (which will change the timestamp)
        #      # and request a message so that parsing occurs here
        #      open(it.server._checker.project_file, "w").write(content)
        #      it.assertEqual(content, open(it.server._checker.project_file).read())

        #      it.server.m_text_document__did_save(
        #          textDocument={"uri": uris.from_fs_path(source), "text": None}
        #      )

        #  @it.should("rebuild if the cache file has been removed") # type: ignore
        #  def test():
        #      # type: (...) -> Any
        #      server = startLspServer()

        #      source = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

        #      os.remove(str(it.server._checker._getCacheFilename()))

        #      def getBuilderName():
        #          return "msim"

        #      with mock.patch.object(it.server.workspace, "publish_diagnostics"):
        #          with mock.patch.object(it.server._checker, "clean") as clean:
        #          #      with mock.patch.object(
        #          #          it.server._checker.config_parser,
        #          #          "getBuilderName",
        #          #          getBuilderName,
        #          #      ):

        #              _logger.info("Sending m_text_document__did_save request")
        #              it.server.m_text_document__did_save(
        #                  textDocument={
        #                      "uri": uris.from_fs_path(source),
        #                      "text": None,
        #                  }
        #              )

        #              call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
        #              doc_uri, diagnostics = call[1]
        #              _logger.info("doc_uri: %s", doc_uri)
        #              _logger.info("diagnostics: %s", diagnostics)

        #              clean.assert_called()

    with it.having("a non existing project file"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        @it.should("respond capabilities upon initialization")  # type: ignore
        def test():
            it.project_file = "__some_project_file.prj"
            it.assertFalse(p.exists(it.project_file))

            _initializeServer(
                it.server,
                params={
                    "rootUri": uris.from_fs_path(TEST_PROJECT),
                    "initializationOptions": {"project_file": it.project_file},
                },
            )

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "another_library", "foo.vhd")
            diagnostics = checkLintFileOnOpen(source)

            it.assertCountEqual(
                diagnostics,
                [
                    {
                        "source": "HDL Code Checker/static",
                        "range": {
                            "start": {"line": 28, "character": 11},
                            "end": {"line": 28, "character": 11},
                        },
                        "message": "Signal 'neat_signal' is never used",
                        "severity": defines.DiagnosticSeverity.Information,
                    },
                ],
            )

    with it.having("neither root URI nor project file set"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        @it.should("respond capabilities upon initialization")  # type: ignore
        def test():
            _initializeServer(
                it.server, params={"initializationOptions": {"project_file": None}}
            )

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")

            it.assertCountEqual(
                checkLintFileOnOpen(source),
                [
                    {
                        "source": "HDL Code Checker/static",
                        "range": {
                            "start": {"line": 26, "character": 11},
                            "end": {"line": 26, "character": 11},
                        },
                        "message": "Signal 'clk_enable_unused' is never used",
                        "severity": defines.DiagnosticSeverity.Information,
                    }
                ],
            )

    with it.having("no root URI but project file set"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        @it.should("respond capabilities upon initialization")  # type: ignore
        def test():
            # In this case, project file is an absolute path, since there's no
            # root URI
            _initializeServer(
                it.server,
                params={
                    "initializationOptions": {
                        "project_file": p.join(TEST_PROJECT, "vimhdl.prj")
                    }
                },
            )

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

            it.assertCountEqual(checkLintFileOnOpen(source), [])


it.createTests(globals())
