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
"Top of the hdl_checker.parsers submodule"

import json
import logging
import os.path as p
from glob import iglob as _glob
from typing import Any, Dict, Iterable, NamedTuple, Optional, Set, Tuple, Type, Union

import six

from .parsers.verilog_parser import VerilogParser
from .parsers.vhdl_parser import VhdlParser

from hdl_checker.exceptions import UnknownTypeExtension
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, BuildFlagScope, FileType

_logger = logging.getLogger(__name__)

tSourceFile = Union[VhdlParser, VerilogParser]

if six.PY3:
    JSONDecodeError = (  # pylint: disable=invalid-name
        json.decoder.JSONDecodeError  # pylint: disable=no-member
    )

    # Python 2 iglob does not take recursive argument
    def glob(pathname):
        "Alias for glob.iglob(pathname, recursive=True)"
        return _glob(pathname, recursive=True)


else:
    JSONDecodeError = ValueError

    def glob(pathname):
        "Alias for glob.iglob(pathname)"
        return _glob(pathname)


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
    "Makes paths absolute by prepending root if needed"
    for path in paths:
        if p.isabs(path):
            yield path
        else:
            yield p.join(root, path)


def getIncludedConfigs(search_paths, root_dir="."):
    # type: (Dict[str, Any], str) -> Iterable[Tuple[str, Dict[str, Any]]]
    "Returns configuration contents of included files"
    # Copy the dict to avoid messing up with the caller's env
    #  config = root_config.copy()

    # Will search for inclusion clauses recursivelly but we need to keep
    # track of infinite loops
    checked_paths = set()  # type: Set[str]

    paths = set(_makeAbsoluteIfNeeded(root_dir, search_paths))

    while paths:
        path = paths.pop()
        checked_paths.add(path)

        if not p.exists(path):
            _logger.warning("Skipping included path '%s' (no such file)", path)
            continue

        # Load the config from the file
        try:
            config = json.load(open(path, "r"))
        except JSONDecodeError:
            _logger.warning("Failed to decode file %s", path)
            continue

        extracted_paths = set(
            _makeAbsoluteIfNeeded(p.dirname(path), config.pop("include", ()))
        )
        # Add new paths to the set so they get parsed as well
        paths |= extracted_paths - checked_paths

        yield p.dirname(path), config


class JsonSourceEntry(
    NamedTuple(
        "JsonSourceEntry",
        (("path_expr", str), ("library", Optional[str]), ("flags", str)),
    )
):
    """
    Converts different methods of representing a source on the JSON file to a
    saner named tuple
    """

    @classmethod
    def make(cls, iterable):  # pylint: disable=arguments-differ
        # type: (...) -> Any
        """
        Creates a JsonSourceEntry from all supported formats:
            - str
            - [str, {"library": "<library_name>", "flags": BuildFlags}]
        """
        path = iterable
        info = {}  # type: Dict[str, Union[None, str, BuildFlags]]

        if not isinstance(path, six.string_types):
            path = iterable[0]
            info = iterable[1]

        library = info.get("library", None)
        flags = info.get("flags", tuple())

        return super(JsonSourceEntry, cls)._make([path, library, flags])


SourceEntry = NamedTuple(
    "SourceEntry",
    (
        ("path", Path),
        ("library", Optional[str]),
        ("single_flags", BuildFlags),
        ("dependencies_flags", BuildFlags),
    ),
)


def flattenConfig(root_config, root_path):
    # type: (Dict[str, Any], str) -> Iterable[SourceEntry]
    """
    Expands the given root config and also recursively expands included JSON
    files as well
    """
    # Extract included paths and yield those results first
    include_paths = root_config.pop("include", ())
    for config_path, config in getIncludedConfigs(include_paths, root_path):
        for entry in _expand(config, config_path):
            yield entry

    # Extract sources form the root config last so these are the values that
    # might eventually prevail
    for entry in _expand(root_config, root_path):
        yield entry


def _expand(config, ref_path):
    # type: (Dict[str, Any], str) -> Iterable[SourceEntry]
    """
    Expands the sources defined in the config dict into a list of tuples
    """

    flags = {}

    for filetype in FileType:
        filetype_cfg = config.pop(filetype.value, {}).pop("flags", {})
        flags[filetype] = (
            filetype_cfg.get(BuildFlagScope.single.value, ()),
            filetype_cfg.get(BuildFlagScope.dependencies.value, ()),
            filetype_cfg.get(BuildFlagScope.all.value, ()),
        )

    for entry in config.pop("sources", ()):
        source = JsonSourceEntry.make(entry)
        path_expr = (
            source.path_expr
            if p.isabs(source.path_expr)
            else p.join(ref_path, source.path_expr)
        )

        for _path in glob(path_expr):
            path = Path(_path, ref_path)

            try:
                filetype = FileType.fromPath(path)
            except UnknownTypeExtension:
                _logger.warning("Won't include non RTL file '%s'", path)
                continue

            single_flags = flags[filetype][0]
            dependencies_flags = flags[filetype][1]
            global_flags = flags[filetype][2]

            yield SourceEntry(
                path,
                source.library,
                tuple(global_flags) + tuple(single_flags) + tuple(source.flags),
                tuple(global_flags) + tuple(dependencies_flags),
            )
