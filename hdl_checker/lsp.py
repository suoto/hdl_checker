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
"Language server protocol implementation"

import json
import logging
from os import getpid
from os import path as p
from tempfile import mkdtemp
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from pygls.features import (
    DEFINITION,
    HOVER,
    INITIALIZE,
    INITIALIZED,
    REFERENCES,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    WORKSPACE_DID_CHANGE_CONFIGURATION,
)
from pygls.server import LanguageServer
from pygls.types import (
    ClientCapabilities,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeConfigurationParams,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    Location,
    MarkupKind,
    MessageType,
    Position,
    Range,
    ReferenceParams,
    TextDocumentPositionParams,
)
from pygls.uris import from_fs_path, to_fs_path
from tabulate import tabulate

from hdl_checker import DEFAULT_LIBRARY, DEFAULT_PROJECT_FILE
from hdl_checker.base_server import BaseServer
from hdl_checker.config_generators.simple_finder import SimpleFinder
from hdl_checker.diagnostics import CheckerDiagnostic, DiagType
from hdl_checker.exceptions import UnknownParameterError
from hdl_checker.parsers.elements.dependency_spec import BaseDependencySpec
from hdl_checker.parsers.elements.design_unit import (
    VerilogDesignUnit,
    VhdlDesignUnit,
    tAnyDesignUnit,
)
from hdl_checker.path import Path, TemporaryPath
from hdl_checker.types import ConfigFileOrigin  # , Location
from hdl_checker.utils import getTemporaryFilename, logCalls, onNewReleaseFound

_logger = logging.getLogger(__name__)

AUTO_PROJECT_FILE_NAME = "project.json"
LINT_DEBOUNCE_S = 0.5  # 500 ms

URI = str


def _translateSeverity(severity: DiagType) -> DiagnosticSeverity:
    """
    Translate hdl_checker's DiagType into pygls's DiagnosticSeverity into LSP
    severity
    """
    if severity in (
        DiagType.STYLE_WARNING,
        DiagType.STYLE_ERROR,
        DiagType.INFO,
        DiagType.STYLE_INFO,
    ):
        return DiagnosticSeverity.Information
    if severity in (DiagType.WARNING,):
        return DiagnosticSeverity.Warning
    if severity in (DiagType.ERROR,):
        return DiagnosticSeverity.Error
    return DiagnosticSeverity.Error


def checkerDiagToLspDict(diag: CheckerDiagnostic) -> Diagnostic:
    """
    Converts a CheckerDiagnostic object into pygls.Diagnostic type expected by
    the publish_diagnostics LSP method
    """
    _logger.debug(diag)
    return Diagnostic(
        range=Range(
            start=Position(
                line=diag.line_number or 0, character=diag.column_number or 0
            ),
            end=Position(line=diag.line_number or 0, character=diag.column_number or 0),
        ),
        message=diag.text,
        severity=_translateSeverity(diag.severity),
        code=diag.error_code if diag.error_code else None,
        source=diag.checker,
    )


class Server(BaseServer):
    """
    HDL Checker project builder class
    """

    def __init__(self, lsp, root_dir):
        # type: (LanguageServer, Path) -> None
        self._lsp = lsp
        super(Server, self).__init__(root_dir)

    def _handleUiInfo(self, message):
        # type: (...) -> Any
        _logger.debug("UI info: %s (lsp=%s)", message, self._lsp)
        if self._lsp:  # pragma: no cover
            self._lsp.show_message(message, MessageType.Info)

    def _handleUiWarning(self, message):
        # type: (...) -> Any
        _logger.debug("UI warning: %s (lsp=%s)", message, self._lsp)
        if self._lsp:  # pragma: no cover
            self._lsp.show_message(message, MessageType.Warning)

    def _handleUiError(self, message):
        # type: (...) -> Any
        _logger.debug("UI error: %s (lsp=%s)", message, self._lsp)
        if self._lsp:  # pragma: no cover
            self._lsp.show_message(message, MessageType.Error)


