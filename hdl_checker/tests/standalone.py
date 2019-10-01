#!/usr/bin/env python
# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.
"HDL Checker standalone stuff"

from __future__ import print_function

import argparse
import logging
import os
import os.path as p
import sys
import time

from prettytable import PrettyTable

import hdl_checker
from hdl_checker.utils import setupLogging

try:
    import cProfile as profile
except ImportError:
    import profile  # type: ignore

try:
    import argcomplete  # type: ignore
    _HAS_ARGCOMPLETE = True
except ImportError: # pragma: no cover
    _HAS_ARGCOMPLETE = False


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
    "Argument parser for standalone hdl_checker"

    if ('--version' in sys.argv[1:]) or ('-V' in sys.argv[1:]):  # pragma: no cover
        print(hdl_checker.__version__)
        sys.exit(0)

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--version', action='store_true',
                        help="Shows hdl_checker version and exit")

    parser.add_argument('--verbose', '-v', action='append_const', const=1,
                        help="""Increases verbose level. Use multiple times to
                                increase more""")

    parser.add_argument('--clean', '-c', action='store_true',
                        help="Cleans the project before building")

    parser.add_argument('--sources', '-s', action='append', nargs='*', default=[],
                        help="""Source(s) file(s) to build individually""") \
                            .completer = _fileExtentensionCompleter('vhd')

    parser.add_argument('--debug-print-sources', action='store_true')
    parser.add_argument('--debug-parse-source-file', action='store_true')
    parser.add_argument('--debug-run-static-check', action='store_true')
    parser.add_argument('--debug-profiling', action='store', nargs='?',
                        metavar='OUTPUT_FILENAME', const='hdl_checker.pstats')

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

class StandaloneProjectBuilder(hdl_checker.hdl_checker_base.HdlCodeCheckerBase):
    """Implementation of standalone hdl_checker.hdl_checker_base.HdlCodeCheckerBase
    to run via shell"""
    _ui_logger = logging.getLogger('UI')
    def _handleUiInfo(self, message):  # pragma: no cover
        self._ui_logger.info(message)

    def _handleUiWarning(self, message):  # pragma: no cover
        self._ui_logger.warning(message)

    def _handleUiError(self, message):  # pragma: no cover
        self._ui_logger.error(message)

def runStandaloneSourceFileParse(fname):
    """Standalone parser run"""
    from hdl_checker.parsers import VhdlParser, VerilogParser

    extension = fname.lower().split('.')[-1]
    cls = VhdlParser if extension in ('vhd', 'vhdl') else VerilogParser

    source = cls(fname)

    print("Source: %s" % source)

    design_units = source.getDesignUnits()
    if design_units: # pragma: no cover
        print(" - Design_units:")
        for unit in design_units:
            print(" -- %s" % str(unit))
    dependencies = source.getDependencies()
    if dependencies: # pragma: no cover
        print(" - Dependencies:")
        for dependency in dependencies:
            print(" -- %s.%s" % (dependency.library, dependency.name))

def runStandaloneStaticCheck(fname):
    """Standalone source_file.VhdlParser run"""
    from hdl_checker.static_check import getStaticMessages

    lines = [x.decode(errors='ignore') for x in open(fname, mode='rb').readlines()]
    for record in getStaticMessages(lines):
        print(record)

def printSourceDiags(project, source):
    "Print diagnostics for the given source"
    start = time.time()
    records = project.getMessagesByPath(source)
    end = time.time()
    _logger.info("Building source '%s' took %.4fs", source, (end - start))
    for record in records:
        if record.filename is not None:
            message = [record.filename]
        else:
            message = [source]

        location = []
        if record.line_number is not None:
            location += ["line %s" % record.line_number]

        if record.column_number is not None:
            location += ["column %s" % record.column_number]

        if location:
            message += ["(%s)" % ', '.join(location)]

        if record.error_code is None:
            message += ["(%s):" % record.severity]
        else:
            message += ["(%s-%s):" % (record.severity,
                                      record.error_code)]

        message += [record.text]

        print(' '.join(message))


def runner(args):
    "Main runner command processing"

    _logger.info("Creating project object")

    project = StandaloneProjectBuilder(args.project_file)

    if args.clean:
        _logger.info("Cleaning up")
        project.clean()

    if args.debug_print_sources:
        sources = PrettyTable(['Filename', 'Library', 'Flags'])
        sources.align['Filename'] = 'l'
        sources.sortby = 'Library'
        for source in project.getSources():
            sources.add_row([source.filename, source.library, " ".join(source.flags)])
        print(sources)

    for source in args.sources:
        printSourceDiags(project, source)

    if args.debug_parse_source_file:
        for source in args.sources:
            runStandaloneSourceFileParse(source)

    if args.debug_run_static_check:
        for source in args.sources:
            runStandaloneStaticCheck(source)

def main():
    "Main hook for standalone usage"
    start = time.time()
    runner_args = parseArguments()
    setupLogging(sys.stdout, runner_args.log_level)
    logging.root.setLevel(runner_args.log_level)
    #  logging.getLogger('hdl_checker.source_file').setLevel(logging.WARNING)
    logging.getLogger('hdl_checker.config_parser').setLevel(logging.WARNING)
    #  logging.getLogger('hdl_checker.builders').setLevel(logging.INFO)
    logging.getLogger('vunit.project').setLevel(logging.ERROR)

    # Running hdl_checker with threads has two major drawbacks:
    # 1) Makes interrupting it impossible currently because each source
    #    file is parsed on is own thread. Since there can be lots of
    #    sources, interrupting a single thread is not enough. This is
    #    discussed at https://github.com/suoto/hdl_checker/issues/19
    # 2) When profiling, the result expected is of the inner hdl_checker calls
    #    and with threads we have no info. This is discussed at
    #    https://github.com/suoto/hdl_checker/issues/16
    # poor results (see suoto/hdl_checker/issues/16).
    # To circumvent this we disable using threads at all when running
    # via standalone (it's ugly, I know)
    # pylint: disable=protected-access
    StandaloneProjectBuilder._USE_THREADS = False
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
