# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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

from .fallback import Fallback
from .ghdl import GHDL
from .msim import MSim
from .xvhdl import XVHDL

_logger = logging.getLogger(__name__)

def getBuilderByName(name):
    "Returns the builder class given a string name"
    # Check if the builder selected is implemented and create the
    # builder attribute
    if name == 'msim':
        builder = MSim
    elif name == 'xvhdl':
        builder = XVHDL
    elif name == 'ghdl':
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
        if builder_class.builder_name == 'fallback':
            continue
        if builder_class.isAvailable():
            _logger.debug("Builder %s worked", builder_class.builder_name)
            yield builder_class.builder_name
        else:
            _logger.debug("Builder %s failed", builder_class.builder_name)

__all__ = ['MSim', 'XVHDL', 'GHDL', 'Fallback']

AVAILABLE_BUILDERS = MSim, XVHDL, GHDL, Fallback

