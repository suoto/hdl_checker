# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
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
"Misc tests of files, such as licensing and copyright"

# pylint: disable=function-redefined, missing-docstring, protected-access

import re
import subprocess as subp
import os.path as p
import logging
from nose2.tools import such

_logger = logging.getLogger(__name__)

_HEADER = re.compile(
    r"(?:--|#) This file is part of HDL Code Checker\.\n"
    r"(?:--|#)\n"
    r"(?:--|#) Copyright \(c\) 2015 - 2019 suoto \(Andre Souto\)\n"
    r"(?:--|#)\n"
    r"(?:--|#) HDL Code Checker is free software: you can redistribute it and/or modify\n"
    r"(?:--|#) it under the terms of the GNU General Public License as published by\n"
    r"(?:--|#) the Free Software Foundation, either version 3 of the License, or\n"
    r"(?:--|#) \(at your option\) any later version\.\n"
    r"(?:--|#)\n"
    r"(?:--|#) HDL Code Checker is distributed in the hope that it will be useful,\n"
    r"(?:--|#) but WITHOUT ANY WARRANTY; without even the implied warranty of\n"
    r"(?:--|#) MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE\.  See the\n"
    r"(?:--|#) GNU General Public License for more details\.\n"
    r"(?:--|#)\n"
    r"(?:--|#) You should have received a copy of the GNU General Public License\n"
    r"(?:--|#) along with HDL Code Checker\.  If not, see <http://www\.gnu\.org/licenses/>\.\n")

with such.A("hdlcc sources") as it:
    @it.should("contain the correct file header")
    def test():

        def _fileFilter(path):
            # Exclude dependencies
            if 'bottle' in path.split(p.sep):
                return False
            if 'requests' in path.split(p.sep):
                return False
            if 'waitress' in path.split(p.sep):
                return False
            # Exclude versioneer files
            if p.basename(path) in ('_version.py', 'versioneer.py'):
                return False
            # Exclude files copied almost as is from
            # https://github.com/palantir/python-language-server/
            if p.basename(path) in ('defines.py', 'uris.py'):
                return False
            return path.split('.')[-1] in ('py', 'sh', 'ps1')

        files = list(getFiles(_fileFilter))

        it.assertNotEquals(files, [], "Couldn't find any files!")
        _logger.info("Files found: %s", ", ".join(files))
        bad_files = []
        for filename in files:
            if checkFile(filename):
                _logger.debug("%s: Ok", filename)
            else:
                _logger.error("%s: problems found", filename)
                bad_files += [filename]

        it.assertEquals(bad_files, [],
                        "Some files have problems: %s" % ", ".join(bad_files))

    def getFiles(func):
        for filename in subp.check_output(
                ['git', 'ls-tree', '--name-only', '-r', 'HEAD']).splitlines():
            if func(filename.decode()):
                yield p.abspath(filename).decode()

    def checkFile(filename):
        lines = open(filename, mode='rb').read().decode(errors='replace')

        match = _HEADER.search(lines)
        return match is not None

it.createTests(globals())
