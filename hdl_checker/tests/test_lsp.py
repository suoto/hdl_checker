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

# pylint: disable=missing-docstring
# pylint: disable=wrong-import-position
# pylint: disable=no-self-use
# pylint: disable=protected-access
# pylint: disable=function-redefined
# pylint: disable=invalid-name

import asyncio
import json
import logging
import os
import os.path as p
import time
from tempfile import mkdtemp
from threading import Event, Thread, Timer
from typing import Any

import parameterized  # type: ignore
import six
import unittest2  # type: ignore
from mock import MagicMock, patch
from pygls import features, uris
from pygls.types import (
    ClientCapabilities,
    Diagnostic,
    DiagnosticSeverity,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    HoverParams,
    InitializeParams,
    MessageType,
    Position,
    Range,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import Workspace
from pyls_jsonrpc.streams import JsonRpcStreamReader  # type: ignore
from tabulate import tabulate

from nose2.tools import such  # type: ignore

from hdl_checker import DEFAULT_LIBRARY
from hdl_checker.base_server import WatchedFile
from hdl_checker.parsers.elements.dependency_spec import RequiredDesignUnit
from hdl_checker.parsers.elements.design_unit import (
    DesignUnitType,
    VerilogDesignUnit,
    VhdlDesignUnit,
)
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path, TemporaryPath
from hdl_checker.types import Location

from hdl_checker.tests import (  # isort:skip
    assertCountEqual,
    getTestTempPath,
    setupTestSuport,
    TestCase,
)

if six.PY3:
    unicode = str

from hdl_checker import lsp  # isort:skip
from hdl_checker.diagnostics import CheckerDiagnostic, DiagType  # isort:skip
from hdl_checker.utils import ON_WINDOWS  # isort:skip

_logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"
LSP_MSG_TEMPLATE = {"jsonrpc": JSONRPC_VERSION, "id": 1, "processId": None}

LSP_MSG_EMPTY_RESPONSE = {"jsonrpc": JSONRPC_VERSION, "id": 1, "result": None}

LSP_REQUEST_TIMEOUT = 1
MOCK_WAIT_TIMEOUT = 5

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

if ON_WINDOWS:
    TEST_PROJECT = TEST_PROJECT.lower()


class MockWaitTimeout(Exception):
    def __init__(self, msg):
        super(MockWaitTimeout, self).__init__(self)
        self.msg = msg

    def __str__(self):
        return self.msg


class TestCheckerDiagToLspDict(unittest2.TestCase):
    @parameterized.parameterized.expand(
        [
            (DiagType.INFO, DiagnosticSeverity.Information),
            (DiagType.STYLE_INFO, DiagnosticSeverity.Information),
            (DiagType.STYLE_WARNING, DiagnosticSeverity.Information),
            (DiagType.STYLE_ERROR, DiagnosticSeverity.Information),
            (DiagType.WARNING, DiagnosticSeverity.Warning),
            (DiagType.ERROR, DiagnosticSeverity.Error),
            (DiagType.NONE, DiagnosticSeverity.Error),
        ]
    )
    def test_converting_to_lsp(self, diag_type, severity):
        # type: (...) -> Any
        _logger.info("Running %s and %s", diag_type, severity)

        diag = lsp.checkerDiagToLspDict(
            CheckerDiagnostic(
                checker="hdl_checker test",
                text="some diag",
                filename=Path("filename"),
                line_number=0,
                column_number=0,
                error_code="error code",
                severity=diag_type,
            )
        )

        self.assertEqual(diag.code, "error code")
        self.assertEqual(diag.source, "hdl_checker test")
        self.assertEqual(diag.message, "some diag")
        self.assertEqual(diag.severity, severity)
        self.assertEqual(
            diag.range,
            Range(
                start=Position(line=0, character=0), end=Position(line=0, character=0),
            ),
        )

    def test_workspace_notify(self):
        # type: (...) -> Any
        workspace = MagicMock(spec=Workspace)

        server = lsp.Server(
            workspace, root_dir=TemporaryPath(mkdtemp(prefix="hdl_checker_"))
        )
        workspace.show_message.reset_mock()

        server._handleUiInfo("some info")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with("some info", MessageType.Info)
        workspace.show_message.reset_mock()

        server._handleUiWarning("some warning")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            "some warning", MessageType.Warning
        )
        workspace.show_message.reset_mock()

        server._handleUiError("some error")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with("some error", MessageType.Error)


