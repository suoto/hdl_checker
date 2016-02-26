#!/usr/bin/env python
# This file is part of hdlcc.
#
# hdlcc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# hdlcc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with hdlcc.  If not, see <http://www.gnu.org/licenses/>.
"Script should be called within Vim to launch tests"

import os
from sys import argv
import logging
import nose2
import coverage

_logger = logging.getLogger(__name__)

def test(nose2_argv):
    cov = coverage.Coverage(config_file='.coveragerc')
    cov.start()

    nose2.discover(exit=False, argv=nose2_argv)

    cov.stop()
    cov.save()
    cov.combine()
    cov.html_report()

def clear():
    for cmd in ('git clean -fdx',
                'git submodule foreach --recursive git clean -fdx'):
        print cmd
        print os.popen(cmd).read()

def main():
    file_handler = logging.FileHandler("tests.log")
    log_format = "[%(asctime)s] %(levelname)-8s || %(name)-30s || %(message)s"
    file_handler.formatter = logging.Formatter(log_format)
    logging.root.addHandler(file_handler)
    logging.root.setLevel(logging.DEBUG)

    if '--clear' in argv[1:]:
        clear()
        argv.pop(argv.index('--clear'))

    test(nose2_argv=argv[1:])

if __name__ == '__main__':
    main()


