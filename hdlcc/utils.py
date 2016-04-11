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
"Common stuff"

import logging

def setupLogging(stream, level, color=True):
    "Setup logging according to the command line parameters"
    if type(stream) is str: # pragma: no cover
        class Stream(file):
            """File subclass that allows RainbowLoggingHandler to write
            with colors"""
            def isatty(self):
                return color
            def write(self, *args, **kwargs):
                super(Stream, self).write(*args, **kwargs)
                super(Stream, self).write("\n")

        stream = Stream(stream, 'ab', buffering=1)

    try:
        from rainbow_logging_handler import RainbowLoggingHandler
        rainbow_stream_handler = RainbowLoggingHandler(
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

        logging.root.addHandler(rainbow_stream_handler)
        logging.root.setLevel(level)
    except ImportError: # pragma: no cover
        file_handler = logging.StreamHandler(stream)
        #  log_format = "%(levelname)-8s || %(name)-30s || %(message)s"
        #  file_handler.formatter = logging.Formatter(log_format)
        file_handler.formatter = logging.Formatter()
        logging.root.addHandler(file_handler)
        logging.root.setLevel(level)

