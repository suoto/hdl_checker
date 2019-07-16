# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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


import json
import logging
import os
import os.path as p

import mock
import six
import unittest2
from nose2.tools import such

from hdlcc.utils import patchPyls, onWindows
patchPyls()

# pylint: disable=ungrouped-imports

import hdlcc.lsp as lsp
from hdlcc.diagnostics import CheckerDiagnostic, DiagType

import pyls.lsp as defines
from pyls import uris
from pyls.workspace import Workspace
from pyls_jsonrpc.streams import JsonRpcStreamReader


_logger = logging.getLogger(__name__)

# pylint: disable=bad-whitespace

JSONRPC_VERSION = '2.0'
LSP_MSG_TEMPLATE = {'jsonrpc': JSONRPC_VERSION,
                    'id': 1,
                    'processId': None}

LSP_MSG_EMPTY_RESPONSE = {'jsonrpc': JSONRPC_VERSION, 'id': 1, 'result': None}

TEST_SUPPORT_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
VIM_HDL_EXAMPLES = p.abspath(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples"))

if onWindows():
    VIM_HDL_EXAMPLES = VIM_HDL_EXAMPLES.lower()

class TestDiagToLsp(unittest2.TestCase):

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
                line_number=1, column=1, error_code='error code',
                severity=diag_type)

            self.assertEqual(
                lsp.diagToLsp(diag),
                {'source': 'hdlcc test',
                 'range': {
                     'start': {
                         'line': 0,
                         'character': -1, },
                     'end': {
                         'line': -1,
                         'character': -1, }},
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
        msg = LSP_MSG_TEMPLATE.copy()
        msg.update({'method': 'initialize'})
        msg.update(params or {})
        _logger.debug("Sending message: %s", msg)
        server._endpoint.consume(msg)

        capabilities = json.loads(it.tx._read_message())
        _logger.debug("capabilities: %s", capabilities)

        it.assertIn('result', capabilities)
        it.assertEqual(capabilities['result'], {"capabilities": {"textDocumentSync": 1}})

        msg = LSP_MSG_TEMPLATE.copy()
        msg.update({'method': 'initialized'})
        _logger.debug("Sending message: %s", msg)
        server._endpoint.consume(msg)

        initialized_reply = json.loads(it.tx._read_message())
        it.assertEqual(initialized_reply, LSP_MSG_EMPTY_RESPONSE)

    @it.has_setup
    def setup():
        _logger.debug("Sever")
        #  rx_r, rx_w = os.pipe()
        tx_r, tx_w = os.pipe()

        #  rx = JsonRpcStreamWriter(os.fdopen(rx_w, 'wb'))
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
            _initializeServer(it.server)

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')
            msg = LSP_MSG_TEMPLATE.copy()
            msg.update({'method': 'text_document__did_open',
                        'params' : {
                            'textDocument': {
                                'uri': uris.from_fs_path(source),
                                'text': None}}})
            _logger.debug("Sending message: %s", msg)
            it.server._endpoint.consume(msg)

            # Read response from did_open
            did_open_reply = json.loads(it.tx._read_message())
            _logger.debug("did_open_reply: %s", did_open_reply)
            it.assertEqual(did_open_reply, LSP_MSG_EMPTY_RESPONSE)

            publish_reply = json.loads(it.tx._read_message())
            _logger.debug("publish_reply: %s", publish_reply)
            it.assertEqual(
                publish_reply,
                {'jsonrpc': JSONRPC_VERSION,
                 'method': 'textDocument/publishDiagnostics',
                 'params': {
                     'uri': uris.from_fs_path(source),
                     'diagnostics': [
                         {'source': 'HDL Code Checker/static',
                          'range': {'start': {'line': 42, 'character': -1},
                                    'end': {'line': -1, 'character': -1}},
                          'message': "Signal 'neat_signal' is never used",
                          'severity': defines.DiagnosticSeverity.Information,
                          'code': -1},
                         {'source': 'HDL Code Checker',
                          'range': {'start': {'line': -1, 'character': -1},
                                    'end': {'line': -1, 'character': -1}},
                          'severity': defines.DiagnosticSeverity.Error,
                          'message': "Exception while creating project for "
                                     "project file 'vimhdl.prj': IOError(2, 'No such file or directory')",
                          'code': -1}]}})

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
                {'params' : {
                    'rootUri': uris.from_fs_path(VIM_HDL_EXAMPLES),
                    'initializationOptions': {
                        'project_file': 'vimhdl.prj'}}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')
            msg = LSP_MSG_TEMPLATE.copy()
            msg.update({'method': 'text_document__did_open',
                        'params' : {
                            'textDocument': {
                                'uri': uris.from_fs_path(source),
                                'text': None}}})
            _logger.debug("Sending message: %s", msg)
            it.server._endpoint.consume(msg)

            # Not sure why this one comes out
            did_open_reply = json.loads(it.tx._read_message())
            _logger.debug("did_open_reply: %s", did_open_reply)
            it.assertEqual(did_open_reply['result'], None)

            #  # Handle notification message
            #  reply = json.loads(it.tx._read_message())
            #  _logger.debug("reply: %s", reply)
            #  it.assertEqual(
            #      reply,
            #      {'jsonrpc': JSONRPC_VERSION,
            #       'method': 'window/showMessage',
            #       'params': {
            #           'type': defines.MessageType.Warning,
            #           'message': "Target directory '%s' doesn't exist, "
            #                      "forcing cleanup" % p.join(VIM_HDL_EXAMPLES, '.hdlcc')}})

            publish_reply = json.loads(it.tx._read_message())
            _logger.debug("publish_reply: %s", publish_reply)
            it.assertEqual(
                publish_reply,
                {'jsonrpc': JSONRPC_VERSION,
                 'method': 'textDocument/publishDiagnostics',
                 'params': {
                     'uri': uris.from_fs_path(source),
                     'diagnostics': [
                         {'source': 'HDL Code Checker/static',
                          'range': {'start': {'line': 42, 'character': -1},
                                    'end': {'line': -1, 'character': -1}},
                          'message': "Signal 'neat_signal' is never used",
                          'severity': 3,
                          'code': -1}]}})

    with it.having('a non existing project file'):

        @it.should('respond capabilities upon initialization')
        def test():
            project_file = '__some_project_file.prj'
            it.assertFalse(p.exists(project_file))
            _initializeServer(
                it.server,
                {'params' : {
                    'initializationOptions': {
                        'rootUri': uris.from_fs_path(VIM_HDL_EXAMPLES),
                        'project_file': project_file}}})

        @it.should('lint file when opening it')
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd')
            msg = LSP_MSG_TEMPLATE.copy()
            msg.update({'method': 'text_document__did_open',
                        'params' : {
                            'textDocument': {
                                'uri': uris.from_fs_path(source),
                                'text': None}}})
            _logger.debug("Sending message: %s", msg)
            it.server._endpoint.consume(msg)

            # Read response from did_open
            did_open_reply = json.loads(it.tx._read_message())
            _logger.debug("did_open_reply: %s", did_open_reply)
            it.assertEqual(did_open_reply, LSP_MSG_EMPTY_RESPONSE)

            publish_reply = json.loads(it.tx._read_message())
            _logger.debug("publish_reply: %s", publish_reply)
            it.assertEqual(
                publish_reply,
                {'jsonrpc': JSONRPC_VERSION,
                 'method': 'textDocument/publishDiagnostics',
                 'params': {
                     'uri': uris.from_fs_path(source),
                     'diagnostics': [
                         {'source': 'HDL Code Checker/static',
                          'range': {'start': {'line': 42, 'character': -1},
                                    'end': {'line': -1, 'character': -1}},
                          'message': "Signal 'neat_signal' is never used",
                          'severity': defines.DiagnosticSeverity.Information,
                          'code': -1},
                         {'source': 'HDL Code Checker',
                          'range': {'start': {'line': -1, 'character': -1},
                                    'end': {'line': -1, 'character': -1}},
                          'severity': defines.DiagnosticSeverity.Error,
                          'message': "Exception while creating project for "
                                     "project file 'vimhdl.prj': IOError(2, 'No such file or directory')",
                          'code': -1}]}})

        @it.should("flag the project file doesn't exist")
        def test():
            source = p.join(VIM_HDL_EXAMPLES, 'some_source.vhd')
            it.assertFalse(p.exists(source))
            open(source, 'w').write('')

            msg = LSP_MSG_TEMPLATE.copy()
            msg.update({'method': 'text_document__did_open',
                        'params' : {
                            'textDocument': {
                                'uri': uris.from_fs_path(source),
                                'text': None}}})
            _logger.debug("Sending message: %s", msg)
            it.server._endpoint.consume(msg)

            # Read response from did_open
            did_open_reply = json.loads(it.tx._read_message())
            _logger.debug("did_open_reply: %s", did_open_reply)
            it.assertEqual(did_open_reply, LSP_MSG_EMPTY_RESPONSE)

            _logger.fatal("reply: %s", json.loads(it.tx._read_message()))

            for _ in range(3):
                msg = LSP_MSG_TEMPLATE.copy()
                msg.update({'method': 'text_document__did_save',
                            'params' : {
                                'textDocument': {
                                    'uri': uris.from_fs_path(source),
                                    'text': None}}})

                _logger.debug("Sending message: %s", msg)
                it.server._endpoint.consume(msg)

                # Not sure why this one comes out
                did_save_reply = json.loads(it.tx._read_message())
                _logger.debug("did_save_reply: %s", did_save_reply)
                it.assertEqual(did_save_reply['result'], None)

                import time
                time.sleep(1)
                _logger.fatal("reply: %s", json.loads(it.tx._read_message()))

            #  it.fail("Stop!")

it.createTests(globals())
