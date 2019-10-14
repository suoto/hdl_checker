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
from contextlib import contextmanager
from enum import Enum
from tempfile import mkdtemp
from typing import (  # pylint: disable=unused-import
    Any,
    Dict,
    Iterable,
    List,
    Tuple,
    Union,
)

from .builders.fallback import Fallback
from .builders.ghdl import GHDL
from .builders.msim import MSim
from .builders.xvhdl import XVHDL

from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, FileType
from hdl_checker.utils import removeDirIfExists

_logger = logging.getLogger(__name__)

AnyValidBuilder = Union[MSim, XVHDL, GHDL]
AnyBuilder = Union[AnyValidBuilder, Fallback]


class BuilderName(Enum):
    """
    Supported tools
    """

    msim = MSim.builder_name
    xvhdl = XVHDL.builder_name
    ghdl = GHDL.builder_name
    fallback = Fallback.builder_name


def getBuilderByName(name):
    "Returns the builder class given a string name"
    # Check if the builder selected is implemented and create the
    # builder attribute
    if name == "msim":
        builder = MSim
    elif name == "xvhdl":
        builder = XVHDL
    elif name == "ghdl":
        builder = GHDL
    else:
        builder = Fallback

    return builder


def getWorkingBuilders():
    """
    Returns a generator with the names of builders that are actually working
    """
    for builder_class in AVAILABLE_BUILDERS:
        if builder_class is Fallback:
            continue
        if builder_class.isAvailable():
            _logger.debug("Builder %s worked", builder_class.builder_name)
            yield builder_class


def foundVunit():  # type: () -> bool
    """
    Checks if our env has VUnit installed
    """
    try:
        import vunit  # type: ignore pylint: disable=unused-import

        return True
    except ImportError:  # pragma: no cover
        pass

    return False


_VUNIT_FLAGS = {
    BuilderName.msim: {"93": ("-93",), "2002": ("-2002",), "2008": ("-2008",)},
    BuilderName.ghdl: {
        "93": ("--std=93c",),
        "2002": ("--std=02",),
        "2008": ("--std=08",),
    },
}  # type: Dict[BuilderName, Dict[str, BuildFlags]]


def getVunitSources(builder):
    # type: (AnyValidBuilder) -> Iterable[Tuple[Path, str, BuildFlags]]
    "Foo bar"
    if not foundVunit():  # or self._builder_name == BuilderName.fallback:
        return

    import vunit  # pylint: disable=import-error

    logging.getLogger("vunit").setLevel(logging.ERROR)

    _logger.debug("VUnit installation found")

    sources = []  # type: List[Any]

    # Prefer VHDL VUnit
    if FileType.vhdl in builder.file_types:
        from vunit import VUnit  # pylint: disable=import-error

        sources += _getSourcesFromVUnitModule(VUnit)
        _logger.debug("Added VUnit VHDL files")

    if FileType.systemverilog in builder.file_types:
        from vunit.verilog import (  # type: ignore # pylint: disable=import-error
            VUnit,
        )

        _logger.debug("Builder supports Verilog, adding VUnit Verilog files")
        builder.addExternalLibrary(FileType.verilog, Identifier("vunit_lib", False))
        builder.addIncludePath(
            FileType.verilog, p.join(p.dirname(vunit.__file__), "verilog", "include")
        )
        sources += _getSourcesFromVUnitModule(VUnit)

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


@contextmanager
def _makeTemporaryDir(*args, **kwargs):
    """
    Context manager that wraps tempfile.mkdtemp but deletes the directory
    afterwards
    """
    path = mkdtemp(*args, **kwargs)
    yield path
    removeDirIfExists(path)


def _getSourcesFromVUnitModule(vunit):
    """
    Creates a temporary VUnit project given a VUnit module and return a list of
    its files
    """
    with _makeTemporaryDir() as output_path:

        # Create a dummy VUnit project to get info on its sources
        vunit_project = vunit.from_argv(["--output-path", output_path])

        # OSVVM is always avilable
        vunit_project.add_osvvm()
        # Communication library and array utility library are only
        # available on VHDL 2008
        if vunit_project.vhdl_standard == "2008":
            vunit_project.add_com()
            vunit_project.add_array_util()

        return list(vunit_project.get_source_files())


__all__ = ["MSim", "XVHDL", "GHDL", "Fallback"]

AVAILABLE_BUILDERS = MSim, XVHDL, GHDL, Fallback
