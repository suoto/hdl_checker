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
"Misc tests of files, such as licensing and copyright"

# pylint: disable=function-redefined
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

import logging
import os.path as p
import re
import subprocess as subp

import parameterized  # type: ignore
import unittest2  # type: ignore
from mock import MagicMock, patch

from hdl_checker.builder_utils import BuilderName, getBuilderByName
from hdl_checker.builders.fallback import Fallback
from hdl_checker.builders.ghdl import GHDL
from hdl_checker.builders.msim import MSim
from hdl_checker.builders.xvhdl import XVHDL
from hdl_checker.utils import _getLatestReleaseVersion, onNewReleaseFound, readFile

_logger = logging.getLogger(__name__)

_HEADER = re.compile(
    r"(?:--|#) This file is part of HDL Checker\.\n"
    r"(?:--|#)\n"
    r"(?:--|#) Copyright \(c\) 2015 - 2019 suoto \(Andre Souto\)\n"
    r"(?:--|#)\n"
    r"(?:--|#) HDL Checker is free software: you can redistribute it and/or modify\n"
    r"(?:--|#) it under the terms of the GNU General Public License as published by\n"
    r"(?:--|#) the Free Software Foundation, either version 3 of the License, or\n"
    r"(?:--|#) \(at your option\) any later version\.\n"
    r"(?:--|#)\n"
    r"(?:--|#) HDL Checker is distributed in the hope that it will be useful,\n"
    r"(?:--|#) but WITHOUT ANY WARRANTY; without even the implied warranty of\n"
    r"(?:--|#) MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE\.  See the\n"
    r"(?:--|#) GNU General Public License for more details\.\n"
    r"(?:--|#)\n"
    r"(?:--|#) You should have received a copy of the GNU General Public License\n"
    r"(?:--|#) along with HDL Checker\.  If not, see <http://www\.gnu\.org/licenses/>\.\n"
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


class TestReportingRelease(unittest2.TestCase):
    @patch(
        "hdl_checker.utils.subp.check_output",
        return_value=b"""\
ee3443bee4ba4ef91a7f8282d6af25c9c75e85d5        refs/tags/v0.1.0
db561d5c26f8371650a60e9c3f1d3f6c2cb564d5        refs/tags/v0.2
b23cce9938ea6723ed9969473f1c84c668f86bab        refs/tags/v0.3
3b1b105060ab8dd91e73619191bf44d7a3e70a95        refs/tags/v0.4
23ce39aaaa494ebc33f9aefec317feaea4200222        refs/tags/v0.4.1
8bca9a3b5764da502d22d9a4c3563bbcdbc6aaa6        refs/tags/v0.4.2
c455f5ca764d17365d77c23d14f2fe3a6234960b        refs/tags/v0.4.3
09a1ee298f30a7412d766fe61974ae7de429d00c        refs/tags/v0.5
ab8d07a45195cc70403cbe31b571f593dfc18c56        refs/tags/v0.5.1
3deeffb3c3e75c385782db66613babfdab60c019        refs/tags/v0.5.2
95444ca3051c0174dab747d4b4d5792ced5f87b6        refs/tags/v0.6
108016f86c3e36ceb7f54bcd12227fb335cd9e25        refs/tags/v0.6.1
7e5264355da66f71e8d1b80887ac6df55b9829ef        refs/tags/v0.6.2
a65602477ef860b48bacfa90a96d8518eb51f030        refs/tags/v0.6.3""",
    )
    def test_GetCorrectVersion(self, *_):
        self.assertEqual(_getLatestReleaseVersion(), "0.6.3")

    @patch("hdl_checker.utils.subp.check_output", return_value=b"0.6.3")
    def test_RejectsInvalidFormats(self, *_):
        self.assertIsNone(_getLatestReleaseVersion())

    @patch("hdl_checker.utils.REPO_URL", "localhost")
    def test_HandlesNoConnection(self, *_):
        self.assertIsNone(_getLatestReleaseVersion())


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value="1.0.0")
@patch("hdl_checker.__version__", "0.9.0")
def test_ReportIfCurrentIsOlder(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_called_once_with(
        "HDL Checker version 1.0.0 is out! (current version is 0.9.0)"
    )


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value="1.0.0")
@patch("hdl_checker.__version__", "1.0.0")
def test_DontReportIfCurrentIsUpToDate(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_not_called()


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value="1.0.0")
@patch("hdl_checker.__version__", "1.0.1")
def test_DontReportIfCurrentIsNewer(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_not_called()


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value=None)
@patch("hdl_checker.__version__", "1.0.1")
def test_DontReportIfFailedToGetVersion(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_not_called()
