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
"Language server protocol implementation"

import logging
import os.path as p
import tempfile
from typing import Any, Dict, Iterable, Optional, Set

import six
from pyls import lsp as defines  # type: ignore
from pyls._utils import debounce  # type: ignore
from pyls.python_ls import PythonLanguageServer  # type: ignore
from pyls.uris import to_fs_path  # type: ignore
from pyls.workspace import Workspace  # type: ignore

from hdlcc import DEFAULT_PROJECT_FILE
from hdlcc.config_generators.simple_finder import SimpleFinder
from hdlcc.diagnostics import CheckerDiagnostic, DiagType
from hdlcc.exceptions import UnknownParameterError
from hdlcc.hdlcc_base import HdlCodeCheckerBase
from hdlcc.path import Path
from hdlcc.utils import logCalls

_logger = logging.getLogger(__name__)

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

    if severity in (DiagType.INFO, DiagType.STYLE_INFO):
        severity = defines.DiagnosticSeverity.Hint
    elif severity in (DiagType.STYLE_WARNING, DiagType.STYLE_ERROR):
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
                "line": (diag.line_number or 1) - 1,
                "character": (diag.column_number or 1) - 1,
            },
            "end": {
                "line": (diag.line_number or 1) - 1,
                "character": (diag.column_number or 1) - 1,
            },
        },
        "message": diag.text,
        "severity": severity,
    }

    if diag.error_code:
        result["code"] = diag.error_code

    return result


class HdlCodeCheckerServer(HdlCodeCheckerBase):
    """
    HDL Code Checker project builder class
    """

    def __init__(self, workspace, root_path):
        # type: (Workspace, Optional[str]) -> None
        self._workspace = workspace
        if root_path is None:
            root_path = tempfile.mkdtemp(prefix="hdlcc_")

        super(HdlCodeCheckerServer, self).__init__(Path(root_path))

    def _handleUiInfo(self, message):
        # type: (...) -> Any
        _logger.debug("UI info: %s (workspace=%s)", message, self._workspace)
        if self._workspace: # pragma: no cover
            self._workspace.show_message(message, defines.MessageType.Info)

    def _handleUiWarning(self, message):
        # type: (...) -> Any
        _logger.debug("UI warning: %s (workspace=%s)", message, self._workspace)
        if self._workspace: # pragma: no cover
            self._workspace.show_message(message, defines.MessageType.Warning)

    def _handleUiError(self, message):
        # type: (...) -> Any
        _logger.debug("UI error: %s (workspace=%s)", message, self._workspace)
        if self._workspace: # pragma: no cover
            self._workspace.show_message(message, defines.MessageType.Error)


class HdlccLanguageServer(PythonLanguageServer):
    """ Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    # pylint: disable=too-many-public-methods,redefined-builtin

    def __init__(self, *args, **kwargs):
        # type: (...) -> None
        self._checker = None  # type: Optional[HdlCodeCheckerServer]
        super(HdlccLanguageServer, self).__init__(*args, **kwargs)
        # Default checker
        self._onConfigUpdate({"project_file": None})
        self._global_diags = set()  # type: Set[CheckerDiagnostic]
        self._initialization_options = {}  # type: Dict[str, Any]

    @logCalls
    def capabilities(self):
        # type: (...) -> Any
        "Returns language server capabilities"
        return {"textDocumentSync": defines.TextDocumentSyncKind.FULL}

    @logCalls
    def m_initialized(self, **_kwargs):
        """
        Enables processing of actions that were generated upon m_initialize and
        were delayed because the client might need further info (for example to
        handle window/showMessage requests)
        """
        self._onConfigUpdate(self._initialization_options)
        return super(HdlccLanguageServer, self).m_initialized(**_kwargs)

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
        result = super(HdlccLanguageServer, self).m_initialize(
            processId=processId,
            rootUri=rootUri,
            rootPath=rootPath,
            initializationOptions={},
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
        root_path = None

        if self.workspace and self.workspace.root_uri is not None:
            root_path = to_fs_path(self.workspace.root_uri)

        self._checker = HdlCodeCheckerServer(self.workspace, root_path=root_path)

        _logger.debug("Updating from %s", options)

        # Clear previous diagnostics
        self._global_diags = set()

        path = self._getProjectFilePath(options)

        if path is not None:
            try:
                self._checker.setConfig(path)
                return
            except UnknownParameterError as exc:
                _logger.info("Failed to read config from %s: %s", path, exc)
                return
            except FileNotFoundError:
                # If the file couldn't be found, proceed to searching the root
                # URI (if it has been set)
                pass

        if not self.workspace or not self.workspace.root_path:
            _logger.debug("No workspace or root path not set, can't search files")
            return

        # Having no project file but with root URI triggers searching for
        # sources automatically
        config = SimpleFinder([self.workspace.root_path]).generate()
        self.workspace.show_message(
            "Added {} files from {}".format(
                len(config["sources"]), self.workspace.root_path
            ),
            defines.MessageType.Info,
        )
        self._checker.configure(config)

    def _getProjectFilePath(self, options=None):
        # type: (...) -> Optional[str]
        """
        Tries to get 'project_file' from the options dict and combine it with
        the root URI as provided by the workspace
        """
        path = (options or {}).get("project_file", DEFAULT_PROJECT_FILE)

        # Path has been explicitly set to none
        if path is None:
            return None

        # Project file will be related to the root path
        if self.workspace:
            path = p.join(self.workspace.root_path or "", path)

        return path

    @debounce(LINT_DEBOUNCE_S, keyed_by="doc_uri")
    def lint(self, doc_uri, is_saved):
        # type: (...) -> Any
        diagnostics = set(self._getDiags(doc_uri, is_saved)) | self._global_diags

        # Since we're debounced, the document may no longer be open
        if doc_uri in self.workspace.documents:
            # Both checker methods return generators, convert to a list before
            # returning
            self.workspace.publish_diagnostics(
                doc_uri, list([checkerDiagToLspDict(x) for x in diagnostics])
            )

    def _getDiags(self, doc_uri, is_saved):
        # type: (URI, bool) -> Iterable[CheckerDiagnostic]
        """
        Gets diags of the URI, wether from the saved file or from its
        contents
        """
        if self._checker is None: # pragma: no cover
            _logger.debug("No checker, won't try to get diagnostics")
            return ()

        # If the file has not been saved, use the appropriate method, which
        # will involve dumping the modified contents into a temporary file
        path = Path(to_fs_path(doc_uri))

        _logger.info("Linting %s (saved=%s)", repr(path), is_saved)

        if is_saved:
            diags = self._checker.getMessagesByPath(path)
        else:
            text = self.workspace.get_document(doc_uri).source
            diags = self._checker.getMessagesWithText(path, text)

        # LSP diagnostics are only valid for the scope of the resource and
        # hdlcc may return a tree of issues, so need to filter those out
        return (diag for diag in diags if diag.filename in (path, None))

    @logCalls
    def m_workspace__did_change_configuration(self, settings=None):
        # type: (...) -> Any
        self._onConfigUpdate(settings or {})
