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

# pylint: disable=missing-docstring
# pylint: disable=wrong-import-position
# pylint: disable=no-self-use
# pylint: disable=protected-access
# pylint: disable=function-redefined


import logging
import os
import os.path as p
import sys
import threading
from threading import Timer
import time

import mock
import unittest2
from nose2.tools import such

import pyls.lsp as defines
from pyls import uris
from pyls.workspace import Workspace
from pyls_jsonrpc.streams import JsonRpcStreamReader

import hdlcc.lsp as lsp
from hdlcc.diagnostics import CheckerDiagnostic, DiagType
from hdlcc.utils import onWindows

_logger = logging.getLogger(__name__)

# pylint: disable=bad-whitespace

JSONRPC_VERSION = '2.0'
LSP_MSG_TEMPLATE = {'jsonrpc': JSONRPC_VERSION,
                    'id': 1,
                    'processId': None}

LSP_MSG_EMPTY_RESPONSE = {'jsonrpc': JSONRPC_VERSION, 'id': 1, 'result': None}

MOCK_WAIT_TIMEOUT = 5

TEST_SUPPORT_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
VIM_HDL_EXAMPLES = p.abspath(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples"))

_ON_WINDOWS = sys.platform == "win32"

if onWindows():
    VIM_HDL_EXAMPLES = VIM_HDL_EXAMPLES.lower()

class TestCheckerDiagToLspDict(unittest2.TestCase):

    def test_converting_to_lsp(self):
        for diag_type, severity in (
                (DiagType.INFO,           defines.DiagnosticSeverity.Hint),
                (DiagType.STYLE_INFO,     defines.DiagnosticSeverity.Hint),
                (DiagType.STYLE_WARNING,  defines.DiagnosticSeverity.Information),
                (DiagType.STYLE_ERROR,    defines.DiagnosticSeverity.Information),
                (DiagType.WARNING,        defines.DiagnosticSeverity.Warning),
                (DiagType.ERROR,          defines.DiagnosticSeverity.Error),
                (DiagType.NONE,           defines.DiagnosticSeverity.Error)):

            _logger.info("Running %s and %s", diag_type, severity)

            diag = CheckerDiagnostic(
                checker='hdlcc test', text='some diag', filename='filename',
                line_number=1, column_number=1, error_code='error code',
                severity=diag_type)

            self.assertEqual(
                lsp.checkerDiagToLspDict(diag),
                {'source': 'hdlcc test',
                 'range': {
                     'start': {
                         'line': 0,
                         'character': 0, },
                     'end': {
                         'line': 0,
                         'character': 0, }},
                 'message': 'some diag',
                 'severity': severity,
                 'code': 'error code'})

    def test_workspace_notify(self):
        workspace = mock.MagicMock(spec=Workspace)

        server = lsp.HdlCodeCheckerServer(workspace, project_file=None)

        server._handleUiInfo('some info')  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            'some info', defines.MessageType.Info)
        workspace.show_message.reset_mock()

        server._handleUiWarning('some warning')  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            'some warning', defines.MessageType.Warning)
        workspace.show_message.reset_mock()

        server._handleUiError('some error')  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            'some error', defines.MessageType.Error)

