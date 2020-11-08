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
"""
Test code inside hdl_checker.lsp that doesn't depend on a server/client setup
"""

import logging
from tempfile import mkdtemp
from typing import Any

import parameterized  # type: ignore
import unittest2  # type: ignore
from mock import Mock
from pygls.types import DiagnosticSeverity, MessageType, Position, Range

from hdl_checker import lsp
from hdl_checker.diagnostics import CheckerDiagnostic, DiagType
from hdl_checker.path import Path, TemporaryPath

_logger = logging.getLogger(__name__)


class TestCheckerDiagToLspDict(unittest2.TestCase):
    """
    Test code inside hdl_checker.lsp that doesn't depend on a server/client
    setup
    """

    @parameterized.parameterized.expand(
        [
            (DiagType.INFO, DiagnosticSeverity.Information),
            (DiagType.STYLE_INFO, DiagnosticSeverity.Information),
            (DiagType.STYLE_WARNING, DiagnosticSeverity.Information),
            (DiagType.STYLE_ERROR, DiagnosticSeverity.Information),
            (DiagType.WARNING, DiagnosticSeverity.Warning),
            (DiagType.ERROR, DiagnosticSeverity.Error),
            (DiagType.NONE, DiagnosticSeverity.Error),
        ]
    )
    def test_converting_to_lsp(self, diag_type, severity):
        # type: (...) -> Any
        """
        Test conversion between hdl_checker.DiagType to pygls.types.DiagnosticSeverity
        """
        _logger.info("Running %s and %s", diag_type, severity)

        diag = lsp.checkerDiagToLspDict(
            CheckerDiagnostic(
                checker="hdl_checker test",
                text="some diag",
                filename=Path("filename"),
                line_number=0,
                column_number=0,
                error_code="error code",
                severity=diag_type,
            )
        )

        self.assertEqual(diag.code, "error code")
        self.assertEqual(diag.source, "hdl_checker test")
        self.assertEqual(diag.message, "some diag")
        self.assertEqual(diag.severity, severity)
        self.assertEqual(
            diag.range,
            Range(
                start=Position(line=0, character=0), end=Position(line=0, character=0),
            ),
        )

    def test_workspace_notify(self) -> None:  # pylint: disable=no-self-use
        """
        Test server notification messages call the appropriate LS methods
        """
        workspace = Mock()
        workspace.show_message = Mock()

        server = lsp.Server(
            workspace, root_dir=TemporaryPath(mkdtemp(prefix="hdl_checker_"))
        )
        workspace.show_message.reset_mock()

        server._handleUiInfo("some info")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with("some info", MessageType.Info)
        workspace.show_message.reset_mock()

        server._handleUiWarning("some warning")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with(
            "some warning", MessageType.Warning
        )
        workspace.show_message.reset_mock()

        server._handleUiError("some error")  # pylint: disable=protected-access
        workspace.show_message.assert_called_once_with("some error", MessageType.Error)
