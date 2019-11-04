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

import six
from pyls import lsp as defines  # type: ignore
from pyls._utils import debounce  # type: ignore
from pyls.python_ls import PythonLanguageServer  # type: ignore
from pyls.uris import from_fs_path, to_fs_path  # type: ignore
from pyls.workspace import Workspace  # type: ignore
from tabulate import tabulate

from hdl_checker import DEFAULT_LIBRARY, DEFAULT_PROJECT_FILE
from hdl_checker.base_server import BaseServer
from hdl_checker.config_generators.simple_finder import SimpleFinder
from hdl_checker.diagnostics import CheckerDiagnostic, DiagType
from hdl_checker.exceptions import UnknownParameterError
from hdl_checker.parsers.elements.dependency_spec import DependencySpec
from hdl_checker.parsers.elements.design_unit import (
    VerilogDesignUnit,
    VhdlDesignUnit,
    tAnyDesignUnit,
)
from hdl_checker.path import Path, TemporaryPath
from hdl_checker.types import Location, MarkupKind
from hdl_checker.utils import getTemporaryFilename, logCalls, onNewReleaseFound

_logger = logging.getLogger(__name__)

AUTO_PROJECT_FILE_NAME = "project.json"
LINT_DEBOUNCE_S = 0.5  # 500 ms

URI = str

if six.PY2:
    FileNotFoundError = (  # pylint: disable=redefined-builtin,invalid-name
        IOError,
        OSError,
    )


def checkerDiagToLspDict(diag):
    # type: (...) -> Any
    """
    Converts a CheckerDiagnostic object into the dictionary with into the LSP
    expects
    """
    _logger.debug(diag)

    # Translate the error into LSP severity
    severity = diag.severity

    if severity in (
        DiagType.STYLE_WARNING,
        DiagType.STYLE_ERROR,
        DiagType.INFO,
        DiagType.STYLE_INFO,
    ):
        severity = defines.DiagnosticSeverity.Information
    elif severity in (DiagType.WARNING,):
        severity = defines.DiagnosticSeverity.Warning
    elif severity in (DiagType.ERROR,):
        severity = defines.DiagnosticSeverity.Error
    else:
        severity = defines.DiagnosticSeverity.Error

    result = {
        "source": diag.checker,
        "range": {
            "start": {
                "line": (diag.line_number or 0),
                "character": (diag.column_number or 0),
            },
            "end": {
                "line": (diag.line_number or 0),
                "character": (diag.column_number or 0),
            },
        },
        "message": diag.text,
        "severity": severity,
    }

    if diag.error_code:
        result["code"] = diag.error_code

    return result


class Server(BaseServer):
    """
    HDL Checker project builder class
    """

    def __init__(self, workspace, root_dir):
        # type: (Workspace, Path) -> None
        self._workspace = workspace
        super(Server, self).__init__(root_dir)

    def _handleUiInfo(self, message):
        # type: (...) -> Any
        _logger.debug("UI info: %s (workspace=%s)", message, self._workspace)
        if self._workspace:  # pragma: no cover
            self._workspace.show_message(message, defines.MessageType.Info)

    def _handleUiWarning(self, message):
        # type: (...) -> Any
        _logger.debug("UI warning: %s (workspace=%s)", message, self._workspace)
        if self._workspace:  # pragma: no cover
            self._workspace.show_message(message, defines.MessageType.Warning)

    def _handleUiError(self, message):
        # type: (...) -> Any
        _logger.debug("UI error: %s (workspace=%s)", message, self._workspace)
        if self._workspace:  # pragma: no cover
            self._workspace.show_message(message, defines.MessageType.Error)


