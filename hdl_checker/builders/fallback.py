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
"Fallback builder for cases where no builder is found"

from typing import Iterable

from hdl_checker.builders.base_builder import BaseBuilder
from hdl_checker.diagnostics import CheckerDiagnostic
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, FileType


class Fallback(BaseBuilder):
    "Dummy fallback builder"

    # Implementation of abstract class properties
    builder_name = "fallback"  # type: ignore[assignment]
    file_types = {FileType.vhdl, FileType.verilog, FileType.systemverilog}  # type: ignore[assignment]

    def __init__(self, *args, **kwargs) -> None:
        self._version = "<undefined>"
        super(Fallback, self).__init__(*args, **kwargs)

    def _makeRecords(self, line: str) -> Iterable[CheckerDiagnostic]:  # pragma: no cover
        return []

    def _shouldIgnoreLine(self, line: str) -> bool:  # pragma: no cover
        return True

    def _checkEnvironment(self) -> None:
        return

    @staticmethod
    def isAvailable():
        return True

    def _buildSource(self, path: Path, library: Identifier, flags: BuildFlags | None = None) -> list[str]:  # pragma: no cover
        return []

    def _createLibrary(self, library: Identifier) -> None:  # pragma: no cover
        pass
