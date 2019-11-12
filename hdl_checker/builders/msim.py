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
"ModelSim builder implementation"

import os
import os.path as p
import re
from shutil import copyfile
from typing import Any, Iterable, List, Optional

from .base_builder import BaseBuilder

from hdl_checker.database import Database
from hdl_checker.diagnostics import BuilderDiag, DiagType
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, BuildFlagScope, FileType
from hdl_checker.utils import runShellCommand


class MSim(BaseBuilder):
    """Builder implementation of the ModelSim compiler"""

    # Implementation of abstract class properties
    builder_name = "msim"
    file_types = {FileType.vhdl, FileType.verilog, FileType.systemverilog}

    # MSim specific class properties
    _stdout_message_scanner = re.compile(
        r"""^\*\*\s*
                (?P<severity>[WE])\w+\s*
                (:?\(suppressible\))?:\s*
                (:?
                    (:?\s*\[\d+\])?\s*
                    (?P<filename>.*(?=\(\d+\)))
                    \((?P<line_number>\d+)\):
                |
                    \(vcom-\d+\)
                )?
            \s*(?P<error_message>.*)\s*""",
        flags=re.VERBOSE,
    ).finditer

    _should_ignore = re.compile(
        "|".join(
            [
                r"^\s*$",
                r"^(?!\*\*\s(Error|Warning)\b).*",
                r".*VHDL Compiler exiting\s*$",
            ]
        )
    ).match

    _iter_rebuild_units = re.compile(
        r"("
        r"Recompile\s*(?P<lib_name_0>\w+)\.(?P<unit_name_0>\w+)\s+because"
        r"\s+.*?\s+ha(?:ve|s) changed"
        r"|"
        r"^\*\* Warning:.*\(vcom-1127\)\s*Entity\s(?P<lib_name_1>\w+)\."
        r"(?P<unit_name_1>\w+).*"
        r")"
    ).finditer

    _BuilderLibraryScanner = re.compile(
        r"^\"(?P<library_name>\w+)\""
        r"\s+maps to directory\s+"
        r"(?P<library_path>.*)\.$",
        re.I,
    )

    # Default build flags
    default_flags = {
        BuildFlagScope.dependencies: {
            FileType.vhdl: ("-defercheck", "-nocheck", "-permissive"),
            FileType.verilog: ("-permissive",),
            FileType.systemverilog: ("-permissive",),
        },
        BuildFlagScope.single: {
            FileType.vhdl: (
                "-check_synthesis",
                "-lint",
                "-rangecheck",
                "-pedanticerrors",
            ),
            FileType.verilog: ("-lint", "-hazards", "-pedanticerrors"),
            FileType.systemverilog: ("-lint", "-hazards", "-pedanticerrors"),
        },
        BuildFlagScope.all: {
            FileType.vhdl: ("-explicit",),
            FileType.verilog: (),
            FileType.systemverilog: (),
        },
    }

    def _shouldIgnoreLine(self, line):
        return self._should_ignore(line)

    def __init__(self, work_folder, database):
        # type: (Path, Database) -> None
        self._version = ""
        self._modelsim_ini = Path(p.join(work_folder.name, "modelsim.ini"))
        super(MSim, self).__init__(work_folder, database)

    def setup(self):
        # type: (...) -> Any
        super(MSim, self).setup()
        if not self._iniFileExists():
            self._createIniFile()

    def _makeRecords(self, line):
        # type: (str) -> Iterable[BuilderDiag]
        for match in self._stdout_message_scanner(line):  # type: ignore
            info = match.groupdict()

            self._logger.debug("Parsed dict: %s", repr(info))

            text = re.sub(
                r"\s*\((vcom|vlog)-\d+\)\s*", " ", info["error_message"]
            ).strip()

            error_code = None

            if ("vcom-" in line) or ("vlog" in line):
                error_code = re.findall(r"((?:vcom-|vlog-)\d+)", line)[0]

            filename = info.get("filename")
            line_number = info.get("line_number")
            column_number = info.get("column_number")

            severity = None
            if info.get("severity", None) in ("W", "e"):
                severity = DiagType.WARNING
            elif info.get("severity", None) in ("E", "e"):
                severity = DiagType.ERROR

            yield BuilderDiag(
                builder_name=self.builder_name,
                text=text,
                error_code=error_code,
                severity=severity,
                filename=None if filename is None else Path(filename),
                line_number=None if line_number is None else int(line_number) - 1,
                column_number=None if column_number is None else int(column_number) - 1,
            )

    def _checkEnvironment(self):
        stdout = runShellCommand(["vcom", "-version"])
        self._version = re.findall(r"(?<=vcom)\s+([\w\.]+)\s+(?=Compiler)", stdout[0])[
            0
        ]
        self._logger.debug(
            "vcom version string: '%s'. " "Version number is '%s'",
            stdout,
            self._version,
        )

    @staticmethod
    def isAvailable():
        try:
            runShellCommand(["vcom", "-version"])
            runShellCommand(["vlog", "-version"])
            return True
        except OSError:
            return False

    def _parseBuiltinLibraries(self):
        # type: (...) -> Any
        "Discovers libraries that exist regardless before we do anything"
        for line in runShellCommand(["vmap"]):
            for match in self._BuilderLibraryScanner.finditer(line):
                yield Identifier(match.groupdict()["library_name"], False)

    def _searchForRebuilds(self, line):
        rebuilds = []
        for match in self._iter_rebuild_units(line):
            mdict = match.groupdict()
            library_name = mdict["lib_name_0"] or mdict["lib_name_1"]
            unit_name = mdict["unit_name_0"] or mdict["unit_name_1"]
            if None not in (library_name, unit_name):
                rebuilds.append({"library_name": library_name, "unit_name": unit_name})
            else:  # pragma: no cover
                _msg = "Something wrong while parsing '%s'. " "Match is '%s'" % (
                    line,
                    mdict,
                )
                self._logger.error(_msg)
                assert 0, _msg

        return rebuilds

    def _buildSource(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> Iterable[str]
        filetype = FileType.fromPath(path)
        if filetype == FileType.vhdl:
            return self._buildVhdl(path, library, flags)
        if filetype in (FileType.verilog, FileType.systemverilog):
            return self._buildVerilog(path, library, flags)

        self._logger.error(  # pragma: no cover
            "Unknown file type %s for path '%s'", filetype, path
        )

        return ""  # Just to satisfy pylint

    def _getExtraFlags(self, path):
        # type: (Path) -> Iterable[str]
        """
        Gets extra flags configured for the specific language
        """
        self._logger.debug("Getting flags for %s", path)
        lang = FileType.fromPath(path)
        if lang is FileType.systemverilog:
            lang = FileType.verilog

        libs = []  # type: List[str]
        for library in self._added_libraries | self._external_libraries[lang]:
            libs = ["-L", library.name]
        for incdir in self._getIncludesForPath(path):
            libs += ["+incdir+" + incdir]
        return libs

    def _buildVhdl(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> Iterable[str]
        "Builds a VHDL file"
        assert isinstance(library, Identifier)
        cmd = [
            "vcom",
            "-modelsimini",
            self._modelsim_ini.name,
            "-quiet",
            "-work",
            p.join(self._work_folder, library.name),
        ]
        if flags:  # pragma: no cover
            cmd += flags
        cmd += [path.name]

        return runShellCommand(cmd)

    def _buildVerilog(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> Iterable[str]
        "Builds a Verilog/SystemVerilog file"
        cmd = [
            "vlog",
            "-modelsimini",
            self._modelsim_ini.name,
            "-quiet",
            "-work",
            p.join(self._work_folder, library.name),
        ]

        if FileType.fromPath(path) == FileType.systemverilog:
            cmd += ["-sv"]
        if flags:  # pragma: no cover
            cmd += flags

        cmd += self._getExtraFlags(path)
        cmd += [path.name]

        return runShellCommand(cmd)

    def _createLibrary(self, library):
        if p.exists(p.join(self._work_folder, library.name)):
            self._logger.debug("Path for library '%s' already exists", library)
            return
        self._mapLibrary(library)
        self._logger.debug("Added and mapped library '%s'", library)

    def _iniFileExists(self):
        # type: (...) -> bool
        """
        Checks if the modelsim.ini file exists at the expected location
        """
        return p.exists(self._modelsim_ini.abspath)

    def _createIniFile(self):
        # type: (...) -> Any
        """
        Adds a library to a non-existent ModelSim init file
        """
        if not p.exists(self._work_folder):  # pragma: no cover
            os.makedirs(self._work_folder)

        self._logger.debug("Creating modelsim.ini at '%s'", self._modelsim_ini)

        modelsim_env = os.environ.get("MODELSIM")
        if modelsim_env is not None:  # pragma: no cover
            self._logger.info(
                "MODELSIM environment variable set to %s, using "
                "this path as default modelsim.ini",
                modelsim_env,
            )
            # Copy the modelsim.ini as indicated by the MODELSIM environment
            # variable
            copyfile(modelsim_env, self._modelsim_ini.abspath)
        else:
            runShellCommand(["vmap", "-c"], cwd=self._work_folder)

    def deleteLibrary(self, library):
        "Deletes a library from ModelSim init file"
        if not p.exists(p.join(self._work_folder, library)):
            self._logger.warning("Library %s doesn't exists", library)
            return None
        return runShellCommand(
            ["vdel", "-modelsimini", self._modelsim_ini, "-lib", library, "-all"]
        )

    def _mapLibrary(self, library):
        # type: (Identifier) -> None
        """
        Adds a library to an existing ModelSim init file
        """
        runShellCommand(["vlib", p.join(self._work_folder, library.name)])

        runShellCommand(
            [
                "vmap",
                "-modelsimini",
                self._modelsim_ini.name,
                library.name,
                p.join(self._work_folder, library.name),
            ]
        )
