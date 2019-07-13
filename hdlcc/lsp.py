# This file is part of HDL Code Checker.
#
# Copyright (c) 2015-2019 Andre Souto
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

# pylint: disable=useless-object-inheritance

import functools
import logging

import pyls.lsp as defines
import pyls.uris as uris
from pyls._utils import debounce
from pyls.python_ls import PythonLanguageServer

from hdlcc.diagnostics import DiagType, FailedToCreateProject
from hdlcc.hdlcc_base import HdlCodeCheckerBase

MONITORED_FILES = ('.vhd', '.vhdl', '.sv', '.svh', '.v', '.vh')
CONFIG_FILES = ()

_logger = logging.getLogger(__name__)

LINT_DEBOUNCE_S = 0.5  # 500 ms


def _logCalls(func):  # pragma: no cover
    "Decorator to Log calls to func"
    import pprint

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        _str = "%s(%s, %s)" % (func.__name__, args, pprint.pformat(kwargs))
        try:
            result = func(self, *args, **kwargs)
            _logger.info("%s => %s", _str, repr(result))
            return result
        except:
            _logger.exception("Failed to run %s", _str)
            raise

    return wrapper


def diagToLsp(diag):
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
    elif severity in (DiagType.WARNING, ):
        severity = defines.DiagnosticSeverity.Warning
    elif severity in (DiagType.ERROR, ):
        severity = defines.DiagnosticSeverity.Error
    else:
        severity = defines.DiagnosticSeverity.Error

    return {
        'source': diag.checker,
        'range': {
            'start': {'line': (diag.line_number or 0) - 1,
                      'character': -1, },
            'end': {'line': -1,
                    'character': -1, },
        },
        'message': diag.text,
        'severity': severity,
        'code':  diag.error_code or -1
    }


class HdlCodeCheckerServer(HdlCodeCheckerBase):
    """
    HDL Code Checker project builder class
    """
    _logger = logging.getLogger(__name__ + '.HdlCodeCheckerServer')

    def __init__(self, workspace, project_file=None):
        self._workspace = workspace
        super(HdlCodeCheckerServer, self).__init__(project_file=project_file)

    def _handleUiInfo(self, message):
        self._logger.info(message)
        self._workspace.show_message(message, defines.MessageType.Info)

    def _handleUiWarning(self, message):
        self._logger.warning(message)
        self._workspace.show_message(message, defines.MessageType.Warning)

    def _handleUiError(self, message):
        self._logger.error(message)
        self._workspace.show_message(message, defines.MessageType.Error)

class HdlccLanguageServer(PythonLanguageServer):
    """ Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    # pylint: disable=too-many-public-methods,redefined-builtin

    def __init__(self, *args, **kwargs):
        super(HdlccLanguageServer, self).__init__(*args, **kwargs)
        # Default checker
        self._checker = None
        self._global_diags = set()

    @_logCalls
    def capabilities(self):
        "Returns language server capabilities"
        return {
            'textDocumentSync': defines.TextDocumentSyncKind.FULL,
        }

    @_logCalls
    def m_initialize(self, processId=None, rootUri=None, # pylint: disable=invalid-name
                     rootPath=None, initializationOptions=None, **_kwargs):

        """
        Initializes the language server
        """
        super(HdlccLanguageServer, self).m_initialize(
            processId=processId, rootUri=rootUri, rootPath=rootPath,
            initializationOptions=initializationOptions, **_kwargs)

        project_file = (initializationOptions or {}).get('project_file', None)
        self._checker = HdlCodeCheckerServer(self.workspace, project_file)
        self._checker.clean()

        # Get our capabilities
        return {'capabilities': self.capabilities()}

    @debounce(LINT_DEBOUNCE_S, keyed_by='doc_uri')
    def lint(self, doc_uri, is_saved):
        if self._checker is None:
            return

        diagnostics = list(self._getDiags(doc_uri, is_saved))
        _logger.info("Diagnostics: %s", diagnostics)

        if self._global_diags:
            diagnostics += list(self._global_diags)

        # Since we're debounced, the document may no longer be open
        if doc_uri in self.workspace.documents:
            # Both checker methods return generators, convert to a list before
            # returning
            self.workspace.publish_diagnostics(
                doc_uri, list([diagToLsp(x) for x in diagnostics]))

    def _getDiags(self, doc_uri, is_saved):
        """
        Gets diags of the URI, wether from the saved file or from its
        contents
        """
        # If the file has not been saved, use the appropriate method, which
        # will involve dumping the modified contents into a temporary file
        path = uris.to_fs_path(doc_uri)

        # LSP diagnostics are only valid for the scope of the resource and
        # hdlcc may return a tree of issues, so need to filter those out
        filter_func = lambda diag: diag.filename in (None, path)

        _logger.info("Linting %s (saved=%s)", repr(path), is_saved)

        if is_saved:
            return filter(filter_func, self._checker.getMessagesByPath(path))

        text = self.workspace.get_document(doc_uri).source
        return filter(filter_func, self._checker.getMessagesWithText(path, text))

    @_logCalls
    def m_workspace__did_change_configuration(self, settings=None):
        project_file = (settings or {}).get('project_file', None)
        if project_file:
            # Clear previous global diags since we're changing projects
            self._global_diags = set()
            try:
                self._checker = HdlCodeCheckerServer(self.workspace, project_file)
                self._checker.clean()
            except Exception as exc:
                self._global_diags.add(FailedToCreateProject(project_file, exc))
                raise

    @_logCalls
    def m_workspace__did_change_watched_files(self, changes=None, **_kwargs):
        changed_monitored_files = set()
        config_changed = False
        for change in (changes or []):
            if change['uri'].endswith(MONITORED_FILES):
                changed_monitored_files.add(change['uri'])
            elif change['uri'].endswith(CONFIG_FILES):
                config_changed = True

        if config_changed:
            self.config.settings.cache_clear()
            self._checker.clean()
        elif not changed_monitored_files:
            # Only externally changed python files and lint configs may result
            # in changed diagnostics.
            return

        for doc_uri in self.workspace.documents:
            # Changes in doc_uri are already handled by m_text_document__did_save
            if doc_uri not in changed_monitored_files:
                self.lint(doc_uri, is_saved=False)
