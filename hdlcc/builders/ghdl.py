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
"GHDL builder implementation"

import os
import os.path as p
import re
from glob import glob
from typing import Any, Iterable, List, Optional

from .base_builder import BaseBuilder

from hdlcc.diagnostics import BuilderDiag, DiagType
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.path import Path
from hdlcc.types import BuildFlags, FileType
from hdlcc.utils import runShellCommand


class GHDL(BaseBuilder):
    """
    Builder implementation of the GHDL compiler
    """

    # Implementation of abstract class properties
    builder_name = "ghdl"
    file_types = {FileType.vhdl}

    # Default build flags
    default_flags = {"global": {FileType.vhdl: ("-fexplicit", "-frelaxed-rules")}}

    # GHDL specific class properties
    _stdout_message_parser = re.compile(
        r"^(?P<filename>.*):(?=\d)"
        r"(?P<line_number>\d+):"
        r"(?P<column_number>\d+):"
        r"((?P<is_warning>warning:)\s*|\s*)"
        r"(?P<error_message>.*)",
        re.I,
    ).finditer

    _scan_library_paths = re.compile(
        r"^\s*(actual prefix|library directory):" r"\s*(?P<library_path>.*)\s*"
    ).search

    _shouldIgnoreLine = re.compile(
        "|".join([r"^\s*$", r"ghdl: compilation error"])
    ).match

    _iter_rebuild_units = re.compile(
        r'((?P<unit_type>entity|package) "(?P<unit_name>\w+)" is obsoleted by (entity|package) "\w+"'
        r"|"
        r"file (?P<rebuild_path>.*)\s+has changed and must be reanalysed)",
        flags=re.I,
    ).finditer

    def __init__(self, *args, **kwargs):
        self._version = ""
        super(GHDL, self).__init__(*args, **kwargs)
        self._parseBuiltinLibraries()

    def _makeRecords(self, line):
        # type: (str) -> Iterable[BuilderDiag]
        for match in GHDL._stdout_message_parser(line):
            info = match.groupdict()
            diag = BuilderDiag(
                builder_name=self.builder_name, text=info.get("error_message", None)
            )

            if info["is_warning"]:
                diag.severity = DiagType.WARNING
            else:
                diag.severity = DiagType.ERROR

            filename = info.get("filename")
            line_number = info.get("line_number")
            column_number = info.get("column_number")

            if filename is not None:
                diag.filename = Path(filename)
            if line_number is not None:
                diag.line_number = line_number
            if column_number is not None:
                diag.column_number = column_number

            self._logger.info("Diag: %s", diag)
            yield diag

    def _checkEnvironment(self):
        stdout = runShellCommand(["ghdl", "--version"])
        self._version = re.findall(r"(?<=GHDL)\s+([^\s]+)\s+", stdout[0])[0]
        self._logger.info(
            "GHDL version string: '%s'. " "Version number is '%s'",
            stdout[:-1],
            self._version,
        )

    @staticmethod
    def isAvailable():
        try:
            runShellCommand(["ghdl", "--version"])
            return True
        except OSError:
            return False

    def _parseBuiltinLibraries(self):
        # type: (...) -> Any
        """
        Discovers libraries that exist regardless before we do anything
        """
        for line in runShellCommand(["ghdl", "--dispconfig"]):
            library_path_match = self._scan_library_paths(line)
            if library_path_match:
                library_path = library_path_match.groupdict()["library_path"]
                self._logger.debug("library path is %s", library_path)

                # Up to v0.36 ghdl kept libraries at
                #   <library_path>/<vhdl starndard>/<name>
                # but his has been changed to
                #   <library_path>/<name>/<vhdl starndard>
                libraries_paths = glob(
                    p.join(library_path, "v93", "*")
                    if self._version < "0.36"
                    else p.join(library_path, "*")
                )

                for path in filter(p.isdir, libraries_paths):
                    name = path.split(p.sep)[-1]
                    self._builtin_libraries.add(Identifier(name.strip().lower()))

    def _getGhdlArgs(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> List[str]
        """
        Return the GHDL arguments that are common to most calls
        """
        cmd = [
            "-P%s" % self._work_folder,
            "--work=%s" % library,
            "--workdir=%s" % self._work_folder,
        ]
        if flags:
            cmd += flags
        cmd += [path.name]
        return cmd

    def _importSource(self, path, library, flags=None):
        """
        Runs GHDL with import source switch
        """
        vhdl_std = tuple(
            filter(lambda flag: flag.startswith("--std="), flags or tuple())
        )
        self._logger.debug("Importing source with std '%s'", vhdl_std)
        cmd = ["ghdl", "-i"] + self._getGhdlArgs(path, library, tuple(vhdl_std))
        return cmd

    def _analyzeSource(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> List[str]
        """
        Runs GHDL with analyze source switch
        """
        return ["ghdl", "-a"] + self._getGhdlArgs(path, library, flags)

    def _checkSyntax(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> List[str]
        """
        Runs GHDL with syntax check switch
        """
        return ["ghdl", "-s"] + self._getGhdlArgs(path, library, flags)

    def _buildSource(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> Iterable[str]
        self._importSource(path, library, flags)

        stdout = []  # type: List[str]
        for cmd in (
            self._analyzeSource(path, library, flags),
            self._checkSyntax(path, library, flags),
        ):
            stdout += runShellCommand(cmd)

        return stdout

    def _createLibrary(self, _):
        workdir = p.join(self._work_folder)
        if not p.exists(workdir):
            os.makedirs(workdir)

    def _searchForRebuilds(self, line):
        rebuilds = []

        for match in self._iter_rebuild_units(line):
            mdict = match.groupdict()
            # When compilers reports units out of date, they do this
            # by either
            #  1. Giving the path to the file that needs to be rebuilt
            #     when sources are from different libraries
            #  2. Reporting which design unit has been affected by a
            #     given change.
            if "rebuild_path" in mdict and mdict["rebuild_path"] is not None:
                rebuilds.append(mdict)
            else:
                rebuilds.append(
                    {"unit_type": mdict["unit_type"], "unit_name": mdict["unit_name"]}
                )

        return rebuilds
