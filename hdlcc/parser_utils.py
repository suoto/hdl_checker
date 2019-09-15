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
"Top of the hdlcc.parsers submodule"

# pylint: disable=useless-object-inheritance

import json
import logging
import os.path as p
#  import os.path as p
from multiprocessing.pool import ThreadPool as Pool
from typing import Any, Dict, Iterable, Set, Tuple, Type, Union

#  from .base_parser import BaseSourceFile
#  from .config_parser import ConfigParser, ProjectSourceSpec
#  from .elements.dependency_spec import DependencySpec, LocationList
#  from .elements.design_unit import (
#      DesignUnitType,
#      VerilogDesignUnit,
#      VhdlDesignUnit,
#      tAnyDesignUnit,
#  )
#  from .elements.identifier import Identifier
from .parsers.verilog_parser import VerilogParser
from .parsers.vhdl_parser import VhdlParser

from hdlcc.path import Path
from hdlcc.types import FileType

_logger = logging.getLogger(__name__)

tSourceFile = Union[VhdlParser, VerilogParser]


def _isVhdl(path):  # pragma: no cover
    "Uses the file extension to check if the given path is a VHDL file"
    if path.lower().endswith(".vhd"):
        return True
    if path.lower().endswith(".vhdl"):
        return True
    return False


def _isVerilog(path):  # pragma: no cover
    """Uses the file extension to check if the given path is a Verilog
    or SystemVerilog file"""
    if path.lower().endswith(".v"):
        return True
    if path.lower().endswith(".sv"):
        return True
    return False


PARSERS = {
    FileType.vhdl: VhdlParser,
    FileType.verilog: VerilogParser,
    FileType.systemverilog: VerilogParser,
}  # type: Dict[FileType, Type[Union[VhdlParser, VerilogParser]]]


def getSourceParserFromPath(path):  # type: (Path) -> tSourceFile
    """
    Returns either a VhdlParser or VerilogParser based on the path's file
    extension
    """
    return PARSERS[FileType.fromPath(path)](path)


def getSourceFileObjects(kwargs_list, workers=None):
    """
    Gets source file objects by applying each item on kwargs_list as
    kwargs on the source parser class. Uses kwargs['filename'] to
    determine if the source is VHDL or Verilog/SystemVerilog
    """
    pool = Pool(workers)
    async_results = []

    for kwargs in kwargs_list:
        if _isVhdl(kwargs["filename"]):
            cls = VhdlParser
        else:
            cls = VerilogParser
        async_results += [pool.apply_async(cls, kwds=kwargs)]

    pool.close()
    pool.join()
    results = [x.get() for x in async_results]

    return results


def _makeAbsoluteIfNeeded(root, paths):
    # type: (str, Iterable[str]) -> Iterable[str]
    for path in paths:
        if p.isabs(path):
            yield path
        else:
            yield p.join(root, path)


def getIncludedConfigs(base_config, root_dir="."):
    # type: (Dict[str, Any], str) -> Iterable[Tuple[str, Dict[str, Any]]]
    "Returns configuration contents of included files"
    # Copy the dict to avoid messing up with the caller's env
    config = base_config.copy()

    # Will search for inclusion clauses recursivelly but we need to keep
    # track of infinite loops
    checked_paths = set()  # type: Set[str]

    paths = set(_makeAbsoluteIfNeeded(root_dir, config.pop("include", ())))

    while paths:
        path = paths.pop()
        checked_paths.add(path)

        if not p.exists(path):
            _logger.warning("Skipping included path '%s' (no such file)", path)
            continue

        # Load the config from the file
        try:
            config = json.load(open(path, "r"))
        except json.decoder.JSONDecodeError:
            _logger.warning("Failed to decode file %s", path)
            continue

        extracted_paths = set(_makeAbsoluteIfNeeded(path, config.pop("include", ())))
        # Add new paths to the set so they get parsed as well
        paths |= extracted_paths - checked_paths

        yield path, config