class HdlCheckerLanguageServer(PythonLanguageServer):
    """ Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    # pylint: disable=too-many-public-methods,redefined-builtin

    def __init__(self, *args, **kwargs):
        # type: (...) -> None
        self._checker = None  # type: Optional[Server]
        super(HdlCheckerLanguageServer, self).__init__(*args, **kwargs)
        # Default checker
        self._onConfigUpdate({"project_file": None})
        self._global_diags = set()  # type: Set[CheckerDiagnostic]
        self._initialization_options = {}  # type: Dict[str, Any]

    @property
    def checker(self):
        # type: () -> Server
        """
        Returns a valid checker, either the one configured during
        HdlCheckerLanguageServer._onConfigUpdate or a new one using a temporary
        directory.
        """
        if self._checker is None:
            _logger.info("Server was not initialized, using a temporary one")
            root_dir = mkdtemp(prefix="temp_hdl_checker_pid{}_".format(getpid()))
            self._checker = Server(self.workspace, root_dir=TemporaryPath(root_dir))
        return self._checker

    def showInfo(self, msg):
        # type: (str) -> None
        """
        Shorthand for self.workspace.show_message(msg, defines.MessageType.Info)
        """
        _logger.info("[INFO] %s", msg)
        self.workspace.show_message(msg, defines.MessageType.Info)

    def showWarning(self, msg):
        # type: (str) -> None
        """
        Shorthand for self.workspace.show_message(msg, defines.MessageType.Warning)
        """
        _logger.info("[WARNING] %s", msg)
        self.workspace.show_message(msg, defines.MessageType.Warning)

    def capabilities(self):
        # type: (...) -> Any
        "Returns language server capabilities"
        return {
            "definitionProvider": True,
            "hoverProvider": True,
            "textDocumentSync": defines.TextDocumentSyncKind.FULL,
        }

    @logCalls
    def m_initialized(self, **_kwargs):
        """
        Enables processing of actions that were generated upon m_initialize and
        were delayed because the client might need further info (for example to
        handle window/showMessage requests)
        """
        self._onConfigUpdate(self._initialization_options)
        onNewReleaseFound(self.showInfo)
        return super(HdlCheckerLanguageServer, self).m_initialized(**_kwargs)

    @logCalls
    def m_initialize(
        self,
        processId=None,
        rootUri=None,
        rootPath=None,
        initializationOptions=None,
        **_kwargs
    ):
        # type: (...) -> Any
        """
        Initializes the language server
        """
        result = super(HdlCheckerLanguageServer, self).m_initialize(
            processId=processId,
            rootUri=rootUri,
            rootPath=rootPath,
            initializationOptions={},
            **_kwargs
        )
        self._initialization_options = initializationOptions
        return result

    def _onConfigUpdate(self, options):
        # type: (...) -> Any
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
        self._checker = Server(self.workspace, root_dir=Path(root_dir))

        _logger.debug("Updating from %s", options)

        # Clear previous diagnostics
        self._global_diags = set()

        path = self._getProjectFilePath(options)

        try:
            self.checker.setConfig(path)
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
        self.checker.setConfig(auto_project_file)

    def _getProjectFilePath(self, options=None):
        # type: (...) -> str
        """
        Tries to get 'project_file' from the options dict and combine it with
        the root URI as provided by the workspace
        """
        path = (options or {}).get("project_file", DEFAULT_PROJECT_FILE)

        # Project file will be related to the root path
        if self.workspace:
            path = p.join(self.workspace.root_path, path)

        return path

    @debounce(LINT_DEBOUNCE_S, keyed_by="doc_uri")
    def lint(self, doc_uri, is_saved):
        # type: (URI, bool) -> Any
        _logger.info("linting: %s", doc_uri)
        diags = set(self._getDiags(doc_uri, is_saved))

        # Separate the diagnostics in filename groups to publish diagnostics
        # referring to all paths
        paths = {diag.filename for diag in diags}
        # Add doc_uri to the set to trigger clearing diagnostics when it's not
        # present
        paths.add(Path(to_fs_path(doc_uri)))

        for path in paths:
            self.workspace.publish_diagnostics(
                from_fs_path(str(path)),
                list(
                    checkerDiagToLspDict(diag)
                    for diag in diags
                    if diag.filename == path
                ),
            )

    def _getDiags(self, doc_uri, is_saved):
        # type: (URI, bool) -> Iterable[CheckerDiagnostic]
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

        _logger.info("Linting %s (saved=%s)", repr(path), is_saved)

        if is_saved:
            return self.checker.getMessagesByPath(path)

        text = self.workspace.get_document(doc_uri).source
        return self.checker.getMessagesWithText(path, text)

    def m_workspace__did_change_configuration(self, settings=None):
        # type: (...) -> Any
        self._onConfigUpdate(settings or {})

    @property
    def _use_markdown_for_hover(self):
        """
        Returns True if the client has reported 'markdown' as one of the
        supported formats, i.e., 'markdown' is present inside
        TextDocumentClientCapabilities.hover.contentFormat
        """
        return MarkupKind.Markdown.value in (
            self.config.capabilities.get("textDocument", {})
            .get("hover", {})
            .get("contentFormat", [])
        )

    def _format(self, text):
        """
        Double line breaks if workspace supports markdown
        """
        if self._use_markdown_for_hover:
            return text.replace("\n", "\n\n")

        return text

    def _getBuildSequenceForHover(self, path):
        # type: (Path) -> str
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
        # type: (DependencySpec) -> Optional[str]
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

    def _getElementAtPosition(self, path, position):
        # type: (Path, Location) -> Union[DependencySpec, tAnyDesignUnit, None]
        """
        Gets design units and dependencies (in this order) of path and checks
        if their definitions include position
        """
        for meth in (
            self.checker.database.getDesignUnitsByPath,
            self.checker.database.getDependenciesByPath,
        ):  # type: Callable
            for element in meth(path):
                if element.includes(position):
                    return element

        return None

    def hover(self, doc_uri, position):
        # type: (URI, Dict[str, int]) -> Any
        path = Path(to_fs_path(doc_uri))
        # Check if the element under the cursor matches something we know
        element = self._getElementAtPosition(
            path, Location(line=position["line"], column=position["character"])
        )

        _logger.debug("Getting info from %s", element)

        if isinstance(element, (VerilogDesignUnit, VhdlDesignUnit)):
            return {"contents": self._getBuildSequenceForHover(path)}

        if isinstance(element, DependencySpec):
            return {"contents": self._getDependencyInfoForHover(element)}

        return None

    @logCalls
    def definitions(self, doc_uri, position):
        # type: (...) -> Any
        doc_path = Path(to_fs_path(doc_uri))
        dependency = self._getElementAtPosition(
            doc_path, Location(line=position["line"], column=position["character"])
        )

        if not isinstance(dependency, DependencySpec):
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

        locations = []  # type: List[Dict[str, Any]]

        # Get the design unit that has matched the dependency to extract the
        # location where it's defined
        for unit in self.checker.database.getDesignUnitsByPath(target_path):
            if unit.name == dependency.name and unit.locations:
                for line, column in unit.locations:
                    locations += [
                        {
                            "uri": target_uri,
                            "range": {
                                "start": {"line": line, "character": column},
                                "end": {"line": line, "character": column + len(unit)},
                            },
                        }
                    ]

        return locations