such.unittest.TestCase.maxDiff = None

with such.A("LSP server") as it:
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    def _initializeServer(server, params=None):
        it.assertEqual(
            server.m_initialize(**(params or {})),
            {
                "capabilities": {
                    "textDocumentSync": 1,
                    "definitionProvider": True,
                    "hoverProvider": True,
                    "referencesProvider": True,
                }
            },
        )

        with patch("hdl_checker.lsp.onNewReleaseFound"):
            it.assertEqual(server.m_initialized(), None)

    def startLspServer():
        _logger.debug("Creating server")
        tx_r, tx_w = os.pipe()
        it.tx = JsonRpcStreamReader(os.fdopen(tx_r, "rb"))

        it.rx = MagicMock()
        it.rx.closed = False

        it.server = lsp.HdlCheckerLanguageServer(it.rx, os.fdopen(tx_w, "wb"))

    def stopLspServer():
        _logger.debug("Shutting down server")
        msg = LSP_MSG_TEMPLATE.copy()
        msg.update({"method": "exit"})
        #  it.server._endpoint.consume(msg)

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
            _logger.error("Timed out waiting for %s", meth)
            raise MockWaitTimeout("Timeout waiting for %s" % meth)

        return result

    def checkLintFileOnOpen(source):
        return checkLintFileOnMethod(source, "m_text_document__did_open")

    def checkLintFileOnSave(source):
        return checkLintFileOnMethod(source, "m_text_document__did_save")

    def checkLintFileOnMethod(source, method):
        with patch.object(it.server.workspace, "publish_diagnostics"):
            _logger.info("Sending %s request", method)
            getattr(it.server, method)(
                textDocument={"uri": unicode(uris.from_fs_path(source)), "text": None}
            )

            mock_call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
            doc_uri, diagnostics = mock_call[1]
            _logger.info("doc_uri: %s", doc_uri)
            _logger.info("diagnostics: %s", diagnostics)

            it.assertEqual(doc_uri, uris.from_fs_path(source))
            return diagnostics

    @it.has_setup
    def setup():
        setupTestSuport(TEST_TEMP_PATH)

    @it.should("show info and warning messages")
    @patch("pyls.workspace.Workspace.show_message")
    def test(show_message):
        startLspServer()

        _initializeServer(
            it.server, params={"rootUri": uris.from_fs_path(TEST_PROJECT)}
        )

        # Initialization calls
        show_message.assert_called_with(
            "Searching %s for HDL files..." % TEST_PROJECT, MessageType.Info
        )

        show_message.reset_mock()

        it.server.showWarning("some warning")
        show_message.assert_called_once_with("some warning", MessageType.Warning)

        stopLspServer()

    with it.having("root URI set but no project file"):

        @it.has_setup
        def setup():
            startLspServer()

        @it.has_teardown
        def teardown():
            stopLspServer()

        import hdl_checker

        @it.should("search for files on initialization")  # type: ignore
        @patch.object(WatchedFile, "__init__", return_value=None)
        @patch.object(
            hdl_checker.config_generators.base_generator.BaseGenerator, "generate"
        )
        @patch("hdl_checker.base_server.json.dump", spec=json.dump)
        def test(dump, generate, watched_file):
            _initializeServer(
                it.server, params={"rootUri": uris.from_fs_path(TEST_PROJECT)}
            )
            watched_file.assert_called_once()
            generate.assert_called_once()
            # Will get called twice
            dump.assert_called()

        @it.should("lint file when opening it")  # type: ignore
        def test():
            source = p.join(TEST_PROJECT, "another_library", "foo.vhd")

            with patch(
                "hdl_checker.lsp.Server.getMessagesByPath",
                return_value=[
                    CheckerDiagnostic(filename=Path(source), text="some text")
                ],
            ) as meth:
                it.assertCountEqual(
                    checkLintFileOnOpen(source),
                    [lsp.checkerDiagToLspDict(CheckerDiagnostic(text="some text"))],
                )
                meth.assert_called_once_with(Path(source))

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

            with patch(
                "hdl_checker.lsp.Server.getMessagesByPath",
                return_value=[
                    CheckerDiagnostic(filename=Path(source), text="some text")
                ],
            ) as meth:
                it.assertCountEqual(
                    checkLintFileOnOpen(source),
                    [lsp.checkerDiagToLspDict(CheckerDiagnostic(text="some text"))],
                )
                meth.assert_called_once_with(Path(source))

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

            with patch(
                "hdl_checker.lsp.Server.getMessagesByPath",
                return_value=[
                    CheckerDiagnostic(filename=Path(source), text="some text")
                ],
            ) as meth:
                it.assertCountEqual(
                    checkLintFileOnOpen(source),
                    [lsp.checkerDiagToLspDict(CheckerDiagnostic(text="some text"))],
                )
                meth.assert_called_once_with(Path(source))

    @it.should("lint file with neither root URI nor project file set")  # type: ignore
    def test():
        startLspServer()

        _initializeServer(
            it.server, params={"initializationOptions": {"project_file": None}}
        )

        source = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")
        checkLintFileOnOpen(source)

        stopLspServer()

    @it.should("lint file with no root URI but project file set")  # type: ignore
    def test():
        startLspServer()

        _initializeServer(
            it.server,
            params={
                "rootUri": None,
                "initializationOptions": {
                    "project_file": p.join(TEST_PROJECT, "vimhdl.prj")
                },
            },
        )

        source = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")
        checkLintFileOnOpen(source)

        stopLspServer()


