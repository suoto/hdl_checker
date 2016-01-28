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

import os
import sys
import logging

try:
    sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), \
            '..', '..', 'dependencies', 'rainbow_logging_handler'))
    from rainbow_logging_handler import RainbowLoggingHandler
    _COLOR_LOGGING = True
except ImportError:
    _COLOR_LOGGING = False

class StreamToFile(object):
    def __init__(self, filename):
        self._filename = filename

    def write(self, s):
        file_desc = open(self._filename, 'a')
        file_desc.write(str(s))
        file_desc.close()

    def isatty(self):
        return True

def _setupStreamHandler(stream):
    if _COLOR_LOGGING:
        stream_handler = RainbowLoggingHandler(
            stream,
            #  Customizing each column's color
            # pylint: disable=bad-whitespace
            color_asctime          = ('dim white',  'black'),
            color_name             = ('dim white',  'black'),
            color_funcName         = ('green',      'black'),
            color_lineno           = ('dim white',  'black'),
            color_pathname         = ('black',      'red'),
            color_module           = ('yellow',     None),
            color_message_debug    = ('color_59',   None),
            color_message_info     = (None,         None),
            color_message_warning  = ('color_226',  None),
            color_message_error    = ('red',        None),
            color_message_critical = ('bold white', 'red'))
            # pylint: enable=bad-whitespace
    else:
        stream_handler = logging.StreamHandler(stream)

    logging.root.addHandler(stream_handler)

_stream = StreamToFile('test.log')
open('test.log', 'w').close()
_setupStreamHandler(_stream)

