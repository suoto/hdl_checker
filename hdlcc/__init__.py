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
"""hdlcc provides a Python API between a VHDL project and some HDL
compilers to catch errors and warnings the compilers generate that can
be used to populate syntax checkers and linters of text editors. It
takes into account the sources dependencies when building so you don't
need to provide a source list ordered by hand."""

__author__ = "Andre Souto (andre820@gmail.com)"
__license__ = "GPLv3"
__version__ = "0.1"
__status__ = "Development"

from hdlcc.project_builder import ProjectBuilder

