#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

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
import os.path as p
import logging
import time
import argparse
from prettytable import PrettyTable
from sys import stdout, path
try:
    import argcomplete
    _HAS_ARGCOMPLETE = True
except ImportError:
    _HAS_ARGCOMPLETE = False

try:
    import cProfile as profile
except ImportError:
    import profile

def _pathSetup():
    import sys
    path_to_this_file = p.realpath(__file__).split(p.sep)[:-2]
    hdlcc_path = p.sep.join(path_to_this_file)
    if hdlcc_path not in sys.path:
        sys.path.insert(0, hdlcc_path)

if __name__ == '__main__':
    _pathSetup()

from config import Config
from project_builder import ProjectBuilder

class StandaloneProjectBuilder(ProjectBuilder):
    _ui_logger = logging.getLogger('UI')
    def _handleUiInfo(self, message):
        self._ui_logger.info(message)

    def _handleUiWarning(self, message):
        self._ui_logger.warning(message)

    def _handleUiError(self, message):
        self._ui_logger.error(message)

def _fileExtentensionCompleter(extension):
    def _completer(**kwargs):
        prefix = kwargs['prefix']
        if prefix == '':
            prefix = os.curdir

        result = []
        for line in os.listdir(prefix):
            if line.lower().endswith('.' + extension):
                result.append(line)
            elif p.isdir(line):
                result.append("./" + line)

        return result
    return _completer

def parseArguments():
    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--verbose', '-v', action='append_const', const=1,
                        help="""Increases verbose level. Use multiple times to
                                increase more""")

    parser.add_argument('--clean', '-c', action='store_true',
                        help="Cleans the project before building")

    parser.add_argument('--build', '-b', action='store_true',
                        help="Builds the project given by <project_file>")

    parser.add_argument('--sources', '-s', action='append', nargs='*',
                        help="""Source(s) file(s) to build individually""") \
                            .completer = _fileExtentensionCompleter('vhd')

    parser.add_argument('--debug-print-sources', action='store_true')
    parser.add_argument('--debug-print-compile-order', action='store_true')
    parser.add_argument('--debug-parse-source-file', action='store_true')
    parser.add_argument('--debug-run-static-check', action='store_true')
    parser.add_argument('--debug-profiling', action='store', nargs='?',
                        metavar='OUTPUT_FILENAME', const='hdlcc.pstats')

    # Mandatory arguments
    parser.add_argument('project_file', action='store', nargs=1,
                        help="""Configuration file that defines what should be
                        built (lists sources, libraries, build flags and so on""")


    if _HAS_ARGCOMPLETE:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    args.project_file = args.project_file[0]

    args.log_level = logging.FATAL
    if args.verbose:
        if len(args.verbose) == 0:
            args.log_level = logging.FATAL
        elif len(args.verbose) == 1:
            args.log_level = logging.WARNING
        elif len(args.verbose) == 2:
            args.log_level = logging.INFO
        elif len(args.verbose) >= 3:
            args.log_level = logging.DEBUG

    # Planify source list if supplied
    if args.sources:
        args.sources = [source for sublist in args.sources for source in sublist]

    Config.log_level = args.log_level
    #  Config.setupBuild()

    return args

def runStandaloneSourceFileParse(fname):
    """Standalone source_file.VhdlSourceFile run"""
    from hdlcc.source_file import VhdlSourceFile
    source = VhdlSourceFile(fname)
    print "Source: %s" % source
    design_units = source.getDesignUnits()
    if design_units:
        print " - Design_units:"
        for unit in design_units:
            print " -- %s" % str(unit)
    dependencies = source.getDependencies()
    if dependencies:
        print " - Dependencies:"
        for dependency in dependencies:
            print " -- %s.%s" % (dependency['library'], dependency['unit'])

def runStandaloneStaticCheck(fname):
    """Standalone source_file.VhdlSourceFile run"""
    from hdlcc.static_check import getStaticMessages

    for record in getStaticMessages(open(fname, 'r').read().split('\n')):
        print record

def main(args):
    "Main runner command processing"

    # FIXME: Find a better way to insert a header to the log file
    _logger.info("#"*(197 - 32))
    _logger.info("Creating project object")

    if args.clean:
        _logger.info("Cleaning up")
        StandaloneProjectBuilder.clean(args.project_file)

    if args.debug_print_sources or args.debug_print_compile_order or args.build:
        project = StandaloneProjectBuilder(args.project_file)
        project.waitForBuild()

    if args.debug_print_sources:
        sources = PrettyTable(['Filename', 'Library', 'Flags'])
        sources.align['Filename'] = 'l'
        sources.sortby = 'Library'
        for source in project.getSources():
            sources.add_row([source.filename, source.library, " ".join(source.flags)])
        print sources

    if args.debug_print_compile_order:
        for source in project.getCompilationOrder():
            print "{lang} {library} {path} {flags}".format(
                lang='vhdl', library=source.library, path=source.filename,
                flags=' '.join(source.flags))
            assert not set(['-93', '-2008']).issubset(source.flags)

    if args.build and args.sources:
        for source in args.sources:
            try:
                _logger.info("Building source '%s'", source)
                for record in project.getMessagesByPath(source):
                    print "[{error_type}-{error_number}] @ " \
                          "({line_number},{column}): {error_message}"\
                            .format(**record)
            except RuntimeError as exception:
                _logger.error("Unable to build '%s': '%s'", source,
                              str(exception))
                continue

    if args.debug_parse_source_file:
        for source in args.sources:
            runStandaloneSourceFileParse(source)

    if args.debug_run_static_check:
        for source in args.sources:
            runStandaloneStaticCheck(source)

    if args.debug_print_sources or args.debug_print_compile_order or args.build:
        project.saveCache()

def setupLogging():
    path.insert(0, p.abspath('dependencies/rainbow_logging_handler/'))
    try:
        from rainbow_logging_handler import RainbowLoggingHandler
        stream_handler = RainbowLoggingHandler(
            stdout,
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
    except ImportError: # pragma: no cover
        stream_handler = logging.StreamHandler(stdout)

    logging.root.addHandler(stream_handler)
    logging.root.setLevel(logging.DEBUG)

if __name__ == '__main__':
    setupLogging()
    _logger = logging.getLogger(__name__)
    start = time.time()
    runner_args = parseArguments()
    logging.getLogger('hdlcc.source_file').setLevel(logging.WARNING)
    if runner_args.debug_profiling:
        profile.run('main(runner_args)', runner_args.debug_profiling)
    else:
        main(runner_args)
    end = time.time()
    _logger.info("Process took %.2fs", (end - start))

