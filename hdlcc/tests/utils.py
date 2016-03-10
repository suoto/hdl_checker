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
"Commom things for tests"

import os
import time
import logging

_logger = logging.getLogger(__name__)

def writeListToFile(filename, _list):
    "Well... writes '_list' to 'filename'"
    _logger.info("Writing to %s", filename)
    open(filename, 'w').write('\n'.join([str(x) for x in _list]))
    mtime = os.path.getmtime(filename)
    time.sleep(0.01)
    os.popen("touch %s" % filename, 'r').read()
    for i in range(10):
        if os.path.getmtime(filename) != mtime:
            break
        _logger.debug("Waiting...[%d]", i)
        time.sleep(0.1)

