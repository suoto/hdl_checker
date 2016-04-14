#!/usr/bin/env python
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
"HDLCC standalone stuff"

import os
import os.path as p
import logging
import time
import argparse
from prettytable import PrettyTable
import sys

try:
    import cProfile as profile
except ImportError:
    import profile

try:
    import argcomplete
    _HAS_ARGCOMPLETE = True
except ImportError: # pragma: no cover
    _HAS_ARGCOMPLETE = False

import hdlcc

_logger = logging.getLogger(__name__)

def _fileExtentensionCompleter(extension): # pragma: no cover
    "Tab completion for 'extension'"
    def _completer(**kwargs): # pylint: disable=missing-docstring
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
    "Argument parser for standalone hdlcc"

    if ('--version' in sys.argv[1:]) or ('-V' in sys.argv[1:]):
        print hdlcc.__version__
        sys.exit(0)

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--version', action='store_true',
                        help="Shows hdlcc version and exit")

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


    if _HAS_ARGCOMPLETE: # pragma: no cover
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    # PYTHON_ARGCOMPLETE_OK

    args.project_file = args.project_file[0]

    args.log_level = logging.FATAL
    if args.verbose:
        if len(args.verbose) == 1:
            args.log_level = logging.WARNING
        elif len(args.verbose) == 2:
            args.log_level = logging.INFO
        else:
            args.log_level = logging.DEBUG

    # Planify source list if supplied
    if args.sources:
        args.sources = [source for sublist in args.sources for source in sublist]

    return args

class StandaloneProjectBuilder(hdlcc.code_checker_base.HdlCodeCheckerBase):
    """Implementation of standalone hdlcc.code_checker_base.HdlCodeCheckerBase
    to run via shell"""
    _ui_logger = logging.getLogger('UI')
    def _handleUiInfo(self, message):
        self._ui_logger.info(message)

    def _handleUiWarning(self, message):
        self._ui_logger.warning(message)

    def _handleUiError(self, message):
        self._ui_logger.error(message)

def runStandaloneSourceFileParse(fname):
    """Standalone source_file.VhdlSourceFile run"""
    from hdlcc.source_file import VhdlSourceFile
    source = VhdlSourceFile(fname)
    print "Source: %s" % source

    design_units = source.getDesignUnits()
    if design_units: # pragma: no cover
        print " - Design_units:"
        for unit in design_units:
            print " -- %s" % str(unit)
    dependencies = source.getDependencies()
    if dependencies: # pragma: no cover
        print " - Dependencies:"
        for dependency in dependencies:
            print " -- %s.%s" % (dependency['library'], dependency['unit'])

def runStandaloneStaticCheck(fname):
    """Standalone source_file.VhdlSourceFile run"""
    from hdlcc.static_check import getStaticMessages

    for record in getStaticMessages(open(fname, 'r').read().split('\n')):
        print record

def runner(args):
    "Main runner command processing"

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
    "Tries to use RainbowLoggingHandler for logging to stdout"
    try:
        from rainbow_logging_handler import RainbowLoggingHandler
        # pylint: disable=bad-whitespace
        stream_handler = RainbowLoggingHandler(
            sys.stdout,
            #  Customizing each column's color
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
        stream_handler = logging.StreamHandler(sys.stdout)

    logging.root.addHandler(stream_handler)
    logging.root.setLevel(logging.WARNING)

def main():
    "Main hook for standalone usage"
    setupLogging()
    start = time.time()
    runner_args = parseArguments()
    logging.root.setLevel(runner_args.log_level)
    logging.getLogger('hdlcc.source_file').setLevel(logging.WARNING)

    # Running hdlcc with threads has two major drawbacks:
    # 1) Makes interrupting it impossible currently because each source
    #    file is parsed on is own thread. Since there can be lots of
    #    sources, interrupting a single thread is not enough. This is
    #    discussed at https://github.com/suoto/hdlcc/issues/19
    # 2) When profiling, the result expected is of the inner hdlcc calls
    #    and with threads we have no info. This is discussed at
    #    https://github.com/suoto/hdlcc/issues/16
    # poor results (see suoto/hdlcc/issues/16).
    # To circumvent this we disable using threads at all when running
    # via standalone (it's ugly, I know)
    # pylint: disable=protected-access
    StandaloneProjectBuilder._USE_THREADS = False
    hdlcc.source_file.VhdlSourceFile._USE_THREADS = False
    # pylint: enable=protected-access

    if runner_args.debug_profiling:
        profile.runctx(
            'runner(runner_args)',
            globals=globals(),
            locals={'runner_args' : runner_args},
            filename=runner_args.debug_profiling, sort=-1)
    else:
        runner(runner_args)
    end = time.time()
    _logger.info("Process took %.2fs", (end - start))

if __name__ == '__main__':
    sys.exit(main())

