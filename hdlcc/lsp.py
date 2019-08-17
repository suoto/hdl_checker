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

# pylint: disable=useless-object-inheritance

import functools
import logging
import os.path as p
import sys

import pyls.lsp as defines # type: ignore
from pyls._utils import debounce # type: ignore
from pyls.python_ls import PythonLanguageServer # type: ignore
from pyls.uris import to_fs_path # type: ignore

from hdlcc.diagnostics import DiagType, FailedToCreateProject
from hdlcc.hdlcc_base import HdlCodeCheckerBase

MONITORED_FILES = ('.vhd', '.vhdl', '.sv', '.svh', '.v', '.vh')
CONFIG_FILES = ()

_logger = logging.getLogger(__name__)

LINT_DEBOUNCE_S = 0.5  # 500 ms
DEFAULT_PROJECT_FILENAME = 'vimhdl.prj'
PY2 = sys.version_info[0] == 2

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


def checkerDiagToLspDict(diag):
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

    result = {
        'source': diag.checker,
        'range': {
            'start': {'line': (diag.line_number or 1) - 1,
                      'character': (diag.column_number or 1) - 1, },
            'end': {'line': (diag.line_number or 1) - 1,
                    'character': (diag.column_number or 1) - 1, },
        },
        'message': diag.text,
        'severity': severity,
    }

    if diag.error_code:
        result['code'] = diag.error_code

    return result


class HdlCodeCheckerServer(HdlCodeCheckerBase):
    """
    HDL Code Checker project builder class
    """
    def __init__(self, workspace, project_file=DEFAULT_PROJECT_FILENAME):
        self._workspace = workspace
        self._project_mtime = 0
        if project_file is not None:
            self._project_mtime = p.getmtime(project_file)

        super(HdlCodeCheckerServer, self).__init__(project_file)

    def _shouldParseProjectFile(self):
        if self.project_file is None:
            return False

        if p.getmtime(self.project_file) <= self._project_mtime:
            return False

        self._project_mtime = p.getmtime(self.project_file)
        return True

    #  def _shouldRecreateTargetDir(self):
    #      if p.exists(self._getCacheFilename()):
    #          return False

    #      return self.config_parser.getBuilderName() != 'fallback'

    #  def _setupEnvIfNeeded(self):
    #      # On LSP, user can't force a fresh rebuild, we'll force a full clean if
    #      # - Project file is valid and has been modified
    #      # - Target directory doesn't exist (and NOT using fallback builder)
    #      #  if self.isSetupRunning() or self.config_parser.isParsing():
    #      #      _logger.info("Setup already running, jsut chill")
    #      #      return

    #      should_parse = self._shouldParseProjectFile()

    #      if should_parse or self._shouldRecreateTargetDir():
    #          if should_parse:
    #              self._handleUiInfo("Project file has changed, rebuilding project")
    #          else:
    #              self._handleUiInfo("Output dir not found, rebuilding project")
    #          self.clean()

    #      super(HdlCodeCheckerServer, self)._setupEnvIfNeeded()

    def _handleUiInfo(self, message):
        self._logger.debug("UI info: %s", message)
        if self._workspace:
            self._workspace.show_message(message, defines.MessageType.Info)

    def _handleUiWarning(self, message):
        self._logger.debug("UI warning: %s", message)
        if self._workspace:
            self._workspace.show_message(message, defines.MessageType.Warning)

    def _handleUiError(self, message):
        self._logger.debug("UI error: %s", message)
        if self._workspace:
            self._workspace.show_message(message, defines.MessageType.Error)

class HdlccLanguageServer(PythonLanguageServer):
    """ Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    # pylint: disable=too-many-public-methods,redefined-builtin

    def __init__(self, *args, **kwargs):
        super(HdlccLanguageServer, self).__init__(*args, **kwargs)
        # Default checker
        self._onProjectFileUpdate({'project_file': None})
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
        result = super(HdlccLanguageServer, self).m_initialize(
            processId=processId, rootUri=rootUri, rootPath=rootPath,
            initializationOptions={})

        self._onProjectFileUpdate(initializationOptions or {})

        return result

    def _onProjectFileUpdate(self, options):
        """
        Updates the checker server from options if the 'project_file' key is
        present
        """
        _logger.debug("Updating from %s", options)

        # Clear previous diagnostics
        self._global_diags = set()

        path = self._getProjectFilePath(options)

        try:
            self._checker = HdlCodeCheckerServer(self.workspace, path)
        except (IOError, OSError) as exc:
            _logger.info("Failed to create checker, reverting to fallback")
            self._global_diags.add(FailedToCreateProject(exc))
            self._checker = HdlCodeCheckerServer(self.workspace, None)

    def _getProjectFilePath(self, options=None):
        """
        Tries to get 'project_file' from the options dict and combine it with
        the root URI as provided by the workspace
        """
        path = (options or {}).get('project_file', DEFAULT_PROJECT_FILENAME)

        # Path has been explicitly set to none
        if 'project_file' in options and path is None:
            return None

        # Project file will be related to the root path
        if self.workspace:
            path = p.join(self.workspace.root_path or '', path)
        return path

    @debounce(LINT_DEBOUNCE_S, keyed_by='doc_uri')
    def lint(self, doc_uri, is_saved):
        diagnostics = list(self._getDiags(doc_uri, is_saved))
        _logger.info("Diagnostics: %s", diagnostics)

        if self._global_diags:
            diagnostics += list(self._global_diags)

        # Since we're debounced, the document may no longer be open
        if doc_uri in self.workspace.documents:
            # Both checker methods return generators, convert to a list before
            # returning
            self.workspace.publish_diagnostics(
                doc_uri, list([checkerDiagToLspDict(x) for x in diagnostics]))

    def _getDiags(self, doc_uri, is_saved):
        """
        Gets diags of the URI, wether from the saved file or from its
        contents
        """
        # If the file has not been saved, use the appropriate method, which
        # will involve dumping the modified contents into a temporary file
        path = to_fs_path(doc_uri)

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
        self._onProjectFileUpdate(settings or {})

    #  @_logCalls
    #  def m_workspace__did_change_watched_files(self, changes=None, **_kwargs):
    #      changed_monitored_files = set()
    #      config_changed = False
    #      for change in (changes or []):
    #          if change['uri'].endswith(MONITORED_FILES):
    #              changed_monitored_files.add(change['uri'])
    #          elif change['uri'].endswith(CONFIG_FILES):
    #              config_changed = True

    #      if config_changed:
    #          self.config.settings.cache_clear()
    #          self._checker.clean()
    #      elif not changed_monitored_files:
    #          # Only externally changed python files and lint configs may result
    #          # in changed diagnostics.
    #          return

    #      for doc_uri in self.workspace.documents:
    #          # Changes in doc_uri are already handled by m_text_document__did_save
    #          if doc_uri not in changed_monitored_files:
    #              self.lint(doc_uri, is_saved=False)
