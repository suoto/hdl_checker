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
import os
import os.path as p
import subprocess as subp
from glob import iglob as glob
from typing import Any, Dict, Iterable, NamedTuple, Optional, Set, Tuple, Type, Union

import six

from .parsers.verilog_parser import VerilogParser
from .parsers.vhdl_parser import VhdlParser

from hdl_checker import DEFAULT_PROJECT_FILE
from hdl_checker.exceptions import UnknownTypeExtension
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, BuildFlagScope, FileType
from hdl_checker.utils import ON_WINDOWS, isFileReadable, toBytes

_logger = logging.getLogger(__name__)

PARSERS = {
    FileType.vhdl: VhdlParser,
    FileType.verilog: VerilogParser,
    FileType.systemverilog: VerilogParser,
}  # type: Dict[FileType, Type[Union[VhdlParser, VerilogParser]]]


def getSourceParserFromPath(path):  # type: (Path) -> Union[VhdlParser, VerilogParser]
    """
    Returns either a VhdlParser or VerilogParser based on the path's file
    extension
    """
    return PARSERS[FileType.fromPath(path)](path)


def _makeAbsoluteIfNeeded(root, paths):
    # type: (str, Iterable[str]) -> Iterable[str]
    "Makes paths absolute by prepending root if needed"
    for path in paths:
        if p.isabs(path):
            yield path
        else:
            yield p.join(root, path)


