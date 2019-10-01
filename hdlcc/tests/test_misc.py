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

import logging
import os.path as p
import re
import subprocess as subp

import parameterized  # type: ignore
import unittest2  # type: ignore

from hdlcc.builder_utils import BuilderName, getBuilderByName
from hdlcc.builders.fallback import Fallback
from hdlcc.builders.ghdl import GHDL
from hdlcc.builders.msim import MSim
from hdlcc.builders.xvhdl import XVHDL
from hdlcc.utils import readFile

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
    r"(?:--|#) along with HDL Code Checker\.  If not, see <http://www\.gnu\.org/licenses/>\.\n"
)


def _getFiles():
    for filename in subp.check_output(
        ["git", "ls-tree", "--name-only", "-r", "HEAD"]
    ).splitlines():
        yield p.abspath(filename).decode()


def _getRelevantFiles():
    def _fileFilter(path):
        # Exclude versioneer files
        if p.basename(path) in ("_version.py", "versioneer.py"):
            return False
        if p.join(".ci", "test_support") in path:
            return False
        return path.split(".")[-1] in ("py", "sh", "ps1")

    return filter(_fileFilter, _getFiles())


def checkFile(filename):
    lines = readFile(filename)

    match = _HEADER.search(lines)
    return match is not None


class TestFileHeaders(unittest2.TestCase):
    @parameterized.parameterized.expand([(x,) for x in _getRelevantFiles()])
    def test_has_license(self, path):
        self.assertTrue(checkFile(path))


class TestBuilderUtils(unittest2.TestCase):
    def test_getBuilderByName(self):
        self.assertEqual(getBuilderByName(BuilderName.msim.value), MSim)
        self.assertEqual(getBuilderByName(BuilderName.ghdl.value), GHDL)
        self.assertEqual(getBuilderByName(BuilderName.xvhdl.value), XVHDL)
        self.assertEqual(getBuilderByName("foo"), Fallback)
