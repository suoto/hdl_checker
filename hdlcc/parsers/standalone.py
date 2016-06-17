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
"VHDL source file parser"

import logging
_logger = logging.getLogger(__name__)

from hdlcc.parsers import getSourceFileObjects

def parseArguments(): # pragma: no cover
    "Argument parser for standalone usage"
    import argparse

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--verbose', '-v', action='append_const', const=1,
                        help="""Increases verbose level. Use multiple times to
                                increase more""")

    parser.add_argument('--processes', '-p', type=int, default=3,
                        help="""Maximum number of processes to be used when
                                parsing source files""")

    # Mandatory arguments
    parser.add_argument('sources', action='append', nargs='+',
                        help="List of sources to parse")

    args = parser.parse_args()

    args.log_level = logging.FATAL
    if args.verbose:
        if len(args.verbose) == 1:
            args.log_level = logging.WARNING
        elif len(args.verbose) == 2:
            args.log_level = logging.INFO
        else:
            args.log_level = logging.DEBUG

    # Planify source list if supplied
    args.sources = [source for sublist in args.sources for source in sublist]

    if args.processes:
        args.processes = min(args.processes, len(args.sources))

    return args

def standalone(): # pragma: no cover
    """Standalone run"""
    import sys
    import time
    from hdlcc.utils import setupLogging
    args = parseArguments()
    setupLogging(sys.stdout, args.log_level, color=True)

    start = time.time()
    sources = list(getSourceFileObjects(
        [{'filename' : source, 'library' : 'work'} for source in args.sources],
        workers=args.processes))
    diff = time.time() - start

    for source in sources:
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

    _logger.info("Parsing took %.4fs", diff)

if __name__ == '__main__':
    standalone()

