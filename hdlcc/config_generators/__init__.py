# This file is part of HDL Code Checker.
#
# Copyright (c) 2015-2019 Andre Souto
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

from .simple_finder import SimpleFinder

_logger = logging.getLogger(__name__)

def getGeneratorByName(name):
    "Returns the builder class given a string name"
    # Check if the builder selected is implemented and create the
    # builder attribute
    return {'SimpleFinder': SimpleFinder}.get(name, SimpleFinder)

__all__ = ['SimpleFinder', ]
