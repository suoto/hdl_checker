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

import asyncio
import json
import logging
import os
import os.path as p
from threading import Thread
from typing import Any, List, Optional, Union

import unittest2  # type: ignore
from mock import patch
from pygls import features, uris
from pygls.server import LanguageServer
from pygls.types import (
    ClientCapabilities,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    HoverAbstract,
    HoverParams,
    InitializeParams,
    MarkupKind,
    Position,
    PublishDiagnosticsAbstract,
    Range,
    ReferenceContext,
    ReferenceParams,
    TextDocumentClientCapabilities,
    TextDocumentContentChangeEvent,
    TextDocumentIdentifier,
    TextDocumentItem,
    TextDocumentPositionParams,
    VersionedTextDocumentIdentifier,
)
from tabulate import tabulate

from hdl_checker.tests import getTestTempPath, setupTestSuport, toCheckerDiagnostic

import hdl_checker
from hdl_checker import DEFAULT_LIBRARY, lsp
from hdl_checker.diagnostics import CheckerDiagnostic
from hdl_checker.parsers.elements.dependency_spec import RequiredDesignUnit
from hdl_checker.parsers.elements.design_unit import (
    DesignUnitType,
    VerilogDesignUnit,
    VhdlDesignUnit,
)
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import Location
from hdl_checker.utils import ON_WINDOWS

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")
LSP_REQUEST_TIMEOUT = 3

_CLIENT_CAPABILITIES = ClientCapabilities(
    text_document=TextDocumentClientCapabilities(
        synchronization=None,  # type: ignore
        completion=None,  # type: ignore
        hover=HoverAbstract(
            dynamic_registration=False, content_format=[MarkupKind.PlainText,],
        ),
        signature_help=None,  # type:ignore
        references=None,  # type:ignore
        document_highlight=None,  # type:ignore
        document_symbol=None,  # type:ignore
        formatting=None,  # type:ignore
        range_formatting=None,  # type:ignore
        on_type_formatting=None,  # type:ignore
        definition=None,  # type:ignore
        type_definition=None,  # type:ignore
        implementation=None,  # type:ignore
        code_action=None,  # type:ignore
        code_lens=None,  # type:ignore
        document_link=None,  # type:ignore
        color_provider=None,  # type:ignore
        rename=None,  # type:ignore
        publish_diagnostics=PublishDiagnosticsAbstract(related_information=True),
        folding_range=None,  # type:ignore
    )
)

if ON_WINDOWS:
    TEST_PROJECT = TEST_PROJECT.lower()


