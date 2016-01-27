import os
import sys
import logging

#  try:
sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), \
        '..', '..', 'dependencies', 'rainbow_logging_handler'))
from rainbow_logging_handler import RainbowLoggingHandler
_COLOR_LOGGING = True
#  except ImportError:
#      _COLOR_LOGGING = False

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

