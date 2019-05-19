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
try:
    import socketserver
except ImportError:
    # Python 2.7 support
    import SocketServer as socketserver
import threading

from pyls_jsonrpc.dispatchers import MethodDispatcher
from pyls_jsonrpc.endpoint import Endpoint
from pyls_jsonrpc.streams import JsonRpcStreamReader, JsonRpcStreamWriter

from hdlcc.utils import debounce, isProcessRunning

from . import defines, uris

#  from . import lsp, _utils, uris
#  from .config import config
#  from .workspace import Workspace

_logger = logging.getLogger(__name__)

LINT_DEBOUNCE_S = 0.5  # 500 ms
PARENT_PROCESS_WATCH_INTERVAL = 10  # 10 s
MAX_WORKERS = 64
PYTHON_FILE_EXTENSIONS = ('.py', '.pyi')
_CONFIG_FILES = ('pycodestyle.cfg', 'setup.cfg', 'tox.ini', '.flake8')

# pylint: disable=useless-object-inheritance

class _StreamHandlerWrapper(socketserver.StreamRequestHandler, object):
    """A wrapper class that is used to construct a custom handler class."""

    delegate = None

    def setup(self):
        super(_StreamHandlerWrapper, self).setup()
        # pylint: disable=no-member
        self.delegate = self.DELEGATE_CLASS(self.rfile, self.wfile)

    def handle(self):
        self.delegate.start()


def startTcpLangServer(bind_addr, port, handler_class):
    """
    Starts a socket-based language server
    """
    if not issubclass(handler_class, LanguageServer):
        raise ValueError('Handler class must be an instance of LanguageServer')

    # Construct a custom wrapper class around the user's handler_class
    wrapper_class = type(
        handler_class.__name__ + 'Handler',
        (_StreamHandlerWrapper,),
        {'DELEGATE_CLASS': handler_class}
    )

    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer((bind_addr, port), wrapper_class)

    try:
        _logger.info('Serving %s on (%s, %s)', handler_class.__name__, bind_addr, port)
        server.serve_forever()
    finally:
        _logger.info('Shutting down')
        server.server_close()


def startIoLangServer(rfile, wfile, check_parent_process, handler_class):
    """
    Starts a stdio-based language server
    """
    if not issubclass(handler_class, LanguageServer):
        raise ValueError('Handler class must be an instance of LanguageServer')
    _logger.info('Starting %s IO language server', handler_class.__name__)
    server = handler_class(rfile, wfile, check_parent_process)
    server.start()

def _toStr(d):
    result = []
    for key, value in d.items():
        if key != 'text':
            result += ['%s: %s' % (repr(key), repr(value))]
        else:
            result += ['%s: <%d lines>' % (repr(key), value.count('\n'))]

    return ', '.join(result)

