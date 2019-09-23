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
"Base class that implements the base builder flow"

import logging
import os.path as p
from enum import Enum
from tempfile import mkdtemp
from typing import Dict, Iterable, Tuple, Union  # pylint: disable=unused-import

from .builders.fallback import Fallback
from .builders.ghdl import GHDL
from .builders.msim import MSim
from .builders.xvhdl import XVHDL

from hdlcc.path import Path  # pylint: disable=unused-import
from hdlcc.types import BuildFlags, FileType
from hdlcc.utils import removeDirIfExists

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
        _logger.info("Using Fallback builder")
        builder = Fallback

    return builder


def getWorkingBuilders():
    """
    Returns a generator with the names of builders that are actually working
    """
    for builder_class in AVAILABLE_BUILDERS:
        if builder_class.builder_name == "fallback":
            continue
        if builder_class.isAvailable():
            _logger.debug("Builder %s worked", builder_class.builder_name)
            yield builder_class.builder_name
        else:
            _logger.debug("Builder %s failed", builder_class.builder_name)


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

    _logger.info("VUnit installation found")

    # Prefer VHDL VUnit
    if FileType.vhdl in builder.file_types:
        from vunit import VUnit  # pylint: disable=import-error
    elif FileType.systemverilog in builder.file_types:
        from vunit.verilog import (  # type: ignore # pylint: disable=import-error
            VUnit,
        )

        _logger.debug("Builder supports Verilog, using vunit.verilog.VUnit")
        builder.addExternalLibrary("verilog", "vunit_lib")
        builder.addIncludePath(
            "verilog", p.join(p.dirname(vunit.__file__), "verilog", "include")
        )
    else:  # pragma: no cover
        _logger.warning("Vunit found but no file types are supported by %s", builder)
        return

    output_path = mkdtemp()

    # Create a dummy VUnit project to get info on its sources
    vunit_project = VUnit.from_argv(["--output-path", output_path])

    flags = tuple()  # type: BuildFlags
    # Get extra flags for building VUnit sources
    try:
        flags = _VUNIT_FLAGS[BuilderName(builder.builder_name)][
            vunit_project.vhdl_standard
        ]
    except KeyError:
        pass

    # OSVVM is always avilable
    vunit_project.add_osvvm()
    # Communication library and array utility library are only
    # available on VHDL 2008
    if vunit_project.vhdl_standard == "2008":
        vunit_project.add_com()
        vunit_project.add_array_util()

    for vunit_source_obj in vunit_project.get_compile_order():
        path = p.abspath(vunit_source_obj.name)
        library = vunit_source_obj.library.name
        yield Path(path), library, flags

    removeDirIfExists(output_path)


__all__ = ["MSim", "XVHDL", "GHDL", "Fallback"]

AVAILABLE_BUILDERS = MSim, XVHDL, GHDL, Fallback
