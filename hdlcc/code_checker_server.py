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
"HDL Code Checker server for running on a different process"

import logging
import multiprocessing
from hdlcc.code_checker_base import HdlCodeCheckerBase

_logger = logging.getLogger('build messages')

# pylint: disable=too-many-instance-attributes,abstract-class-not-used
class HdlCodeCheckerSever(multiprocessing.Process):
    "HDL Code Checker project builder class"
    def __init__(self, *args, **kwargs):
        self._code_checker = HdlCodeCheckerBase(*args, **kwargs)
        self.name = 'HdlCodeCheckerSever.%d' % self._identity

