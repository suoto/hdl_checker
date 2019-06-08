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

# This implementation is heavily based on
# https://github.com/palantir/python-language-server/

# pylint: disable=missing-docstring

import functools
import logging

import pyls.uris as uris
import pyls.lsp as defines
from pyls._utils import debounce
from pyls.python_ls import PythonLanguageServer

from hdlcc.diagnostics import DiagType
from hdlcc.hdlcc_base import HdlCodeCheckerBase

MONITORED_FILES = ('.vhd', '.vhdl', '.sv', '.svh', '.v', '.vh')
CONFIG_FILES = ()

_logger = logging.getLogger(__name__)

LINT_DEBOUNCE_S = 0.5  # 500 ms

# pylint: disable=useless-object-inheritance

def _logCalls(func):
    import pprint
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        _str = "%s(%s, %s)" % (func.__name__, args, pprint.pformat(kwargs))
        if getattr(func, '_lsp_unimplemented', False):
            _logger.warning(_str)
        else:
            _logger.debug(_str)
        return func(self, *args, **kwargs)

    return wrapper

def _markUnimplemented(func):
    """
    Mark a method as unimplmemented so any calls logged via _logCalls decorator
    will be warnings
    """
    func._lsp_unimplemented = True  # pylint: disable=protected-access
    return func

def diagToLsp(diag):
    """
    Converts a CheckerDiagnostic object into the dictionary with into the LSP
    expects
    """
    _logger.debug(diag)

    # Translate the error into LSP severity
    severity = diag.severity

    if severity in (DiagType.INFO, DiagType.STYLE_INFO):
        severity = defines.DiagnosticSeverity.Information
    elif severity in (DiagType.STYLE_WARNING, DiagType.STYLE_ERROR):
        severity = defines.DiagnosticSeverity.Hint
    elif severity in (DiagType.WARNING, DiagType.STYLE_WARNING):
        severity = defines.DiagnosticSeverity.Warning
    elif severity in (DiagType.ERROR, DiagType.STYLE_ERROR):
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
        'code':  diag.error_number or -1
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
        self._checker = HdlCodeCheckerServer(self.workspace, None)

    def capabilities(self):
        "Returns language server capabilities"
        server_capabilities = {
            'textDocumentSync': defines.TextDocumentSyncKind.NONE,
        }
        _logger.debug('Server capabilities: %s', server_capabilities)
        return server_capabilities

    @_logCalls
    def m_initialize(self, processId=None, rootUri=None, # pylint: disable=invalid-name
                     rootPath=None, initializationOptions=None, **_kwargs):

        """
        Initializes the language server
        """
        super(HdlccLanguageServer, self).m_initialize(
            processId=processId, rootUri=rootUri, rootPath=rootPath,
            initializationOptions=initializationOptions, **_kwargs)

        config_file = (initializationOptions or {}).get('config_file', None)
        if config_file:
            self._checker = HdlCodeCheckerServer(self.workspace, config_file)

        # Get our capabilities
        return {'capabilities': self.capabilities(), 'result': 'error'}

    @debounce(LINT_DEBOUNCE_S, keyed_by='doc_uri')
    def lint(self, doc_uri, is_saved):
        if self._checker is None:
            return

        path = uris.to_fs_path(doc_uri)
        _logger.info("Linting %s (saved=%s)", repr(path), is_saved)

        # If the file has not been saved, use the appropriate method, which
        # will involve dumping the modified contents into a temporary file
        if is_saved:
            diagnostics = self._checker.getMessagesByPath(path)
        else:
            text = self.workspace.get_document(doc_uri).source
            diagnostics = self._checker.getMessagesWithText(path, text)

        # Both checker methods return generators, convert to a list before
        # returning
        diagnostics = list([diagToLsp(x) for x in diagnostics])

        if diagnostics:
            _logger.debug("Diags:")
            for diag in diagnostics:
                _logger.debug(diag)

        # Since we're debounced, the document may no longer be open
        if doc_uri in self.workspace.documents:
            self.workspace.publish_diagnostics(doc_uri, list(diagnostics))

    @_logCalls
    def m_workspace__did_change_configuration(self, settings=None):
        config_file = (settings or {}).get('config_file', None)
        if config_file:
            self._checker = HdlCodeCheckerServer(self.workspace, config_file)

    @_logCalls
    def m_workspace__did_change_watched_files(self, changes=None, **_kwargs):
        changed_monitored_files = set()
        config_changed = False
        for d in (changes or []):
            if d['uri'].endswith(MONITORED_FILES):
                changed_monitored_files.add(d['uri'])
            elif d['uri'].endswith(CONFIG_FILES):
                config_changed = True

        if config_changed:
            self.config.settings.cache_clear()
        elif not changed_monitored_files:
            # Only externally changed python files and lint configs may result
            # in changed diagnostics.
            return

        for doc_uri in self.workspace.documents:
            # Changes in doc_uri are already handled by m_text_document__did_save
            if doc_uri not in changed_monitored_files:
                self.lint(doc_uri, is_saved=False)