def getIncludedConfigs(search_paths, root_dir="."):
    # type: (Iterable[str], str) -> Iterable[Tuple[str, Dict[str, Any]]]
    "Returns configuration contents of included files"
    # Copy the dict to avoid messing up with the caller's env

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

        use_json = False

        # Cover cases where 'path' is an existing file
        if not p.isdir(path):
            use_json = True

        # Cover cases where 'path' is a folder that has a file named
        # DEFAULT_PROJECT_FILE inside
        if p.isdir(path) and p.exists(p.join(path, DEFAULT_PROJECT_FILE)):
            path = p.join(path, DEFAULT_PROJECT_FILE)
            _logger.debug("Path is a folder and %s exists, using it", path)
            use_json = True

        if use_json:
            # Load the config from the file
            try:
                config = json.load(open(path, "r"))
            except json.decoder.JSONDecodeError:
                _logger.warning("Failed to decode file %s", path)
                continue

            extracted_paths = set(
                _makeAbsoluteIfNeeded(p.dirname(path), config.pop("include", ()))
            )
            # Add new paths to the set so they get parsed as well
            paths |= extracted_paths - checked_paths

            yield p.dirname(path), config
        else:
            # If the path pointed to a folder, search it for sources
            yield path, {"sources": tuple(findRtlSourcesByPath(Path(path)))}


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
            - {"path": str,               <- Mandatory
               "library": <library_name>, <- Optional
               "flags": <BuildFlags>,     <- Optional
              }
        """
        path = iterable
        info = {}  # type: Dict[str, Union[None, str, BuildFlags]]

        # Support both
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
        ("source_specific_flags", BuildFlags),
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

    sources = config.pop("sources", None)

    # If no sources were defined, search ref_path
    if sources is None:
        _logger.debug("No sources found, will search %s", ref_path)
        sources = (x.name for x in findRtlSourcesByPath(Path(ref_path)))

    for entry in sources:
        source = JsonSourceEntry.make(entry)
        path_expr = (
            source.path_expr
            if p.isabs(source.path_expr)
            else p.join(ref_path, source.path_expr)
        )

        for _path in glob(path_expr, recursive=True):
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
                tuple(source.flags),
                tuple(global_flags) + tuple(single_flags),
                tuple(global_flags) + tuple(dependencies_flags),
            )


def findRtlSourcesByPath(path):
    # type: (Path) -> Iterable[Path]
    """
    Finds RTL sources (files with extensions within FileType enum) inside
    <path>
    """
    for dirpath, _, filenames in os.walk(path.name):
        for filename in filenames:
            full_path = Path(p.join(dirpath, filename))

            if not p.isfile(full_path.name):
                continue

            try:
                # FileType.fromPath will fail if the file's extension is not
                # valid (one of '.vhd', '.vhdl', '.v', '.vh', '.sv',
                # '.svh')
                FileType.fromPath(full_path)
            except UnknownTypeExtension:
                continue

            if isFileReadable(full_path.name):
                yield full_path


def isGitRepo(path):
    # type: (Path) -> bool
    """
    Checks if path is a git repository by checking if 'git -C path rev-parse
    --show-toplevel' returns an existing path
    """
    cmd = ("git", "-C", path.abspath, "rev-parse", "--show-toplevel")

    try:
        return p.exists(subp.check_output(cmd, stderr=subp.STDOUT).decode().strip())
    except (subp.CalledProcessError, FileNotFoundError):
        return False


def _gitLsFiles(path_to_repo, recurse_submodules=False):
    # type: (Path, bool) -> Iterable[Path]
    "Lists files from a git repository"
    cmd = ["git", "-C", path_to_repo.abspath, "ls-files"]
    if recurse_submodules:
        cmd += ["--recurse-submodules"]

    for line in subp.check_output(cmd, stderr=subp.STDOUT).decode().split("\n"):
        if not line:
            continue
        yield Path(line, path_to_repo.abspath)


def _filterGitIgnoredPathsOnWin(path_to_repo, paths):
    # type: (Path, Iterable[Path]) -> Iterable[Path]
    """
    Filters out paths that are ignored by git; paths outside the repo are kept.
    Uses a multiple calls to 'git check-ignore' and checks if the output is
    empty (ignored paths will be echoed). The command will return non zero exit
    code for paths outside the repo or if <path_to_repo> is not actually a git
    repo, in which cases paths will be included.
    """
    files = _gitLsFiles(path_to_repo, recurse_submodules=True)
    base_cmd = ("git", "-C", path_to_repo.abspath, "check-ignore")

    for path in paths:
        # If the file was found on git ls-files, it is part of the repo and
        # there's no need to check if any git ignore rules match
        if path in files:
            yield path
            continue

        cmd = base_cmd + (str(path),)
        try:
            if not subp.check_output(cmd, stderr=subp.STDOUT):
                yield path
        except subp.CalledProcessError:
            yield path


def _filterGitIgnoredPathsOnUnix(path_to_repo, paths):
    # type: (Path, Iterable[Path]) -> Iterable[Path]
    """
    Filters out paths that are ignored by git; paths outside the repo are kept.
    Uses a 'git check-ignore --stdin' and writes <paths> iteratively to avoid
    piping to the OS all the time
    """
    _logger.debug("Filtering git ignored files from %s", path_to_repo)

    cmd = (
        "git",
        "-C",
        path_to_repo.abspath,
        "check-ignore",
        "--verbose",
        "--non-matching",
        "--stdin",
    )

    proc = None

    for path in paths:
        # Besides the first iteration, the process also needs to be recreated
        # whenever it has died
        if proc is None:
            proc = subp.Popen(cmd, stdin=subp.PIPE, stdout=subp.PIPE, stderr=subp.PIPE)

        proc.stdin.write(toBytes(str(path.abspath) + "\n"))
        # Flush so that data makes to the process
        proc.stdin.flush()

        if proc.stdout.readline().decode().startswith("::"):
            yield path

        # proc will die whenever we write a path that's outside the repo.
        # Because this method aims to filter *out* ignored files and files
        # outside the repo aren't subject to this filter, we'll include them
        if proc.poll() is not None:
            yield path
            # Deallocate the process (hopefully this won't leave a zombie
            # process behind)
            del proc
            proc = None


def filterGitIgnoredPaths(path_to_repo, paths):
    # type: (Path, Iterable[Path]) -> Iterable[Path]
    """
    Filters out paths that are ignored by git; paths outside the repo are kept.
    """
    files = set(_gitLsFiles(path_to_repo, recurse_submodules=True))
    paths = set(paths)

    # Files found on git ls-files are part of the repo, no need to check if any
    # git ignore rules match
    for path in files.intersection(paths):
        yield path

    func = _filterGitIgnoredPathsOnWin if ON_WINDOWS else _filterGitIgnoredPathsOnUnix

    for path in func(path_to_repo, paths - files):
        yield path
