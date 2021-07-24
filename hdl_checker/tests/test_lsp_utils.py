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
import time
from multiprocessing import Queue
from tempfile import mkdtemp
from typing import Any

import mock
import parameterized  # type: ignore
import unittest2  # type: ignore
from pygls.types import DiagnosticSeverity, MessageType, Position, Range

from hdl_checker import lsp
from hdl_checker.diagnostics import CheckerDiagnostic, DiagType
from hdl_checker.path import Path, TemporaryPath
from hdl_checker.utils import debounce

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
    def test_convertingDiagnosticType(self, diag_type, severity):
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
                start=Position(line=0, character=0), end=Position(line=0, character=1),
            ),
        )

    def test_workspaceNotify(self) -> None:  # pylint: disable=no-self-use
        """
        Test server notification messages call the appropriate LS methods
        """
        workspace = mock.Mock()
        workspace.show_message = mock.Mock()

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

    def test_debounceWithoutKey(self):
        _logger.info("#" * 100)
        interval = 0.1

        queue = Queue()

        def func(arg):
            _logger.info("Called with %s", arg)
            queue.put(arg)

        wrapped = debounce(interval)(func)
        self.assertTrue(queue.empty())

        wrapped(1)
        wrapped(2)
        self.assertTrue(queue.empty())

        time.sleep(2 * interval)

        self.assertEqual(queue.get(1), 2)
        self.assertTrue(queue.empty())

    def test_debounceWithKey(self):
        _logger.info("#" * 100)
        interval = 0.1

        obj = mock.Mock()

        def func(arg):
            _logger.info("Called with %s", arg)
            obj(arg)

        wrapped = debounce(interval, "arg")(func)
        obj.assert_not_called()

        wrapped(1)
        wrapped(2)
        wrapped(3)

        obj.assert_not_called()

        time.sleep(2 * interval)

        obj.assert_has_calls(
            [mock.call(1), mock.call(2), mock.call(3),], any_order=True
        )

        wrapped(4)
        wrapped(4)
        wrapped(4)
        time.sleep(2 * interval)

        obj.assert_has_calls(
            [mock.call(1), mock.call(2), mock.call(3), mock.call(4),], any_order=True
        )
