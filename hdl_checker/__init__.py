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
"""
hdl_checker provides a Python API between a VHDL project and some HDL
compilers to catch errors and warnings the compilers generate that can
be used to populate syntax checkers and linters of text editors. It
takes into account the sources dependencies when building so you don't
need to provide a source list ordered by hand.
"""
import os

from ._version import get_versions

from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.utils import ON_WINDOWS

__author__ = "Andre Souto (andre820@gmail.com)"
__license__ = "GPLv3"
__status__ = "Development"

__version__ = get_versions()["version"]
del get_versions

DEFAULT_PROJECT_FILE = os.environ.get(
    "HDL_CHECKER_DEFAULT_PROJECT_FILE",
    "_hdl_checker.config" if ON_WINDOWS else ".hdl_checker.config",
)

CACHE_NAME = os.environ.get("HDL_CHECKER_CACHE_NAME", "cache.json")
WORK_PATH = os.environ.get(
    "HDL_CHECKER_WORK_PATH", "_hdl_checker" if ON_WINDOWS else ".hdl_checker"
)
DEFAULT_LIBRARY = Identifier("default_library")
