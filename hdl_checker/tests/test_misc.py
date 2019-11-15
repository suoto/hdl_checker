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
from mock import MagicMock, Mock, patch

from hdl_checker.tests import linuxOnly

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
    @patch("hdl_checker.utils.subp.Popen")
    def test_GetCorrectVersion(self, popen):
        process_mock = Mock()
        stdout = b"""\
7e5264355da66f71e8d1b80887ac6df55b9829ef        refs/tags/v0.6.2
7e5264355da66f71e8d1b80887ac6df55b9829ef        refs/tags/v0.6.10
a65602477ef860b48bacfa90a96d8518eb51f030        refs/tags/v0.6.3"""

        stderr = ""

        attrs = {"communicate.return_value": (stdout, stderr)}
        process_mock.configure_mock(**attrs)
        popen.return_value = process_mock

        self.assertEqual(_getLatestReleaseVersion(), (0, 6, 10))

    @patch("hdl_checker.utils.subp.Popen")
    def test_TagExtractionFails(self, popen):
        # Tests if the function doesn't throw any exceptions in case the
        # reported format is different than what we expected
        process_mock = Mock()
        stdout = b"""\
refs/tags/v0.6.2
refs/tags/v0.6.10
refs/tags/v0.6.3"""

        stderr = ""

        attrs = {"communicate.return_value": (stdout, stderr)}
        process_mock.configure_mock(**attrs)
        popen.return_value = process_mock

        self.assertFalse(_getLatestReleaseVersion())

    @patch("hdl_checker.utils.REPO_URL", "localhost")
    def test_HandlesNoConnection(self, *_):
        self.assertIsNone(_getLatestReleaseVersion())

    @linuxOnly
    def test_UnmockedCallWorks(self):
        self.assertIsNotNone(_getLatestReleaseVersion())


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value=(1, 0, 0))
@patch("hdl_checker.__version__", "0.9.0")
def test_ReportIfCurrentIsOlder(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_called_once_with(
        "HDL Checker version 1.0.0 is out! (current version is 0.9.0)"
    )


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value=(1, 0, 10))
@patch("hdl_checker.__version__", "1.0.9")
def test_InterpretAsNumbersNotString(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_called_once_with(
        "HDL Checker version 1.0.10 is out! (current version is 1.0.9)"
    )


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value=(1, 0, 0))
@patch("hdl_checker.__version__", "1.0.0")
def test_DontReportIfCurrentIsUpToDate(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_not_called()


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value=(1, 0, 0))
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


@patch("hdl_checker.utils._getLatestReleaseVersion", return_value=None)
@patch("hdl_checker.__version__", "0+unknown")
def test_DontReportOnInvalidFormats(*_):
    func = MagicMock()
    onNewReleaseFound(func)
    func.assert_not_called()