def _logCalls(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        _str = "%s(%s, %s)" % (func.__name__, args, _toStr(kwargs))
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
    func._lsp_unimplemented = True
    return func


class LanguageServer(MethodDispatcher):
    """ Implementation of the Microsoft VSCode Language Server Protocol
    https://github.com/Microsoft/language-server-protocol/blob/master/versions/protocol-1-x.md
    """

    # pylint: disable=too-many-public-methods,redefined-builtin

    def __init__(self, rx, tx, check_parent_process=False):
        self._jsonrpc_stream_reader = JsonRpcStreamReader(rx)
        self._jsonrpc_stream_writer = JsonRpcStreamWriter(tx)
        self._check_parent_process = check_parent_process
        self._endpoint = Endpoint(self, self._jsonrpc_stream_writer.write, max_workers=MAX_WORKERS)
        self._dispatchers = []
        self._shutdown = False

    def start(self):
        """Entry point for the server."""
        self._jsonrpc_stream_reader.listen(self._endpoint.consume)

    def __getitem__(self, item):
        """Override getitem to fallback through multiple dispatchers."""
        if self._shutdown and item != 'exit':
            # exit is the only allowed method during shutdown
            _logger.debug("Ignoring non-exit method during shutdown: %s", item)
            raise KeyError

        try:
            return super(LanguageServer, self).__getitem__(item)
        except KeyError:
            # Fallback through extra dispatchers
            for dispatcher in self._dispatchers:
                try:
                    return dispatcher[item]
                except KeyError:
                    continue

        raise KeyError()

    @_logCalls
    def m_shutdown(self, **_kwargs):
        "Shutdowns the server"
        self._shutdown = True

    @_logCalls
    def m_exit(self, **_kwargs):
        "Don't know yet"
        self._endpoint.shutdown()
        self._jsonrpc_stream_reader.close()
        self._jsonrpc_stream_writer.close()

    def capabilities(self):
        "Returns language server capabilities"
        server_capabilities = {
            'documentHighlightProvider': True,
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
            'textDocumentSync': defines.TextDocumentSyncKind.INCREMENTAL,
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
        _logger.debug('Language server initialized with %s %s %s %s',
                      processId, rootUri, rootPath, initializationOptions)

        if rootUri is None:
            rootUri = uris.from_fs_path(rootPath) if rootPath is not None else ''

        if self._check_parent_process and processId is not None:
            def watchParentProcess(pid):
                # exist when the given pid is not alive
                if not isProcessRunning(pid):
                    _logger.info("parent process %s is not alive", pid)
                    self.m_exit()
                _logger.debug("parent process %s is still alive", pid)
                threading.Timer(PARENT_PROCESS_WATCH_INTERVAL, watchParentProcess, args=[pid]).start()

            watching_thread = threading.Thread(target=watchParentProcess, args=(processId,))
            watching_thread.daemon = True
            watching_thread.start()

        # Get our capabilities
        return {'capabilities': self.capabilities()}

    @_logCalls
    @_markUnimplemented
    def m_initialized(self, **_kwargs):
        "Unimplemented LSP handler"

    def execute_command(self, command, arguments):
        pass

    @debounce(LINT_DEBOUNCE_S, keyed_by='doc_uri')
    def lint(self, doc_uri, is_saved):
        _logger.info("Linting %s, saved=%s", doc_uri, is_saved)

    @_logCalls
    @_markUnimplemented
    def m_text_document__did_close(self,  # pylint: disable=invalid-name
                                   textDocument=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    def m_text_document__did_open(self,  # pylint: disable=invalid-name
                                  textDocument=None, **_kwargs):
        #  self.workspace.put_document(textDocument['uri'], textDocument['text'], version=textDocument.get('version'))
        #  self._hook('pyls_document_did_open', textDocument['uri'])
        self.lint(textDocument['uri'], is_saved=False)

    @_logCalls
    def m_text_document__did_change(self,  # pylint: disable=invalid-name
                                    contentChanges=None, textDocument=None,
                                    **_kwargs):
        #  for change in contentChanges:
        #      self.workspace.update_document(
        #          textDocument['uri'],
        #          change,
        #          version=textDocument.get('version')
        #      )
        self.lint(textDocument['uri'], is_saved=False)

    @_logCalls
    def m_text_document__did_save(self,  # pylint: disable=invalid-name
                                  textDocument=None, **_kwargs):
        self.lint(textDocument['uri'], is_saved=True)

    @_logCalls
    @_markUnimplemented
    def m_text_document__code_action(self,  # pylint: disable=invalid-name
                                     textDocument=None, range=None,
                                     context=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__code_lens(self,  # pylint: disable=invalid-name
                                   textDocument=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__completion(self,  # pylint: disable=invalid-name
                                    textDocument=None, position=None,
                                    **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__definition(self,  # pylint: disable=invalid-name
                                    textDocument=None, position=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__document_highlight(self,  # pylint: disable=invalid-name
                                            textDocument=None, position=None,
                                            **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__hover(self,  # pylint: disable=invalid-name
                               textDocument=None, position=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__document_symbol(self,  # pylint: disable=invalid-name
                                         textDocument=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__formatting(self,  # pylint: disable=invalid-name
                                    textDocument=None, _options=None,
                                    **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__rename(self,  # pylint: disable=invalid-name
                                textDocument=None, position=None, newName=None,
                                **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__range_formatting(self,  # pylint: disable=invalid-name
                                          textDocument=None, range=None,
                                          _options=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__references(self,  # pylint: disable=invalid-name
                                    textDocument=None, position=None,
                                    context=None, **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_text_document__signature_help(self,  # pylint: disable=invalid-name
                                        textDocument=None, position=None,
                                        **_kwargs):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_workspace__did_change_configuration(self,  # pylint: disable=invalid-name
                                              settings=None):
        "Unimplemented LSP handler"

    @_logCalls
    @_markUnimplemented
    def m_workspace__did_change_watched_files(self,  # pylint: disable=invalid-name
                                              changes=None, **_kwargs):
        changed_py_files = set()
        config_changed = False
        for path in (changes or []):
            if path['uri'].endswith(PYTHON_FILE_EXTENSIONS):
                changed_py_files.add(path['uri'])
            elif path['uri'].endswith(_CONFIG_FILES):
                config_changed = True

        #  if config_changed:
        #      self.config.settings.cache_clear()
        #  elif not changed_py_files:
        #      # Only externally changed python files and lint configs may result in changed diagnostics.
        #      return

        #  for doc_uri in self.workspace.documents:
        #      # Changes in doc_uri are already handled by m_text_document__did_save
        #      if doc_uri not in changed_py_files:
        #          self.lint(doc_uri, is_saved=False)

    @_logCalls
    def m_workspace__execute_command(self, command=None, arguments=None):
        return self.execute_command(command, arguments)



def flatten(list_of_lists):
    return [item for lst in list_of_lists for item in lst]


def merge(list_of_dicts):
    return {k: v for dictionary in list_of_dicts for k, v in dictionary.items()}