class TestValidProject(TestCase):

    params = {
        "rootUri": uris.from_fs_path(TEST_PROJECT),
        "initializationOptions": {"project_file": "config.json"},
        "processId": 0,
    }

    def setUp(self):
        _logger.fatal("############################################")
        setupTestSuport(TEST_TEMP_PATH)

        _logger.debug("Creating server")

        # Client to Server pipe
        csr, csw = os.pipe()
        # Server to client pipe
        scr, scw = os.pipe()

        self.server = lsp.HdlCheckerLanguageServer()
        lsp.setupLanguageServerFeatures(self.server)
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
        self.client = lsp.HdlCheckerLanguageServer(asyncio.new_event_loop())
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

        self.client.lsp.send_request(
            features.INITIALIZE,
            InitializeParams(
                process_id=0,
                capabilities=ClientCapabilities(),
                root_uri=uris.from_fs_path(TEST_PROJECT),
                initialization_options={"project_file": "config.json"},
            ),
        ).result(timeout=LSP_REQUEST_TIMEOUT)

        self.client.lsp.send_request(features.INITIALIZED).result(
            timeout=LSP_REQUEST_TIMEOUT
        )

        #  _logger.info("Calling m_initialized")
        #  with patch("hdl_checker.lsp.onNewReleaseFound"):
        #      self.assertIsNone(self.server.m_initialized())

    def tearDown(self):
        _logger.debug("Shutting down server")
        shutdown_response = self.client.lsp.send_request(features.SHUTDOWN).result(
            timeout=2
        )
        assert shutdown_response is None
        self.client.lsp.notify(features.EXIT)

        #  msg = LSP_MSG_TEMPLATE.copy()
        #  msg.update({"method": "exit"})
        #  self.server._endpoint.consume(msg)

        #  # Close the pipe from the server to stdout and empty any pending
        #  # messages
        #  self.tx_stream_reader.close()
        #  self.tx_stream_reader.listen(_logger.fatal)

        del self.server

    def _checkLintFileOnOpen(self, source):
        return self._checkLintFileOnMethod(source, "m_text_document__did_open")

    def _checkLintFileOnSave(self, source):
        return self._checkLintFileOnMethod(source, "m_text_document__did_save")

    def _checkLintFileOnMethod(self, source, method):
        with patch.object(self.server, "publish_diagnostics"):
            _logger.info("Sending %s request", method)
            getattr(self.server, method)(
                textDocument={"uri": unicode(uris.from_fs_path(source)), "text": None}
            )

            mock_call = _waitOnMockCall(self.server.workspace.publish_diagnostics)
            doc_uri, diagnostics = mock_call[1]
            _logger.info("doc_uri: %s", doc_uri)
            _logger.info("diagnostics: %s", diagnostics)

            self.assertEqual(doc_uri, uris.from_fs_path(source))
            return diagnostics

    def test_LintFileOnOpening(self):
        source = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
        with patch(
            "hdl_checker.lsp.Server.getMessagesByPath",
            return_value=[CheckerDiagnostic(filename=Path(source), text="some text")],
        ) as meth:

            self.assertFalse(self.client_diagnostics)  # Shouldn't have prev diags
            self.client.lsp.send_request(
                features.TEXT_DOCUMENT_DID_OPEN,
                DidOpenTextDocumentParams(
                    TextDocumentItem(
                        uris.from_fs_path(source),
                        language_id="vhdl",
                        version=0,
                        text="",
                    )
                ),
            ).result(timeout=LSP_REQUEST_TIMEOUT)

            _logger.fatal("%s", self.client_diagnostics[0])
            _logger.fatal("dir: %s", dir(self.client_diagnostics[0]))

            self.assertItemsEqual(
                [x.uri for x in self.client_diagnostics], [uris.from_fs_path(source),],
            )

            self.assertItemsEqual(
                [(x.message,) for x in self.client_diagnostics.pop().diagnostics],
                [("some text",)],
            )

            meth.assert_called_once_with(Path(source))

    def runTestBuildSequenceTable(self, tablefmt):
        _logger.fatal("############################################")
        very_common_pkg = Path(
            p.join(TEST_PROJECT, "basic_library", "very_common_pkg.vhd")
        )
        clk_en_generator = Path(
            p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
        )

        expected = [
            "Build sequence for %s is" % str(clk_en_generator),
            "",
            tabulate(
                [
                    (1, "basic_library", str(very_common_pkg)),
                    (2, DEFAULT_LIBRARY.name, str(clk_en_generator)),
                ],
                headers=("#", "Library", "Path"),
                tablefmt=tablefmt,
            ),
        ]

        self.maxDiff = None
        try:
            got = self.server._getBuildSequenceForHover(clk_en_generator)
            self.assertEqual(got, "\n".join(expected))
        except:
            _logger.error(
                "Gotten\n\n%s\n\nExpected\n\n%s\n\n", got, "\n".join(expected)
            )
            raise

    @patch("hdl_checker.lsp.HdlCheckerLanguageServer._use_markdown_for_hover", 0)
    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_ReportBuildSequencePlain(self):
        self.runTestBuildSequenceTable(tablefmt="plain")

    @patch("hdl_checker.lsp.HdlCheckerLanguageServer._use_markdown_for_hover", 1)
    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_ReportBuildSequenceMarkdown(self):
        self.runTestBuildSequenceTable(tablefmt="github")

    @patch.object(
        hdl_checker.base_server.BaseServer,
        "resolveDependencyToPath",
        lambda self, _: None,
    )
    def test_DependencyInfoForPathNotFound(self):
        path = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))
        dependency = RequiredDesignUnit(
            name=Identifier("clock_divider"),
            library=Identifier("basic_library"),
            owner=path,
            locations=(),
        )
        self.assertEqual(
            self.server._getDependencyInfoForHover(dependency),
            "Couldn't find a source defining 'basic_library.clock_divider'",
        )

    @patch.object(
        hdl_checker.base_server.BaseServer,
        "resolveDependencyToPath",
        lambda self, _: (Path("some_path"), Identifier("some_library")),
    )
    def test_ReportDependencyInfo(self):
        path = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))
        dependency = RequiredDesignUnit(
            name=Identifier("clock_divider"),
            library=Identifier("basic_library"),
            owner=path,
            locations=(),
        )
        self.assertEqual(
            self.server._getDependencyInfoForHover(dependency),
            'Path "some_path", library "some_library"',
        )

    def test_ReportDesignUnitAccordingToPosition(self):
        UNIT_A = VhdlDesignUnit(
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            type_=DesignUnitType.entity,
            name="unit_a",
            locations=(Location(line=1, column=2), Location(line=3, column=4)),
        )

        UNIT_B = VerilogDesignUnit(
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            type_=DesignUnitType.package,
            name="unit_b",
            locations=(Location(line=5, column=6), Location(line=7, column=8)),
        )

        DEP_A = RequiredDesignUnit(
            name=Identifier("dep_a"),
            library=Identifier("lib_a"),
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            locations=(Location(line=9, column=10), Location(line=11, column=12)),
        )

        DEP_B = RequiredDesignUnit(
            name=Identifier("dep_a"),
            library=Identifier("lib_a"),
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            locations=(Location(line=13, column=14), Location(line=15, column=16)),
        )

        def getDesignUnitsByPath(self, path):  # pylint: disable=unused-argument
            if path != Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")):
                it.fail("Expected foo.vhd but got %s" % path)
            return {UNIT_A, UNIT_B}

        def getDependenciesByPath(self, path):  # pylint: disable=unused-argument
            if path != Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")):
                it.fail("Expected foo.vhd but got %s" % path)
            return {DEP_A, DEP_B}

        patches = (
            patch.object(
                hdl_checker.database.Database,
                "getDesignUnitsByPath",
                getDesignUnitsByPath,
            ),
            patch.object(
                hdl_checker.database.Database,
                "getDependenciesByPath",
                getDependenciesByPath,
            ),
        )

        path = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))

        for _patch in patches:
            _patch.start()

        # Check locations outside return nothing
        self.assertIsNone(self.server._getElementAtPosition(path, Location(0, 0)))

        # Check design units are found, ensure boundaries match
        self.assertIsNone(self.server._getElementAtPosition(path, Location(1, 1)))
        self.assertIs(self.server._getElementAtPosition(path, Location(1, 2)), UNIT_A)
        self.assertIs(self.server._getElementAtPosition(path, Location(1, 7)), UNIT_A)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(1, 8)))

        self.assertIsNone(self.server._getElementAtPosition(path, Location(3, 3)))
        self.assertIs(self.server._getElementAtPosition(path, Location(3, 4)), UNIT_A)
        self.assertIs(self.server._getElementAtPosition(path, Location(3, 9)), UNIT_A)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(3, 10)))

        self.assertIsNone(self.server._getElementAtPosition(path, Location(5, 5)))
        self.assertIs(self.server._getElementAtPosition(path, Location(5, 6)), UNIT_B)
        self.assertIs(self.server._getElementAtPosition(path, Location(5, 11)), UNIT_B)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(5, 12)))

        self.assertIsNone(self.server._getElementAtPosition(path, Location(7, 7)))
        self.assertIs(self.server._getElementAtPosition(path, Location(7, 8)), UNIT_B)
        self.assertIs(self.server._getElementAtPosition(path, Location(7, 13)), UNIT_B)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(7, 14)))

        # Now check dependencies
        self.assertIsNone(self.server._getElementAtPosition(path, Location(9, 9)))
        self.assertIs(self.server._getElementAtPosition(path, Location(9, 10)), DEP_A)
        self.assertIs(self.server._getElementAtPosition(path, Location(9, 20)), DEP_A)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(9, 21)))

        self.assertIsNone(self.server._getElementAtPosition(path, Location(11, 11)))
        self.assertIs(self.server._getElementAtPosition(path, Location(11, 12)), DEP_A)
        self.assertIs(self.server._getElementAtPosition(path, Location(11, 22)), DEP_A)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(11, 23)))

        self.assertIsNone(self.server._getElementAtPosition(path, Location(13, 13)))
        self.assertIs(self.server._getElementAtPosition(path, Location(13, 14)), DEP_B)
        self.assertIs(self.server._getElementAtPosition(path, Location(13, 24)), DEP_B)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(13, 25)))

        self.assertIsNone(self.server._getElementAtPosition(path, Location(15, 15)))
        self.assertIs(self.server._getElementAtPosition(path, Location(15, 16)), DEP_B)
        self.assertIs(self.server._getElementAtPosition(path, Location(15, 26)), DEP_B)
        self.assertIsNone(self.server._getElementAtPosition(path, Location(15, 27)))

        for _patch in patches:
            _patch.stop()

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_HoverOnInvalidRange(self):
        path = p.join(TEST_PROJECT, "another_library", "foo.vhd")
        self.assertIsNone(
            self.client.lsp.send_request(
                features.HOVER,
                HoverParams(
                    TextDocumentIdentifier(uris.from_fs_path(path)),
                    Position(line=0, character=0),
                ),
            ).result(timeout=LSP_REQUEST_TIMEOUT)
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_HoverOnDesignUnit(self):
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")
        very_common_pkg = p.join(TEST_PROJECT, "basic_library", "very_common_pkg.vhd")
        package_with_constants = p.join(
            TEST_PROJECT, "basic_library", "package_with_constants.vhd"
        )
        clock_divider = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")

        expected = [
            "Build sequence for %s is" % str(path_to_foo),
            "",
            tabulate(
                [
                    (1, "basic_library", str(very_common_pkg)),
                    (2, "basic_library", str(package_with_constants)),
                    (3, "basic_library", str(clock_divider)),
                    (4, DEFAULT_LIBRARY.name, str(path_to_foo)),
                ],
                headers=("#", "Library", "Path"),
                tablefmt="plain",
            ),
        ]

        response = self.client.lsp.send_request(
            features.HOVER,
            HoverParams(
                TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                Position(line=7, character=7),
            ),
        ).result(timeout=LSP_REQUEST_TIMEOUT)

        self.assertEqual(
            response.contents, "\n".join(expected),
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_HoverOnDependency(self):
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")
        clock_divider = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")

        self.assertEqual(
            self.client.lsp.send_request(
                features.HOVER,
                HoverParams(
                    TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                    Position(line=32, character=32),
                ),
            )
            .result(timeout=LSP_REQUEST_TIMEOUT)
            .contents,
            'Path "%s", library "basic_library"' % clock_divider,
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_GetDefinitionMatchingDependency(self):
        source = p.join(TEST_PROJECT, "basic_library", "use_entity_a_and_b.vhd")
        target = p.join(TEST_PROJECT, "basic_library", "two_entities_one_file.vhd")

        definitions = self.server.definitions(
            uris.from_fs_path(source), {"line": 1, "character": 9}
        )

        self.assertIn(
            {
                "uri": uris.from_fs_path(target),
                "range": {
                    "start": {"line": 1, "character": 7},
                    "end": {"line": 1, "character": 15},
                },
            },
            definitions,
        )

        self.assertIn(
            {
                "uri": uris.from_fs_path(target),
                "range": {
                    "start": {"line": 4, "character": 7},
                    "end": {"line": 4, "character": 15},
                },
            },
            definitions,
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_GetDefinitionBuiltInLibrary(self):
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        self.assertEqual(
            self.server.definitions(
                uris.from_fs_path(path_to_foo), {"line": 3, "character": 15}
            ),
            [],
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_GetDefinitionNotKnown(self):
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        self.assertEqual(
            self.server.definitions(
                uris.from_fs_path(path_to_foo), {"line": 0, "character": 0}
            ),
            [],
        )

    @patch.object(
        hdl_checker.database.Database,
        "getReferencesToDesignUnit",
        return_value=[
            RequiredDesignUnit(
                name=Identifier("clock_divider"),
                library=Identifier("basic_library"),
                owner=Path("some_path"),
                locations=(Location(1, 2), Location(3, 4)),
            )
        ],
    )
    def test_ReferencesOfAValidElement(self, get_references):
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        # Make sure we picked up an existing element
        unit = self.server._getElementAtPosition(Path(path_to_foo), Location(7, 7))
        self.assertIsNotNone(unit)

        self.assertCountEqual(
            self.server.references(
                doc_uri=uris.from_fs_path(path_to_foo),
                position={"line": 7, "character": 7},
                exclude_declaration=True,
            ),
            (
                {
                    "uri": uris.from_fs_path("some_path"),
                    "range": {
                        "start": {"line": 1, "character": 2},
                        "end": {"line": 1, "character": 2},
                    },
                },
                {
                    "uri": uris.from_fs_path("some_path"),
                    "range": {
                        "start": {"line": 3, "character": 4},
                        "end": {"line": 3, "character": 4},
                    },
                },
            ),
        )

        get_references.assert_called_once()
        get_references.reset_mock()

        self.assertCountEqual(
            self.server.references(
                doc_uri=uris.from_fs_path(path_to_foo),
                position={"line": 7, "character": 7},
                exclude_declaration=False,
            ),
            (
                {
                    "uri": uris.from_fs_path(path_to_foo),
                    "range": {
                        "start": {"line": 7, "character": 7},
                        "end": {"line": 7, "character": 7},
                    },
                },
                {
                    "uri": uris.from_fs_path("some_path"),
                    "range": {
                        "start": {"line": 1, "character": 2},
                        "end": {"line": 1, "character": 2},
                    },
                },
                {
                    "uri": uris.from_fs_path("some_path"),
                    "range": {
                        "start": {"line": 3, "character": 4},
                        "end": {"line": 3, "character": 4},
                    },
                },
            ),
        )

    def test_ReferencesOfAnInvalidElement(self):
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        # Make sure there's no element at this location
        unit = self.server._getElementAtPosition(Path(path_to_foo), Location(0, 0))
        self.assertIsNone(unit)

        for exclude_declaration in (True, False):
            self.assertIsNone(
                self.server.references(
                    doc_uri=uris.from_fs_path(path_to_foo),
                    position={"line": 0, "character": 0},
                    exclude_declaration=exclude_declaration,
                )
            )


it.createTests(globals())
