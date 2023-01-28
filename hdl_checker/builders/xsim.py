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
"Xilinx Simulator builder implementation"

import os.path as p
import re
import shutil
import tempfile
from typing import Iterable, Mapping, Optional

from hdl_checker.diagnostics import BuilderDiag, DiagType
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, FileType
from hdl_checker.utils import runShellCommand

from .base_builder import BaseBuilder

_ITER_REBUILD_UNITS = re.compile(
    r"ERROR:\s*\[[^\]]*\]\s*"
    r"'?.*/(?P<library_name>\w+)/(?P<unit_name>\w+)\.vdb'?"
    r"\s+needs to be re-saved.*",
    flags=re.I,
).finditer

# XSIM specific class properties
_STDOUT_MESSAGE_SCANNER = re.compile(
    r"^(?P<severity>[EW])\w+:\s*"
    r"\[(?P<error_code>[^\]]+)\]\s*"
    r"(?P<error_message>[^\[]+)\s*"
    r"("
    r"\[(?P<filename>[^:]+):"
    r"(?P<line_number>\d+)\]"
    r")?",
    flags=re.I,
)


class XSIM(BaseBuilder):
    """Builder implementation of the xvhdl and xvlog compiler"""

    # Implementation of abstract class properties
    builder_name = "xsim"
    file_types = {FileType.vhdl, FileType.verilog, FileType.systemverilog}

    def _shouldIgnoreLine(self, line):
        # type: (str) -> bool
        if "ignored due to previous errors" in line:
            return True

        # Ignore messages like
        # ERROR: [VRFC 10-3032] 'library.package' failed to restore
        # This message doesn't come alone, we should be getting other (more
        # usefull) info anyway
        if "[VRFC 10-3032]" in line:  # pragma: no cover
            return True

        return not (line.startswith("ERROR") or line.startswith("WARNING"))

    def __init__(self, *args, **kwargs):
        # type: (...) -> None
        self._version = ""
        super().__init__(*args, **kwargs)
        self._xsimini = p.join(self._work_folder, ".xsim.init")
        # Create the ini file
        with open(self._xsimini, "w", encoding="utf8"):
            pass

    def _makeRecords(self, line):
        # type: (str) -> Iterable[BuilderDiag]
        for match in _STDOUT_MESSAGE_SCANNER.finditer(line):

            info = match.groupdict()

            # Filename and line number aren't always present
            filename = info.get("filename", None)
            line_number = info.get("line_number", None)

            if info.get("severity", None) in ("W", "e"):
                severity = DiagType.WARNING
            else:
                severity = DiagType.ERROR

            yield BuilderDiag(
                builder_name=self.builder_name,
                filename=None if filename is None else Path(filename),
                text=info["error_message"].strip(),
                error_code=info["error_code"],
                line_number=None if line_number is None else int(line_number) - 1,
                severity=severity,
            )

    def _parseBuiltinLibraries(self):
        "(Not used by XSIM)"
        return (
            Identifier(x, case_sensitive=False)
            for x in (
                "ieee",
                "std",
                "unisim",
                "xilinxcorelib",
                "synplify",
                "synopsis",
                "maxii",
                "family_support",
            )
        )

    def _checkEnvironment(self):
        stdout = runShellCommand(
            ["xvhdl", "--nolog", "--version"], cwd=self._work_folder
        )
        self._version = re.findall(r"^Vivado Simulator\s+([\d\.]+)", stdout[0])[0]
        self._logger.info(
            "xvhdl version string: '%s'. Version number is '%s'",
            stdout[:-1],
            self._version,
        )

    @staticmethod
    def isAvailable():
        try:
            temp_dir = tempfile.mkdtemp()
            runShellCommand(["xvhdl", "--nolog", "--version"], cwd=temp_dir)
            runShellCommand(["xvlog", "--nolog", "--version"], cwd=temp_dir)
            return True
        except OSError:
            return False
        finally:
            shutil.rmtree(temp_dir)

    def _createLibrary(self, library):
        # type: (Identifier) -> None
        with open(self._xsimini, mode="w", encoding="utf8") as fd:
            content = "\n".join(
                [
                    f"{x}=%s" % p.join(self._work_folder, x.name)
                    for x in self._added_libraries
                ]
            )
            fd.write(content)

    def _buildSource(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> Iterable[str]
        xsim_cmd = None
        filetype = FileType.fromPath(path)
        if filetype == FileType.vhdl:
            xsim_cmd = "xvhdl"
        if filetype in (FileType.verilog, FileType.systemverilog):
            xsim_cmd = "xvlog"
        assert xsim_cmd is not None
        cmd = [
            xsim_cmd,
            "--nolog",
            "--verbose",
            "0",
            "--initfile",
            self._xsimini,
            "--work",
            library.name,
        ]
        if filetype == FileType.systemverilog:
            cmd += ["-sv"]
        cmd += [str(x) for x in (flags or [])]
        cmd += [path.name]
        return runShellCommand(cmd, cwd=self._work_folder)

    def _searchForRebuilds(self, path, line):
        # type: (Path, str) -> Iterable[Mapping[str, str]]
        for match in _ITER_REBUILD_UNITS(line):
            dict_ = match.groupdict()
            yield {
                "library_name": dict_["library_name"],
                "unit_name": dict_["unit_name"],
            }
