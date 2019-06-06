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

import pyls.python_ls as python_ls

import pyls.uris as uris
import pyls.lsp as defines
from pyls._utils import debounce
from pyls.python_ls import PythonLanguageServer

python_ls.PYTHON_FILE_EXTENSIONS = ('.vhd', '.vhdl', '.sv', '.svh', '.v',
                                    '.vh')
python_ls.CONFIG_FILEs = ('msim.prj', )

from hdlcc.diagnostics import DiagType
from hdlcc.hdlcc_base import HdlCodeCheckerBase

_logger = logging.getLogger(__name__)

LINT_DEBOUNCE_S = 0.5  # 500 ms
PARENT_PROCESS_WATCH_INTERVAL = 10  # 10 s
MAX_WORKERS = 64
PYTHON_FILE_EXTENSIONS = ('.py', '.pyi')
_CONFIG_FILES = ('pycodestyle.cfg', 'setup.cfg', 'tox.ini', '.flake8')

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

    def _toLspFormat(self, messages):
        for message in messages:
            _logger.info(message)
            # Translate the error into LSP severity
            severity = message.severity

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

            yield {
                'source': message.checker,
                'range': {
                    'start': {'line': (message.line_number or 0) - 1,
                              'character': -1, },
                    'end': {'line': -1,
                            'character': -1, },
                },
                'message': message.text,
                'severity': severity,
            }

    def getMessagesByPath(self, path, *args, **kwargs):
        """
        Translate message format into LSP format
        """
        return self._toLspFormat(
            super(HdlCodeCheckerServer, self).getMessagesByPath(path, *args, **kwargs))

    def getMessagesWithText(self, path, content):
        """
        Translate message format into LSP format
        """
        return self._toLspFormat(
            super(HdlCodeCheckerServer, self).getMessagesWithText(path, content))

class HdlccLanguageServer(PythonLanguageServer):
    """ Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    # pylint: disable=too-many-public-methods,redefined-builtin

    def __init__(self, *args, **kwargs):
        super(HdlccLanguageServer, self).__init__(*args, **kwargs)
        self._checker = None

    def capabilities(self):
        "Returns language server capabilities"
        server_capabilities = {
            #  'documentHighlightProvider': True,
            #  'documentSymbolProvider': True,
            #  'definitionProvider': True,
            #  'executeCommandProvider': {
            #      'commands': flatten(self._hook('pyls_commands'))
            #  },
            #  'hoverProvider': True,
            #  'referencesProvider': True,
            #  'renameProvider': True,
            #  'signatureHelpProvider': {
            #      'triggerCharacters': ['(', ',']
            #  },
            'textDocumentSync': defines.TextDocumentSyncKind.NONE,
            #  'experimental': merge(self._hook('pyls_experimental_capabilities'))
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

        self._checker = HdlCodeCheckerServer(
            self.workspace, initializationOptions.get('config_file', None))

        # Get our capabilities
        return {'capabilities': self.capabilities()}

    @debounce(LINT_DEBOUNCE_S, keyed_by='doc_uri')
    def lint(self, doc_uri, is_saved):
        if self._checker is None:
            return

        path = uris.to_fs_path(doc_uri)
        _logger.info("Linting %s (saved=%s)", repr(path), is_saved)

        # If the file has not been saved, use the appropriate method, which
        # will involve dumping the modified contents into a temporary file
        if is_saved:
            diagnostics = list(self._checker.getMessagesByPath(path))
        else:
            text = self.workspace.get_document(doc_uri).source
            diagnostics = list(self._checker.getMessagesWithText(path, text))

        if diagnostics:
            _logger.debug("Diags:")
            for diag in diagnostics:
                _logger.debug(diag)

        # Since we're debounced, the document may no longer be open
        if doc_uri in self.workspace.documents:
            self.workspace.publish_diagnostics(doc_uri, list(diagnostics))
