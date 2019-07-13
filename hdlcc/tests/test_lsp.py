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

# pylint: disable=function-redefined, missing-docstring, protected-access

import logging
import unittest

import mock

from hdlcc.utils import patchPyls

patchPyls()

import hdlcc.lsp as lsp
import pyls.lsp as defines
from hdlcc.diagnostics import DiagType, CheckerDiagnostic

_logger = logging.getLogger(__name__)

# pylint: disable=bad-whitespace

class TestDiagToLsp(unittest.TestCase):

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
        workspace = mock.MagicMock()
        workspace.show_message = mock.MagicMock()

        server = lsp.HdlCodeCheckerServer(workspace)

        server._handleUiInfo('some info')
        workspace.show_message.assert_called_once_with(
            'some info', defines.MessageType.Info)
        workspace.show_message.reset_mock()

        server._handleUiWarning('some warning')
        workspace.show_message.assert_called_once_with(
            'some warning', defines.MessageType.Warning)
        workspace.show_message.reset_mock()

        server._handleUiError('some error')
        workspace.show_message.assert_called_once_with(
            'some error', defines.MessageType.Error)