class _LspHelper(unittest2.TestCase):
    def _createClientServerPair(self, params: Optional[InitializeParams]):
        # pylint: disable=attribute-defined-outside-init
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")

        # Client to Server pipe
        csr, csw = os.pipe()
        # Server to client pipe
        scr, scw = os.pipe()

        # Setup server
        self.server = lsp.HdlCheckerLanguageServer()
        lsp.setupLanguageServerFeatures(self.server)

        self.server_diagnostics = []  # type: ignore

        @self.server.feature(features.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
        def serverPublishDiagnosticsHandler(diag):  # pylint: disable=unused-variable
            _logger.info("Publishing diagnostic: %s", diag)
            self.server_diagnostics.append(diag)

        self.server_thread = Thread(
            target=self.server.start_io,
            args=(os.fdopen(csr, "rb"), os.fdopen(scw, "wb")),
        )

        self.server_thread.daemon = True
        self.server_thread.name = "server"
        self.server_thread.start()

        # Add thread id to the server (just for testing)
        self.server.thread_id = self.server_thread.ident  # type: ignore

        # Setup client (client doesn't need the HDL checker stuff)
        self.client = LanguageServer(asyncio.new_event_loop())
        self.client_messages = []  # type: ignore
        self.client_diagnostics = []  # type: ignore

        @self.client.feature(features.WINDOW_SHOW_MESSAGE)
        def clientShowMessageHandler(*args):  # pylint: disable=unused-variable
            type_ = DiagnosticSeverity(args[0][0])
            msg = args[0][1]
            _logger.info("[Client] [%s]: %s", type_, msg)
            self.client_messages.append((type_, msg))

        @self.client.feature(features.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
        def clientPublishDiagnosticsHandler(diag):  # pylint: disable=unused-variable
            _logger.info("Publishing diagnostic: %s", diag)
            self.client_diagnostics.append(diag)

        self.client_thread = Thread(
            target=self.client.start_io,
            args=(os.fdopen(scr, "rb"), os.fdopen(csw, "wb")),
        )

        self.client_thread.daemon = True
        self.client_thread.name = "client"
        self.client_thread.start()

        if params is None:
            _logger.info("No parameters given, won't initialize server")
            return

        _logger.info("Sending initialize request")
        self.client.lsp.send_request(features.INITIALIZE, params).result(
            LSP_REQUEST_TIMEOUT
        )

        _logger.info("Sending initialized request")
        self.client.lsp.send_request(features.INITIALIZED).result(LSP_REQUEST_TIMEOUT)
        _logger.info("Client server setup complete")

    def tearDown(self):  # pylint:disable=inconsistent-return-statements
        if self.__class__ is _LspHelper:
            self.assertIsNone(getattr(self, "server", None))
            self.assertIsNone(getattr(self, "client", None))
            return unittest2.skip("Won't run this on %s" % self.__class__)
        _logger.info("#" * 100)
        _logger.info("Shutting down server")
        shutdown_response = self.client.lsp.send_request(features.SHUTDOWN).result(
            LSP_REQUEST_TIMEOUT
        )
        self.client.lsp.notify(features.EXIT)
        self.assertIsNone(shutdown_response)
        # pygls server has cleanup routines run when the interpreter is
        # exiting, at which point the client will be long gone. This results in
        # RuntimeError: cannot schedule new futures after shutdown. To work
        # around this, we're accessing its itnernal event to force it to exit
        self.client._stop_event.set()
        self.server_thread.join()
        self.client_thread.join()

    def checkLintFileOnMethod(
        self,
        params: Union[
            DidOpenTextDocumentParams,
            DidSaveTextDocumentParams,
            DidChangeTextDocumentParams,
        ],
        expected_diags=List[CheckerDiagnostic],
    ):
        """
        Generic method to check diagnostics reported are correct
        """
        filename = uris.to_fs_path(params.textDocument.uri)
        _logger.info("Checking lint of file %s, event is %s", filename, type(params))
        assert isinstance(
            params,
            (
                DidOpenTextDocumentParams,
                DidSaveTextDocumentParams,
                DidChangeTextDocumentParams,
            ),
        )

        if isinstance(params, DidOpenTextDocumentParams):
            method = features.TEXT_DOCUMENT_DID_OPEN
        elif isinstance(params, DidSaveTextDocumentParams):
            method = features.TEXT_DOCUMENT_DID_SAVE
        else:
            method = features.TEXT_DOCUMENT_DID_CHANGE

        self.assertFalse(
            self.client_diagnostics, "Client shoult not have diagnostics by now"
        )

        _logger.info("Patching %s with %s", "getMessagesByPath", list(expected_diags))
        with patch.object(
            self.server.checker, "getMessagesByPath", return_value=list(expected_diags),
        ):
            hdl_checker.utils.ENABLE_DEBOUNCE = False
            try:
                self.client.lsp.send_request(method, params).result(LSP_REQUEST_TIMEOUT)
            finally:
                hdl_checker.utils.ENABLE_DEBOUNCE = True

            self.assertTrue(
                self.client_diagnostics, "Expected client to have diagnostics"
            )
            diags: List[CheckerDiagnostic] = []
            while self.client_diagnostics:
                diag = self.client_diagnostics.pop()
                diags += list(toCheckerDiagnostic(diag[0], diag[1]))

            _logger.info("Expected: %d => %s", len(expected_diags), expected_diags)
            _logger.info("Got:      %d => %s", len(diags), diags)
            self.assertFalse(set(expected_diags) - set(diags))

    def _runDidOpenCheck(self, source: Optional[Path]):
        self.checkLintFileOnMethod(
            DidOpenTextDocumentParams(
                TextDocumentItem(
                    uris.from_fs_path(source), language_id="vhdl", version=0, text="",
                )
            ),
            [
                CheckerDiagnostic(
                    text="testing clk en gen",
                    filename=source,
                    line_number=0,
                    column_number=0,
                ),
            ],
        )

    def _runDidSaveCheck(self, source: Optional[Path]):
        self.checkLintFileOnMethod(
            DidSaveTextDocumentParams(
                text_document=TextDocumentIdentifier(uris.from_fs_path(source)),
                text="Hello",
            ),
            [
                CheckerDiagnostic(
                    text="testing clk en gen",
                    filename=source,
                    line_number=0,
                    column_number=0,
                ),
            ],
        )

    def _runDidChangeCheck(self, source: Optional[Path]):
        self.checkLintFileOnMethod(
            DidChangeTextDocumentParams(
                VersionedTextDocumentIdentifier(uris.from_fs_path(source), version=1,),
                [
                    TextDocumentContentChangeEvent(
                        range=Range(Position(0, 0), Position(1, 1))
                    ),
                ],
            ),
            [
                CheckerDiagnostic(
                    text="post change diag",
                    filename=source,
                    line_number=1,
                    column_number=2,
                ),
            ],
        )

    def test_LintFileOnOpen(self):  # pylint: disable=inconsistent-return-statements
        if self.__class__ is _LspHelper:
            return unittest2.skip("Won't run this on %s" % self.__class__)
        _logger.info("#" * 100)
        self._runDidOpenCheck(p.join(TEST_PROJECT, "another_library", "foo.vhd"))

    def test_LintFileWhenSaving(self):  # pylint: disable=inconsistent-return-statements
        if self.__class__ is _LspHelper:
            return unittest2.skip("Won't run this on %s" % self.__class__)
        _logger.info("#" * 100)
        self._runDidSaveCheck(
            p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")
        )

    def test_LintFileOnChange(self):  # pylint: disable=inconsistent-return-statements
        if self.__class__ is _LspHelper:
            return unittest2.skip("Won't run this on %s" % self.__class__)
        _logger.info("#" * 100)
        self._runDidOpenCheck(
            p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
        )
        self._runDidChangeCheck(
            p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
        )


class TestRootUriNoProjectFile(_LspHelper):
    def setUp(self):
        _logger.info("#" * 100)
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")

        self.patches = (
            patch.object(
                hdl_checker.config_generators.base_generator.BaseGenerator, "generate",
            ),
            patch("hdl_checker.core.json.dump", spec=json.dump),
        )

        for _patch in self.patches:
            _patch.start()

        self._createClientServerPair(
            InitializeParams(
                process_id=1234,
                capabilities=_CLIENT_CAPABILITIES,
                root_uri=uris.from_fs_path(TEST_PROJECT),
            )
        )

    def tearDown(self):
        _logger.info("#" * 100)
        _logger.info("Shutting down server")
        for _patch in self.patches:
            _patch.stop()
        super(TestRootUriNoProjectFile, self).tearDown()

    def test_SearchesForFilesOnInitialization(
        self,
    ):  # pylint: disable=no-self-use,invalid-name
        _logger.info("#" * 100)
        lsp.SimpleFinder.generate.assert_called_once()  # pylint: disable=no-member
        #  Will get called twice
        hdl_checker.core.json.dump.assert_called()  # pylint: disable=no-member


class TestOldStyleProjectFile(_LspHelper):
    def setUp(self):
        _logger.info("#" * 100)
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")

        self._createClientServerPair(
            InitializeParams(
                process_id=1235,
                capabilities=_CLIENT_CAPABILITIES,
                root_uri=uris.from_fs_path(TEST_PROJECT),
                initialization_options={"project_file": "vimhdl.prj"},
            ),
        )


class TestNonExistingProjectFile(_LspHelper):
    def setUp(self):
        _logger.info("#" * 100)
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")
        self.project_file = "__some_project_file.prj"
        self.assertFalse(p.exists(self.project_file))

        self._createClientServerPair(
            InitializeParams(
                process_id=1236,
                capabilities=_CLIENT_CAPABILITIES,
                root_uri=uris.from_fs_path(TEST_PROJECT),
                initialization_options={"project_file": self.project_file},
            ),
        )


class TestNoRootNoProjectFile(_LspHelper):
    def setUp(self):
        _logger.info("#" * 100)
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")
        self.project_file = "__some_project_file.prj"
        self.assertFalse(p.exists(self.project_file))

        self._createClientServerPair(
            InitializeParams(
                process_id=1236,
                capabilities=_CLIENT_CAPABILITIES,
                root_uri=None,
                initialization_options={"project_file": None},
            ),
        )


class TestNoRootWithProjectFile(_LspHelper):
    def setUp(self):
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")
        self.project_file = "__some_project_file.prj"
        self.assertFalse(p.exists(self.project_file))

        self._createClientServerPair(
            InitializeParams(
                process_id=1237,
                capabilities=_CLIENT_CAPABILITIES,
                root_uri=None,
                initialization_options={
                    "project_file": p.join(TEST_PROJECT, "vimhdl.prj")
                },
            ),
        )


class TestValidProject(_LspHelper):
    def setUp(self):
        _logger.info("#" * 100)
        setupTestSuport(TEST_TEMP_PATH)
        _logger.debug("Creating server")
        self.project_file = "__some_project_file.prj"
        self.assertFalse(p.exists(self.project_file))

        self._createClientServerPair(
            InitializeParams(
                process_id=1238,
                capabilities=_CLIENT_CAPABILITIES,
                root_uri=uris.from_fs_path(TEST_PROJECT),
                initialization_options={"project_file": "config.json"},
            ),
        )

    def runTestBuildSequenceTable(self, tablefmt):
        _logger.debug("############################################")
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

        try:
            got = self.server.getBuildSequenceForHover(clk_en_generator)
            self.assertEqual(got, "\n".join(expected))
        except:
            _logger.error(
                "Gotten\n\n%s\n\nExpected\n\n%s\n\n", got, "\n".join(expected)
            )
            raise

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_ReportBuildSequencePlain(self):
        _logger.info("#" * 100)
        self.runTestBuildSequenceTable(tablefmt="plain")

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )  # pylint: disable=invalid-name
    def test_ReportBuildSequenceFallback(self):
        _logger.info("#" * 100)
        with patch.object(self.server, "client_capabilities", None):
            self.runTestBuildSequenceTable(tablefmt="plain")

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )  # pylint: disable=invalid-name
    def test_ReportBuildSequenceMarkdown(self):
        _logger.info("#" * 100)
        with patch.object(
            self.server,
            "client_capabilities",
            ClientCapabilities(
                text_document=TextDocumentClientCapabilities(
                    synchronization=None,
                    completion=None,
                    hover=HoverAbstract(
                        dynamic_registration=False,
                        # This is what we really need
                        content_format=[MarkupKind.Markdown,],
                    ),
                    signature_help=None,
                    references=None,
                    document_highlight=None,
                    document_symbol=None,
                    formatting=None,
                    range_formatting=None,
                    on_type_formatting=None,
                    definition=None,
                    type_definition=None,
                    implementation=None,
                    code_action=None,
                    code_lens=None,
                    document_link=None,
                    color_provider=None,
                    rename=None,
                    publish_diagnostics=PublishDiagnosticsAbstract(
                        related_information=True
                    ),
                    folding_range=None,
                )
            ),
        ):
            self.runTestBuildSequenceTable(tablefmt="github")

    @patch.object(
        hdl_checker.core.HdlCheckerCore,
        "resolveDependencyToPath",
        lambda self, _: None,
    )  # pylint: disable=invalid-name
    def test_DependencyInfoForPathNotFound(self):  # pylint: disable=invalid-name
        _logger.info("#" * 100)
        path = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))
        dependency = RequiredDesignUnit(
            name=Identifier("clock_divider"),
            library=Identifier("basic_library"),
            owner=path,
            locations=(),
        )
        self.assertEqual(
            self.server.getDependencyInfoForHover(dependency),
            "Couldn't find a source defining 'basic_library.clock_divider'",
        )

    @patch.object(
        hdl_checker.core.HdlCheckerCore,
        "resolveDependencyToPath",
        lambda self, _: (Path("some_path"), Identifier("some_library")),
    )
    def test_ReportDependencyInfo(self):
        _logger.info("#" * 100)
        path = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))
        dependency = RequiredDesignUnit(
            name=Identifier("clock_divider"),
            library=Identifier("basic_library"),
            owner=path,
            locations=(),
        )
        self.assertEqual(
            self.server.getDependencyInfoForHover(dependency),
            'Path "some_path", library "some_library"',
        )

    def test_ReportDesignUnitAccordingToPosition(  # pylint: disable=invalid-name
        self,
    ) -> None:
        _logger.info("#" * 100)
        unit_a = VhdlDesignUnit(
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            type_=DesignUnitType.entity,
            name="unit_a",
            locations=(Location(line=1, column=2), Location(line=3, column=4)),
        )

        unit_b = VerilogDesignUnit(
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            type_=DesignUnitType.package,
            name="unit_b",
            locations=(Location(line=5, column=6), Location(line=7, column=8)),
        )

        dep_a = RequiredDesignUnit(
            name=Identifier("dep_a"),
            library=Identifier("lib_a"),
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            locations=(Location(line=9, column=10), Location(line=11, column=12)),
        )

        dep_b = RequiredDesignUnit(
            name=Identifier("dep_a"),
            library=Identifier("lib_a"),
            owner=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
            locations=(Location(line=13, column=14), Location(line=15, column=16)),
        )

        def getDesignUnitsByPath(self, path):  # pylint: disable=unused-argument
            if path != Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")):
                self.fail("Expected foo.vhd but got %s" % path)
            return {unit_a, unit_b}

        def getDependenciesByPath(self, path):  # pylint: disable=unused-argument
            if path != Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")):
                self.fail("Expected foo.vhd but got %s" % path)
            return {dep_a, dep_b}

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
        self.assertIsNone(self.server.getElementAtPosition(path, Position(0, 0)))

        # Check design units are found, ensure boundaries match
        self.assertIsNone(self.server.getElementAtPosition(path, Position(1, 1)))
        self.assertIs(self.server.getElementAtPosition(path, Position(1, 2)), unit_a)
        self.assertIs(self.server.getElementAtPosition(path, Position(1, 7)), unit_a)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(1, 8)))

        self.assertIsNone(self.server.getElementAtPosition(path, Position(3, 3)))
        self.assertIs(self.server.getElementAtPosition(path, Position(3, 4)), unit_a)
        self.assertIs(self.server.getElementAtPosition(path, Position(3, 9)), unit_a)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(3, 10)))

        self.assertIsNone(self.server.getElementAtPosition(path, Position(5, 5)))
        self.assertIs(self.server.getElementAtPosition(path, Position(5, 6)), unit_b)
        self.assertIs(self.server.getElementAtPosition(path, Position(5, 11)), unit_b)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(5, 12)))

        self.assertIsNone(self.server.getElementAtPosition(path, Position(7, 7)))
        self.assertIs(self.server.getElementAtPosition(path, Position(7, 8)), unit_b)
        self.assertIs(self.server.getElementAtPosition(path, Position(7, 13)), unit_b)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(7, 14)))

        # Now check dependencies
        self.assertIsNone(self.server.getElementAtPosition(path, Position(9, 9)))
        self.assertIs(self.server.getElementAtPosition(path, Position(9, 10)), dep_a)
        self.assertIs(self.server.getElementAtPosition(path, Position(9, 20)), dep_a)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(9, 21)))

        self.assertIsNone(self.server.getElementAtPosition(path, Position(11, 11)))
        self.assertIs(self.server.getElementAtPosition(path, Position(11, 12)), dep_a)
        self.assertIs(self.server.getElementAtPosition(path, Position(11, 22)), dep_a)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(11, 23)))

        self.assertIsNone(self.server.getElementAtPosition(path, Position(13, 13)))
        self.assertIs(self.server.getElementAtPosition(path, Position(13, 14)), dep_b)
        self.assertIs(self.server.getElementAtPosition(path, Position(13, 24)), dep_b)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(13, 25)))

        self.assertIsNone(self.server.getElementAtPosition(path, Position(15, 15)))
        self.assertIs(self.server.getElementAtPosition(path, Position(15, 16)), dep_b)
        self.assertIs(self.server.getElementAtPosition(path, Position(15, 26)), dep_b)
        self.assertIsNone(self.server.getElementAtPosition(path, Position(15, 27)))

        for _patch in patches:
            _patch.stop()

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_HoverOnInvalidRange(self):
        _logger.info("#" * 100)
        self.assertIsNone(
            self.client.lsp.send_request(
                features.HOVER,
                HoverParams(
                    TextDocumentIdentifier(
                        uris.from_fs_path(
                            p.join(TEST_PROJECT, "another_library", "foo.vhd")
                        )
                    ),
                    Position(line=0, character=0),
                ),
            ).result(LSP_REQUEST_TIMEOUT)
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_HoverOnDesignUnit(self):
        _logger.info("#" * 100)
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

        self.assertEqual(
            self.client.lsp.send_request(
                features.HOVER,
                HoverParams(
                    TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                    Position(line=7, character=7),
                ),
            )
            .result(LSP_REQUEST_TIMEOUT)
            .contents,
            "\n".join(expected),
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_HoverOnDependency(self):
        _logger.info("#" * 100)
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
            .result(LSP_REQUEST_TIMEOUT)
            .contents,
            'Path "%s", library "basic_library"' % clock_divider,
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )  # pylint: disable=invalid-name
    def test_GetDefinitionMatchingDependency(self):
        _logger.info("#" * 100)
        source = p.join(TEST_PROJECT, "basic_library", "use_entity_a_and_b.vhd")
        target = p.join(TEST_PROJECT, "basic_library", "two_entities_one_file.vhd")

        definitions = {
            (
                x.uri,
                x.range.start.line,
                x.range.start.character,
                x.range.end.line,
                x.range.end.character,
            )
            for x in self.client.lsp.send_request(
                features.DEFINITION,
                TextDocumentPositionParams(
                    TextDocumentIdentifier(uris.from_fs_path(source)), Position(1, 9),
                ),
            ).result(LSP_REQUEST_TIMEOUT)
        }

        self.assertIn(
            (uris.from_fs_path(target), 1, 7, 1, 15), definitions,
        )

        self.assertIn(
            (uris.from_fs_path(target), 4, 7, 4, 15), definitions,
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )  # pylint: disable=invalid-name
    def test_GetDefinitionBuiltInLibrary(self) -> None:
        _logger.info("#" * 100)
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        self.assertFalse(
            self.server.definitions(
                TextDocumentPositionParams(
                    TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                    Position(3, 15),
                )
            )
        )

    @patch(
        "hdl_checker.builders.base_builder.BaseBuilder.builtin_libraries",
        (Identifier("ieee"),),
    )
    def test_GetDefinitionNotKnown(self) -> None:
        _logger.info("#" * 100)
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        self.assertFalse(
            self.server.definitions(
                TextDocumentPositionParams(
                    TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                    Position(0, 0),
                )
            )
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
    def test_ReferencesOfAValidElement(self, get_references) -> Any:
        _logger.info("#" * 100)
        # We'll pass the path to foo.vhd but we're patching the
        # getReferencesToDesignUnit to return "some_path"
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        # Make sure we picked up an existing element
        unit = self.server.getElementAtPosition(Path(path_to_foo), Position(7, 7))
        self.assertIsNotNone(unit)

        references = [
            (
                x.uri,
                x.range.start.line,
                x.range.start.character,
                x.range.end.line,
                x.range.end.character,
            )
            for x in self.client.lsp.send_request(
                features.REFERENCES,
                ReferenceParams(
                    TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                    Position(7, 7),
                    ReferenceContext(include_declaration=False),
                ),
            ).result(LSP_REQUEST_TIMEOUT)
        ]

        self.assertCountEqual(
            references,
            {
                (uris.from_fs_path("some_path"), 1, 2, 1, 2),
                (uris.from_fs_path("some_path"), 3, 4, 3, 4),
            },
        )

        get_references.assert_called_once()
        get_references.reset_mock()

        references = [
            (
                x.uri,
                x.range.start.line,
                x.range.start.character,
                x.range.end.line,
                x.range.end.character,
            )
            for x in self.client.lsp.send_request(
                features.REFERENCES,
                ReferenceParams(
                    TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                    Position(7, 7),
                    ReferenceContext(include_declaration=True),
                ),
            ).result(LSP_REQUEST_TIMEOUT)
        ]

        self.assertCountEqual(
            references,
            {
                (uris.from_fs_path(path_to_foo), 7, 7, 7, 7),
                (uris.from_fs_path("some_path"), 1, 2, 1, 2),
                (uris.from_fs_path("some_path"), 3, 4, 3, 4),
            },
        )

    def test_ReferencesOfAnInvalidElement(self):  # pylint: disable=invalid-name
        _logger.info("#" * 100)
        path_to_foo = p.join(TEST_PROJECT, "another_library", "foo.vhd")

        # Make sure there's no element at this location
        unit = self.server.getElementAtPosition(Path(path_to_foo), Position(0, 0))
        self.assertIsNone(unit)

        for include_declaration in (False, True):
            self.assertIsNone(
                self.server.references(
                    ReferenceParams(
                        TextDocumentIdentifier(uris.from_fs_path(path_to_foo)),
                        Position(0, 0),
                        ReferenceContext(include_declaration=include_declaration),
                    )
                )
            )

    def test_changeConfiguration(self):
        _logger.info("#" * 100)
        # pylint: disable=no-member
        with patch.object(self.server, "onConfigUpdate"):
            self.client.lsp.send_request(
                features.WORKSPACE_DID_CHANGE_CONFIGURATION, {"foo": "bar"}
            ).result(LSP_REQUEST_TIMEOUT)

            self.assertIn(
                "bar", {x[0].foo for x in self.server.onConfigUpdate.call_args if x},
            )
        # pylint: enable=no-member