class HdlCheckerLanguageServer(LanguageServer):
    """
    Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    def __init__(self, *args, **kwargs) -> None:
        self._checker: Optional[Server] = None
        super(HdlCheckerLanguageServer, self).__init__(*args, **kwargs)
        # Default checker
        self.onConfigUpdate(None)
        self._global_diags: Set[CheckerDiagnostic] = set()
        self.initialization_options: Optional[Any] = None
        self.client_capabilities: Optional[ClientCapabilities] = None

    @property
    def checker(self) -> Server:
        """
        Returns a valid checker, either the one configured during
        HdlCheckerLanguageServer.onConfigUpdate or a new one using a temporary
        directory.
        """
        if self._checker is None:
            _logger.debug("Server was not initialized, using a temporary one")
            root_dir = mkdtemp(prefix="temp_hdl_checker_pid{}_".format(getpid()))
            self._checker = Server(self, root_dir=TemporaryPath(root_dir))
        return self._checker

    def showInfo(self, msg: str) -> None:
        """
        Shorthand for self.show_message(msg, MessageType.Info)
        """
        _logger.info("[INFO] %s", msg)
        self.show_message(msg, MessageType.Info)

    def showWarning(self, msg: str) -> None:
        """
        Shorthand for self.show_message(msg, MessageType.Warning)
        """
        _logger.info("[WARNING] %s", msg)
        self.show_message(msg, MessageType.Warning)

    def onConfigUpdate(self, options: Optional[Any]) -> None:
        """
        Updates the checker server from options if the 'project_file' key is
        present. Please not that this is run from both initialize and
        workspace/did_change_configuration and when ran initialize the LSP
        client might not ready to take messages. To circumvent this, make sure
        m_initialize returns before calling this to actually configure the
        server.
        """
        if not self.workspace or not self.workspace.root_uri:
            return

        root_dir = to_fs_path(self.workspace.root_uri)
        self._checker = Server(self, root_dir=Path(root_dir))

        _logger.debug("Updating from %s, workspace=%s", options, self.workspace)

        # Clear previus diagnostics
        self._global_diags = set()

        path = self._getProjectFilePath(options)

        try:
            self.checker.setConfig(path, origin=ConfigFileOrigin.user)
            return
        except UnknownParameterError as exc:
            _logger.info("Failed to read config from %s: %s", path, exc)
            return
        except FileNotFoundError:
            # If the file couldn't be found, proceed to searching the root
            # URI (if it has been set)
            pass

        if not self.workspace or not self.workspace.root_path:
            _logger.debug("No workspace and/or root path not set, can't search files")
            return

        self.showInfo("Searching {} for HDL files...".format(self.workspace.root_path))

        # Having no project file but with root URI triggers searching for
        # sources automatically
        config = SimpleFinder([self.workspace.root_path]).generate()

        # Write this to a file and tell the server to use it
        auto_project_file = getTemporaryFilename(AUTO_PROJECT_FILE_NAME)
        json.dump(config, open(auto_project_file, "w"))
        self.checker.setConfig(auto_project_file, origin=ConfigFileOrigin.generated)

    def _getProjectFilePath(self, options: Optional[Any] = None) -> str:
        """
        Tries to get 'project_file' from the options dict and combine it with
        the root URI as provided by the workspace
        """
        path = DEFAULT_PROJECT_FILE
        if options and options.project_file is not None:
            path = options.project_file

        # Project file will be related to the root path
        if self.workspace:
            path = p.join(self.workspace.root_path, path)

        return path

    def lint(self, uri: URI, is_saved: bool) -> None:
        """
        Check a file for lint errors
        """
        _logger.debug("Linting %s (file was %s saved)", uri, "" if is_saved else "not")
        diags = set(self._getDiags(uri, is_saved))

        # Separate the diagnostics in filename groups to publish diagnostics
        # referring to all paths
        paths = {diag.filename for diag in diags}
        # Add text_doc.uri to the set to trigger clearing diagnostics when it's not
        # present
        paths.add(Path(to_fs_path(uri)))

        for path in paths:
            diags_to_publish = {
                checkerDiagToLspDict(diag) for diag in diags if diag.filename == path
            }
            if diags_to_publish:
                self.lsp.publish_diagnostics(
                    from_fs_path(str(path)), tuple(diags_to_publish)
                )
            else:
                _logger.debug("No diagnostics for %s", path)

    def _getDiags(self, doc_uri: URI, is_saved: bool) -> Iterable[CheckerDiagnostic]:
        """
        Gets diags of the URI, wether from the saved file or from its contents;
        returns an iterable containing the diagnostics of the doc_uri and other
        URIs that were compiled as dependencies and generated diagnostics with
        severity higher than error
        """
        if self.checker is None:  # pragma: no cover
            _logger.debug("No checker, won't try to get diagnostics")
            return ()

        # If the file has not been saved, use the appropriate method, which
        # will involve dumping the modified contents into a temporary file
        path = Path(to_fs_path(doc_uri))

        if is_saved:
            return self.checker.getMessagesByPath(path)
        text = self.workspace.get_document(doc_uri).source
        return self.checker.getMessagesWithText(path, text)

    def references(self, params: ReferenceParams) -> Optional[List[Location]]:
        "Tries to find references for the selected element"

        element = self._getElementAtPosition(
            Path(to_fs_path(params.textDocument.uri)), params.position
        )

        # Element not identified
        if element is None:
            return None

        references: List[Location] = []

        if params.context.includeDeclaration:
            for line, column in element.locations:
                references += [
                    Location(
                        uri=from_fs_path(str(element.owner)),
                        range=Range(
                            start=Position(line, column), end=Position(line, column)
                        ),
                    )
                ]

        for reference in self.checker.database.getReferencesToDesignUnit(element):
            for line, column in reference.locations:
                references += [
                    Location(
                        uri=from_fs_path(str(reference.owner)),
                        range=Range(
                            start=Position(line, column), end=Position(line, column)
                        ),
                    )
                ]

        return references

    @property
    def _use_markdown_for_hover(self):
        """
        Returns True if the client has reported 'markdown' as one of the
        supported formats, i.e., 'markdown' is present inside
        TextDocumentClientCapabilities.hover.contentFormat
        """
        try:
            return (
                MarkupKind.Markdown.value
                in self.client_capabilities.textDocument.hover.contentFormat
            )
        except AttributeError:
            return False

    def _format(self, text):
        """
        Double line breaks if workspace supports markdown
        """
        if self._use_markdown_for_hover:
            return text.replace("\n", "\n\n")

        return text

    def _getBuildSequenceForHover(self, path: Path) -> str:
        """
        Return a formatted text with the build sequence for the given path
        """
        sequence = []  # type: List[Tuple[int, str, str]]

        # Adds the sequence of dependencies' paths
        for i, (seq_library, seq_path) in enumerate(
            self.checker.database.getBuildSequence(
                path, self.checker.builder.builtin_libraries
            ),
            1,
        ):
            sequence += [(i, str(seq_library), str(seq_path))]

        # Adds the original path
        sequence += [
            (
                len(sequence) + 1,
                str(self.checker.database.getLibrary(path) or DEFAULT_LIBRARY),
                str(path),
            )
        ]

        return "Build sequence for {} is\n\n{}".format(
            path,
            tabulate(
                sequence,
                tablefmt="github" if self._use_markdown_for_hover else "plain",
                headers=("#", "Library", "Path"),
            ),
        )

    def _getDependencyInfoForHover(self, dependency):
        # type: (BaseDependencySpec) -> str
        """
        Report which source defines a given dependency when the user hovers
        over its name
        """
        # If that doesn't match, check for dependencies
        info = self.checker.resolveDependencyToPath(dependency)
        if info is not None:
            return self._format('Path "{}", library "{}"'.format(info[0], info[1]))

        return "Couldn't find a source defining '{}.{}'".format(
            dependency.library, dependency.name
        )

    def _getElementAtPosition(
        self, path: Path, position: Position
    ) -> Union[BaseDependencySpec, tAnyDesignUnit, None]:
        """
        Gets design units and dependencies (in this order) of path and checks
        if their definitions include position. Not every element is identified,
        only those pertinent to the core functionality, e.g. design units and
        dependencies.
        """
        for meth in (
            self.checker.database.getDesignUnitsByPath,
            self.checker.database.getDependenciesByPath,
        ):  # type: Callable
            for element in meth(path):
                if element.includes(position.line, position.character):
                    return element

        return None

    def hover(self, params: HoverParams) -> Optional[Hover]:
        path = Path(to_fs_path(params.textDocument.uri))
        # Check if the element under the cursor matches something we know
        element = self._getElementAtPosition(path, params.position)

        _logger.debug("Getting info from %s", element)

        if not isinstance(
            element, (VerilogDesignUnit, VhdlDesignUnit, BaseDependencySpec)
        ):
            return None

        if isinstance(element, (VerilogDesignUnit, VhdlDesignUnit)):
            contents = self._getBuildSequenceForHover(path)
        else:
            contents = self._getDependencyInfoForHover(element)

        return Hover(
            contents=contents,
            range=Range(
                start=Position(
                    line=params.position.line, character=params.position.character
                ),
                end=Position(
                    line=params.position.line, character=params.position.character
                ),
            ),
        )

    @logCalls
    def definitions(
        self, params: TextDocumentPositionParams
    ) -> Optional[List[Location]]:
        dependency = self._getElementAtPosition(
            Path(to_fs_path(params.textDocument.uri)), params.position
        )

        if not isinstance(dependency, BaseDependencySpec):
            _logger.debug("Go to definition not supported for item %s", dependency)
            return []

        # Work out where this dependency refers to
        info = self.checker.resolveDependencyToPath(dependency)

        if info is None:
            _logger.debug("Unable to resolve %s to a path", dependency)
            return []

        _logger.info("Dependency %s resolved to %s", dependency, info)

        # Make the response
        target_path, _ = info
        target_uri = from_fs_path(str(target_path))

        locations: List[Location] = []

        # Get the design unit that has matched the dependency to extract the
        # location where it's defined
        for unit in self.checker.database.getDesignUnitsByPath(target_path):
            if unit.name == dependency.name and unit.locations:
                for line, column in unit.locations:
                    locations += [
                        Location(
                            target_uri,
                            Range(
                                Position(line, column),
                                Position(line, column + len(unit)),
                            ),
                        )
                    ]

        return locations


def setupLanguageServerFeatures(server: HdlCheckerLanguageServer) -> None:
    """Adds pygls features to an instance of HdlCheckerLanguageServer"""

    # pylint: disable=unused-variable
    @server.feature(INITIALIZE)
    def initialize(self: HdlCheckerLanguageServer, params: InitializeParams) -> None:
        options = params.initializationOptions
        self.client_capabilities = params.capabilities
        self.initialization_options = options

    @server.feature(INITIALIZED)
    def initialized(self: HdlCheckerLanguageServer, *_):
        """
        Enables processing of actions that were generated upon m_initialize and
        were delayed because the client might need further info (for example to
        handle window/showMessage requests)
        """
        self.onConfigUpdate(self.initialization_options)
        onNewReleaseFound(self.showInfo)

    @server.feature(TEXT_DOCUMENT_DID_SAVE)
    def didSave(self: HdlCheckerLanguageServer, params: DidSaveTextDocumentParams):
        """Text document did change notification."""
        self.lint(params.textDocument.uri, True)

    @server.feature(TEXT_DOCUMENT_DID_CHANGE)
    def didChange(
        self: HdlCheckerLanguageServer, params: DidChangeTextDocumentParams,
    ):
        """Text document did change notification."""
        self.lint(params.textDocument.uri, False)

    @server.feature(TEXT_DOCUMENT_DID_OPEN)
    def didOpen(self: HdlCheckerLanguageServer, params: DidOpenTextDocumentParams):
        """Text document did change notification."""
        self.lint(params.textDocument.uri, True)

    @server.feature(WORKSPACE_DID_CHANGE_CONFIGURATION)
    def didChangeConfiguration(
        self: HdlCheckerLanguageServer, settings: DidChangeConfigurationParams = None,
    ) -> None:
        self.onConfigUpdate(settings)

    @server.feature(HOVER)
    def onHover(
        self: HdlCheckerLanguageServer, params: HoverParams,
    ) -> Optional[Hover]:
        return self.hover(params)

    @server.feature(REFERENCES)
    def onReferences(
        self: HdlCheckerLanguageServer, params: ReferenceParams,
    ) -> Optional[List[Location]]:
        return self.references(params)

    @server.feature(DEFINITION)
    def onDefinition(
        self: HdlCheckerLanguageServer, params: TextDocumentPositionParams,
    ) -> Optional[List[Location]]:
        return self.definitions(params)

    # pylint: enable=unused-variable
