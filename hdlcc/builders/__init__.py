# This file is part of HDL Code Checker.
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

__all__ = ['MSim', 'XVHDL', 'Fallback', 'GHDL']

AVAILABLE_BUILDERS = MSim, XVHDL, Fallback, GHDL

