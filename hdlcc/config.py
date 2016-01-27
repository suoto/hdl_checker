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

import logging, os, sys
try:
    sys.path.insert(0, '/home/souto/temp/rainbow_logging_handler')
    from rainbow_logging_handler import RainbowLoggingHandler
    _COLOR_LOGGING = True
except ImportError:
    _COLOR_LOGGING = False

class Config(object):
    "Store HDL Code Checker configuration"
    is_toolchain = None
    thread_limit = 20

    # Only for running in standlone mode
    log_level = logging.DEBUG
    log_format = "%(levelname)-8s || %(name)s || %(message)s"

    show_only_current_file = False

    # When building a specific source, we can build its first level
    # dependencies and display their errors and/or warnings. Notice
    # that no dependency tracking will be done when none of them
    # are enabled!
    show_reverse_dependencies_errors = True
    show_reverse_dependencies_warnings = False
    max_reverse_dependency_sources = 20

    # When we find errors, we can cache them to avoid recompiling a
    # specific source file or consider the file as changed. Notice this
    # is changed from True to False, the errors reported for a given
    # source will be the cached ontes until we force rebuilding it
    cache_error_messages = True

    _logger = logging.getLogger(__name__)

    _added_stream_handler = False
    @staticmethod
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

        #  stream_handler.formatter = logging.Formatter(Config.log_format)
        #  logging.root.addHandler(stream_handler)
        logging.root.handlers = [stream_handler]
        logging.root.setLevel(Config.log_level)

    @staticmethod
    def _setupToolchain():
        Config.log_level = logging.DEBUG
        Config._logger.info("Setup for toolchain")
        Config.is_toolchain = True

    @staticmethod
    def _setupStandalone():
        Config.is_toolchain = False
        if not Config._added_stream_handler:
            Config._setupStreamHandler(sys.stdout)
            Config._added_stream_handler = True
        Config._logger.info("Setup for standalone")

    @staticmethod
    def setupBuild():
        if Config.is_toolchain is not None:
            return
        logging.getLogger("requests").setLevel(logging.WARNING)
        try:
            import vim
            Config._setupToolchain()
        except ImportError:
            if 'VIM' in os.environ.keys():
                Config._setupToolchain()
            else:
                Config._setupStandalone()

    @staticmethod
    def updateFromArgparse(args):
        for k, v in args._get_kwargs():
            if k in ('is_toolchain', ):
                raise RuntimeError("Can't redefine %s" % k)

            if k == 'thread_limit' and v is None:
                continue

            setattr(Config, k, v)

        _msg = ["Configuration update"]
        for k, v in Config.getCurrentConfig().iteritems():
            _msg += ["%s = %s" % (str(k), str(v))]

        Config._logger.info("\n".join(_msg))

    @staticmethod
    def getCurrentConfig():
        r = {}
        for k, v in Config.__dict__.iteritems():
            if k.startswith('_'):
                continue
            if k.startswith('__') and k.startswith('__'):
                continue
            if type(v) is staticmethod:
                continue
            r[k] = v
        return r

