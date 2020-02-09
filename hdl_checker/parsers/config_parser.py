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
"Configuration file parser"

# pylint: disable=useless-object-inheritance

import logging
import os.path as p
import re
from glob import glob
from threading import RLock
from typing import Any, Dict, Iterable, List, Tuple, Union

from hdl_checker import exceptions
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, BuildFlagScope, FileType

# pylint: disable=invalid-name
_splitAtWhitespaces = re.compile(r"\s+").split
_replaceCfgComments = re.compile(r"(\s*#.*|\n)").sub
_configFileScan = re.compile(
    "|".join(
        [
            r"^\s*(?P<parameter>\w+)\s*(\[(?P<parm_lang>vhdl|verilog|systemverilog)\]|\s)*=\s*(?P<value>.+)\s*$",
            r"^\s*(?P<lang>(vhdl|verilog|systemverilog))\s+"
            r"(?P<library>\w+)\s+"
            r"(?P<path>[^\s]+)\s*(?P<flags>.*)\s*",
        ]
    ),
    flags=re.I,
).finditer
# pylint: enable=invalid-name


def _extractSet(entry):  # type: (str) -> BuildFlags
    """
    Extract a list by splitting a string at whitespaces, removing
    empty values caused by leading/trailing/multiple whitespaces
    """
    string = str(entry).strip()
    # Return an empty list if the string is empty
    if not string:
        return ()
    return tuple(_splitAtWhitespaces(string))


class ConfigParser(object):
    """
    Configuration info provider
    """

    _list_parms = {
        "single_build_flags": BuildFlagScope.single,
        "global_build_flags": BuildFlagScope.all,
        "dependencies_build_flags": BuildFlagScope.dependencies,
    }

    _single_value_parms = ("builder",)
    _deprecated_parameters = ("target_dir",)

    _logger = logging.getLogger(__name__ + ".ConfigParser")

    def __init__(self, filename):  # type: (Path) -> None
        self._logger.debug("Creating config parser for filename '%s'", filename)

        self._parms = {"builder": None}  # type: Dict[str, Union[str, None]]

        self._flags = {
            FileType.vhdl: {
                BuildFlagScope.single: (),
                BuildFlagScope.all: (),
                BuildFlagScope.dependencies: (),
            },
            FileType.verilog: {
                BuildFlagScope.single: (),
                BuildFlagScope.all: (),
                BuildFlagScope.dependencies: (),
            },
            FileType.systemverilog: {
                BuildFlagScope.single: (),
                BuildFlagScope.all: (),
                BuildFlagScope.dependencies: (),
            },
        }  # type: Dict[FileType, Dict[BuildFlagScope, BuildFlags] ]

        self._sources = []  # type: List[Tuple[str, str, BuildFlags]]

        self.filename = filename

        self._timestamp = 0.0
        self._parse_lock = RLock()

    def _shouldParse(self):  # type: () -> bool
        """
        Checks if we should parse the configuration file
        """
        return self.filename.mtime > self._timestamp

    def _updateTimestamp(self):
        # type: (...) -> Any
        """
        Updates our timestamp with the configuration file
        """
        self._timestamp = self.filename.mtime

    def isParsing(self):  # type: () -> bool
        "Checks if parsing is ongoing in another thread"
        locked = not self._parse_lock.acquire(False)
        if not locked:
            self._parse_lock.release()
        return locked

    def _parseIfNeeded(self):
        # type: () -> None
        """
        Locks accesses to parsed attributes and parses the configuration file
        """
        with self._parse_lock:
            if self._shouldParse():
                self._parse()

    def _parse(self):  # type: () -> None
        """
        Parse the configuration file without any previous checking
        """
        self._logger.info("Parsing '%s'", self.filename)
        self._updateTimestamp()
        self._sources = []
        for _line in open(self.filename.name, mode="rb").readlines():
            line = _replaceCfgComments("", _line.decode(errors="ignore"))
            self._parseLine(line)

    def _parseLine(self, line):  # type: (str) -> None
        """
        Parses a line a calls the appropriate extraction methods
        """
        for match in _configFileScan(line):
            groupdict = match.groupdict()
            self._logger.debug("match: '%s'", groupdict)
            if groupdict["parameter"] is not None:
                self._handleParsedParameter(
                    groupdict["parameter"], groupdict["parm_lang"], groupdict["value"]
                )
            else:
                for source_path in self._getSourcePaths(groupdict["path"]):
                    self._sources.append(
                        (
                            source_path,
                            {
                                "library": groupdict["library"],
                                "flags": _extractSet(groupdict["flags"]),
                            },
                        )
                    )

    def _handleParsedParameter(self, parameter, lang, value):
        # type: (str, str, str) -> None
        """
        Handles a parsed line that sets a parameter
        """
        self._logger.debug(
            "Found parameter '%s' for '%s' with value '%s'", parameter, lang, value
        )
        if parameter in self._deprecated_parameters:
            self._logger.debug("Ignoring deprecated parameter '%s'", parameter)
        elif parameter in self._single_value_parms:
            self._logger.debug("Handling '%s' as a single value", parameter)
            self._parms[parameter] = value
        elif parameter in self._list_parms:
            self._logger.debug("Handling '%s' as a list of values", parameter)
            self._flags[FileType(lang)][self._list_parms[parameter]] = _extractSet(
                value
            )
        else:
            raise exceptions.UnknownParameterError(parameter)

    def _getSourcePaths(self, path):  # type: (str) -> Iterable[str]
        """
        Normalizes and handles absolute/relative paths
        """
        source_path = p.normpath(p.expanduser(path))
        # If the path to the source file was not absolute, we assume
        # it was relative to the config file base path
        if not p.isabs(source_path):
            fname_base_dir = p.dirname(self.filename.abspath)
            source_path = p.join(fname_base_dir, source_path)

        return glob(source_path) or [source_path]

    def parse(self):
        # type: (...) -> Dict[Any, Any]
        """
        Parses the file if it hasn't been parsed before or if the config file
        has been changed
        """
        self._parseIfNeeded()
        data = {"sources": self._sources}  # type: Dict[Any, Any]

        builder_name = self._parms.get("builder", None)
        if builder_name is not None:
            data["builder"] = builder_name

        for filetype, flags in self._flags.items():
            flags_dict = {}
            for scope in (
                x for x in BuildFlagScope if x is not BuildFlagScope.source_specific
            ):
                flags_dict[scope.value] = flags[scope]
            data.update({filetype.name: {"flags": flags_dict}})

        return data