with such.A("LSP server") as it:

    def _initializeServer(server, params=None):
        it.assertEqual(
            server.m_initialize(**(params or {})),
            {"capabilities": {"textDocumentSync": 1}})

        it.assertEqual(server.m_initialized(), None)

    def _waitOnMockCall(meth):
        event = threading.Event()

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
            it.fail("Timeout waiting for %s" % meth)

        return result


    @it.has_setup
    def setup():
        _logger.debug("Sever")
        tx_r, tx_w = os.pipe()
        it.tx = JsonRpcStreamReader(os.fdopen(tx_r, 'rb'))

        it.rx = mock.MagicMock()
        it.rx.closed = False

        it.server = lsp.HdlccLanguageServer(it.rx, os.fdopen(tx_w, 'wb'))

    @it.has_teardown
    def teardown():
        _logger.debug("Shutting down server")
        msg = LSP_MSG_TEMPLATE.copy()
        msg.update({'method': 'exit'})
        it.server._endpoint.consume(msg)

        # Close the pipe from the server to stdout and empty any pending
        # messages
        it.tx.close()
        it.tx.listen(_logger.fatal)

        del it.server
        import shutil
        try:
            shutil.rmtree(p.join(VIM_HDL_EXAMPLES, '.hdlcc'))
        except OSError:
            pass

    with it.having('no project file'):

        @it.should('respond capabilities upon initialization')
        def test():
            _initializeServer(
                it.server,
                params={
                    'rootUri': uris.from_fs_path(VIM_HDL_EXAMPLES),
                    'initializationOptions': {
                        'project_file': None}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')

            meth = mock.MagicMock()
            with mock.patch.object(it.server.workspace,
                                   'publish_diagnostics',
                                   meth):

                it.server.m_text_document__did_open(
                    textDocument={'uri': uris.from_fs_path(source),
                                  'text': None})

                call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
                doc_uri, diagnostics = call[1]
                _logger.info("doc_uri: %s", doc_uri)
                _logger.info("diagnostics: %s", diagnostics)

                it.assertEqual(doc_uri, uris.from_fs_path(source))
                it.assertItemsEqual(
                    diagnostics,
                    [{'source': 'HDL Code Checker/static',
                      'range': {'start': {'line': 42, 'character': 0},
                                'end': {'line': 42, 'character': 0}},
                      'message': "Signal 'neat_signal' is never used",
                      'severity': defines.DiagnosticSeverity.Information}])


        @it.should('not lint file outside workspace')
        @mock.patch.object(Workspace, 'publish_diagnostics',
                           mock.MagicMock(spec=Workspace.publish_diagnostics))
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                            'clock_divider.vhd')

            it.server.lint(doc_uri=uris.from_fs_path(source),
                           is_saved=True)

            it.server.workspace.publish_diagnostics.assert_not_called()

    with it.having('an existing and valid project file'):

        @it.should('respond capabilities upon initialization')
        def test():
            _initializeServer(
                it.server,
                params={
                    'rootUri': uris.from_fs_path(VIM_HDL_EXAMPLES),
                    'initializationOptions': {
                        'project_file': 'vimhdl.prj'}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')

            meth = mock.MagicMock()
            with mock.patch.object(it.server.workspace,
                                   'publish_diagnostics',
                                   meth):

                it.server.m_text_document__did_open(
                    textDocument={'uri': uris.from_fs_path(source),
                                  'text': None})

                call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
                doc_uri, diagnostics = call[1]
                _logger.info("doc_uri: %s", doc_uri)
                _logger.info("diagnostics: %s", diagnostics)

                it.assertEqual(doc_uri, uris.from_fs_path(source))
                it.assertItemsEqual(
                    diagnostics,
                    [{'source': 'HDL Code Checker/static',
                      'range': {'start': {'line': 42, 'character': 0},
                                'end': {'line': 42, 'character': 0}},
                      'message': "Signal 'neat_signal' is never used",
                      'severity': defines.DiagnosticSeverity.Information}])

    with it.having('a non existing project file'):

        @it.should('respond capabilities upon initialization')
        def test():
            it.project_file = '__some_project_file.prj'
            it.assertFalse(p.exists(it.project_file))

            _initializeServer(
                it.server,
                params={
                    'rootUri': uris.from_fs_path(VIM_HDL_EXAMPLES),
                    'initializationOptions': {
                        'project_file': it.project_file}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')

            meth = mock.MagicMock()
            with mock.patch.object(it.server.workspace,
                                   'publish_diagnostics',
                                   meth):

                it.server.m_text_document__did_open(
                    textDocument={'uri': uris.from_fs_path(source),
                                  'text': None})

                call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
                doc_uri, diagnostics = call[1]
                _logger.info("doc_uri: %s", doc_uri)
                _logger.info("diagnostics: %s", diagnostics)

                if _ON_WINDOWS:
                    error = '[WinError 2] The system cannot find the file specified'
                else:
                    error = '[Errno 2] No such file or directory'

                it.assertEqual(doc_uri, uris.from_fs_path(source))
                it.assertItemsEqual(
                    diagnostics,
                    [{'source': 'HDL Code Checker/static',
                      'range': {'start': {'line': 42, 'character': 0},
                                'end': {'line': 42, 'character': 0}},
                      'message': "Signal 'neat_signal' is never used",
                      'severity': defines.DiagnosticSeverity.Information},
                     {'source': 'HDL Code Checker',
                      'range': {'start': {'line': 0, 'character': 0},
                                'end': {'line': 0, 'character': 0}},
                      'message': "Exception while creating server: '{}: {}'"
                                 .format(error,
                                         repr(p.join(VIM_HDL_EXAMPLES,
                                                     it.project_file))),
                      'severity': defines.DiagnosticSeverity.Error}])

    with it.having('no root URI or project file set'):

        @it.should('respond capabilities upon initialization')
        def test():
            _initializeServer(
                it.server,
                params={
                    'initializationOptions': {
                        'project_file': None}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')

            meth = mock.MagicMock()
            with mock.patch.object(it.server.workspace,
                                   'publish_diagnostics',
                                   meth):

                it.server.m_text_document__did_open(
                    textDocument={'uri': uris.from_fs_path(source),
                                  'text': None})

                call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
                doc_uri, diagnostics = call[1]
                _logger.info("doc_uri: %s", doc_uri)
                _logger.info("diagnostics: %s", diagnostics)

                it.assertEqual(doc_uri, uris.from_fs_path(source))
                it.assertItemsEqual(
                    diagnostics,
                    [{'source': 'HDL Code Checker/static',
                      'range': {'start': {'line': 42, 'character': 0},
                                'end': {'line': 42, 'character': 0}},
                      'message': "Signal 'neat_signal' is never used",
                      'severity': defines.DiagnosticSeverity.Information}])

    with it.having('no root URI but project file set'):

        @it.should('respond capabilities upon initialization')
        def test():
            # In this case, project file is an absolute path, since there's no
            # root URI
            _initializeServer(
                it.server,
                params={
                    'initializationOptions': {
                        'project_file': p.join(VIM_HDL_EXAMPLES, 'vimhdl.prj')}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')

            meth = mock.MagicMock()
            with mock.patch.object(it.server.workspace,
                                   'publish_diagnostics',
                                   meth):

                it.server.m_text_document__did_open(
                    textDocument={'uri': uris.from_fs_path(source),
                                  'text': None})

                call = _waitOnMockCall(it.server.workspace.publish_diagnostics)
                doc_uri, diagnostics = call[1]
                _logger.info("doc_uri: %s", doc_uri)
                _logger.info("diagnostics: %s", diagnostics)

                it.assertEqual(doc_uri, uris.from_fs_path(source))
                it.assertItemsEqual(
                    diagnostics,
                    [{'source': 'HDL Code Checker/static',
                      'range': {'start': {'line': 42, 'character': 0},
                                'end': {'line': 42, 'character': 0}},
                      'message': "Signal 'neat_signal' is never used",
                      'severity': defines.DiagnosticSeverity.Information}])

it.createTests(globals())
