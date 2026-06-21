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
"Base class that implements the base builder flow"

import logging
import os.path as p
import subprocess
import sys
from contextlib import contextmanager
from enum import Enum
from tempfile import mkdtemp
from typing import Iterable  # pylint: disable=unused-import

from hdl_checker.parser_utils import findRtlSourcesByPath
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, FileType
from hdl_checker.utils import removeDirIfExists

from .builders.fallback import Fallback
from .builders.ghdl import GHDL
from .builders.msim import MSim

_logger = logging.getLogger(__name__)


def _find_vunit_site_packages() -> str | None:
    """
    Try to locate the site-packages directory containing vunit by querying the
    python interpreter in PATH.  This allows hdl_checker (e.g. installed via
    pipx) to find vunit installed in the user's active venv or system Python.
    """
    for python in ("python", "python3"):
        try:
            result = subprocess.run(
                [python, "-c",
                 "import vunit, os; print(os.path.dirname(os.path.dirname(vunit.__file__)))"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError) as exc:
            _logger.info("VUnit not, got exception: %s", exc)
            continue
    return None


_vunit_pkg_dir: str | None = None

try:
    # __file__ is str | None (None for built-in/namespace packages); vunit is
    # always a file-backed package so the fallback to "" is never reached, but
    # it narrows the type to str so p.dirname is satisfied without a type: ignore.
    import vunit as _vunit  # type: ignore[import-not-found]  # pylint: disable=import-error
    from vunit import (
        VUnit as VUnit_VHDL,  # type: ignore[import-not-found]  # pylint: disable=import-error
    )
    from vunit.verilog import (
        VUnit as VUnit_Verilog,  # type: ignore  # pylint: disable=import-error
    )
    _vunit_pkg_dir = p.dirname(_vunit.__file__ or "")
    HAS_VUNIT = True
except ImportError:  # pragma: no cover
    _vunit_sp = _find_vunit_site_packages()
    if _vunit_sp and _vunit_sp not in sys.path:
        sys.path.append(_vunit_sp)
        try:
            import vunit as _vunit  # type: ignore[import-not-found]  # pylint: disable=import-error
            from vunit import (
                VUnit as VUnit_VHDL,  # type: ignore[import-not-found]  # pylint: disable=import-error
            )
            from vunit.verilog import (
                VUnit as VUnit_Verilog,  # type: ignore  # pylint: disable=import-error
            )
            _vunit_pkg_dir = p.dirname(_vunit.__file__ or "")
            HAS_VUNIT = True
            _logger.debug("VUnit found in external environment: %s", _vunit_pkg_dir)
        except ImportError as exc:
            _logger.warning("No VUnit support: %s", exc)
            HAS_VUNIT = False
    else:
        HAS_VUNIT = False

AnyValidBuilder = MSim | GHDL
AnyBuilder = AnyValidBuilder | Fallback


class BuilderName(Enum):
    """
    Supported tools
    """

    msim = "msim"
    ghdl = "ghdl"
    fallback = "fallback"


def getBuilderByName(name: str):
    "Returns the builder class given a string name"
    return {
        "msim": MSim,
        "ghdl": GHDL,
    }.get(name, Fallback)


def getPreferredBuilder():
    """
    Returns a generator with the names of builders that are actually working
    """
    for builder_class in AVAILABLE_BUILDERS:
        if builder_class is Fallback:
            continue
        if builder_class.isAvailable():
            _logger.debug("Builder %s worked", builder_class.builder_name)
            return builder_class

    # If no compiler worked, use fallback
    return Fallback


def foundVunit() -> bool:
    """
    Checks if our env has VUnit installed
    """
    return HAS_VUNIT


_VUNIT_FLAGS: dict[BuilderName, dict[str, tuple[str, ...]]] = {
    BuilderName.msim: {"93": ("-93",), "2002": ("-2002",), "2008": ("-2008",)},
    BuilderName.ghdl: {
        "93": ("--std=93c",),
        "2002": ("--std=02",),
        "2008": ("--std=08",),
    },
}


def _isHeader(path: Path) -> bool:
    ext = path.name.split(".")[-1].lower()
    return ext in ("vh", "svh")


def getVunitSources(builder: AnyValidBuilder) -> Iterable[tuple[Path, str | None, BuildFlags]]:
    "Gets VUnit sources according to the file types supported by builder"
    if not foundVunit():
        _logger.info("VUnit not found, VUnit files will not be included")
        return

    _logger.debug("VUnit installation found")

    sources: list = []

    # Prefer VHDL VUnit
    if FileType.vhdl in builder.file_types:
        sources += _getSourcesFromVUnitModule(VUnit_VHDL)  # type: ignore[possibly-undefined]
        _logger.debug("Added VUnit VHDL files")

    if FileType.systemverilog in builder.file_types:
        _logger.debug("Builder supports Verilog, adding VUnit Verilog files")
        builder.addExternalLibrary(FileType.verilog, Identifier("vunit_lib", False))
        sources += _getSourcesFromVUnitModule(VUnit_Verilog)  # type: ignore[possibly-undefined]

    if not sources:
        _logger.info("Vunit found but no file types are supported by %s", builder)
        return

    for source in sources:
        path = p.abspath(source.name)
        library = source.library.name

        # Get extra flags for building VUnit sources
        try:
            flags = _VUNIT_FLAGS[BuilderName(builder.builder_name)][
                source.vhdl_standard
            ]
        except KeyError:
            flags = tuple()

        yield Path(path), library, flags

    if FileType.systemverilog in builder.file_types:
        for path in findRtlSourcesByPath(Path(_vunit_pkg_dir)):  # type: ignore[arg-type]
            if _isHeader(path):
                yield Path(path), None, ()


@contextmanager
def _makeTemporaryDir(*args, **kwargs):
    """
    Context manager that wraps tempfile.mkdtemp but deletes the directory
    afterwards
    """
    path = mkdtemp(*args, **kwargs)
    yield path
    removeDirIfExists(path)


def _getSourcesFromVUnitModule(vunit_module):
    """
    Creates a temporary VUnit project given a VUnit module and return a list of
    its files
    """
    with _makeTemporaryDir() as output_path:

        # Create a dummy VUnit project to get info on its sources
        vunit_project = vunit_module.from_argv(["--output-path", output_path])

        # OSVVM is always avilable
        vunit_project.add_osvvm()
        # Communication library and array utility library are only
        # available on VHDL 2008
        if vunit_project.vhdl_standard == "2008":
            vunit_project.add_com()
            vunit_project.add_array_util()

        return list(vunit_project.get_source_files())


__all__ = ["MSim", "GHDL", "Fallback"]

# This holds the builders in order of preference
AVAILABLE_BUILDERS = MSim, GHDL, Fallback
