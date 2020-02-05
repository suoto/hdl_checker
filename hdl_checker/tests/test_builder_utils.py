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

# pylint: disable=function-redefined
# pylint: disable=invalid-name
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=useless-object-inheritance

import logging
import os.path as p

from mock import MagicMock, patch

from hdl_checker.tests import TestCase, disableVunit, getTestTempPath

from hdl_checker.builder_utils import (
    foundVunit,
    getBuilderByName,
    getPreferredBuilder,
    getVunitSources,
)
from hdl_checker.builders.fallback import Fallback
from hdl_checker.builders.ghdl import GHDL
from hdl_checker.builders.msim import MSim
from hdl_checker.builders.xvhdl import XVHDL
from hdl_checker.path import Path
from hdl_checker.types import FileType

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


class TestBuilderUtils(TestCase):
    def test_getBuilderByName(self):
        self.assertEqual(getBuilderByName("msim"), MSim)
        self.assertEqual(getBuilderByName("xvhdl"), XVHDL)
        self.assertEqual(getBuilderByName("ghdl"), GHDL)
        self.assertEqual(getBuilderByName("other"), Fallback)

    def test_getWorkingBuilders(self):
        # Test no working builders
        _logger.info("Checking no builder works")
        self.assertEqual(getPreferredBuilder(), Fallback)

        # Patch one builder
        with patch.object(MSim, "isAvailable", staticmethod(lambda: True)):
            self.assertEqual(getPreferredBuilder(), MSim)
            # Patch another builder with lower priority
            with patch.object(GHDL, "isAvailable", staticmethod(lambda: True)):
                self.assertEqual(getPreferredBuilder(), MSim)

        # Patch one builder
        with patch.object(GHDL, "isAvailable", staticmethod(lambda: True)):
            self.assertEqual(getPreferredBuilder(), GHDL)

            # Patch another builder
            with patch.object(MSim, "isAvailable", staticmethod(lambda: True)):
                self.assertEqual(getPreferredBuilder(), MSim)


class Library(object):  # pylint: disable=too-few-public-methods
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name


class SourceFile(object):
    def __init__(self, name, library, vhdl_standard="2008"):
        self._name = name
        self._library = Library(library)
        self._vhdl_standard = vhdl_standard

    @property
    def name(self):
        return self._name

    @property
    def library(self):
        return self._library

    @property
    def vhdl_standard(self):
        return self._vhdl_standard


class TestGetVunitSources(TestCase):
    def test_VunitNotFound(self):
        builder = MagicMock()
        with disableVunit:
            self.assertFalse(list(getVunitSources(builder)))

    @patch("vunit.VUnit.get_source_files")
    def test_VhdlBuilder(self, get_source_files):
        get_source_files.side_effect = [
            [
                SourceFile(name=_path("path_0.vhd"), library="libary_0"),
                SourceFile(name=_path("path_1.vhd"), library="libary_1"),
            ]
        ]

        builder = MagicMock()
        builder.builder_name = "msim"
        builder.file_types = {FileType.vhdl}

        self.maxDiff = None  # pylint: disable=attribute-defined-outside-init
        self.assertTrue(foundVunit(), "Need VUnit for this test")
        # Should only have VHDL files
        sources = list(getVunitSources(builder))

        get_source_files.assert_called_once()

        self.assertCountEqual(
            sources,
            {
                (Path(_path("path_0.vhd")), "libary_0", ("-2008",)),
                (Path(_path("path_1.vhd")), "libary_1", ("-2008",)),
            },
        )

    @patch("hdl_checker.builder_utils.findRtlSourcesByPath")
    @patch("vunit.verilog.VUnit.get_source_files")
    def test_SystemverilogOnlyBuilder(self, get_source_files, find_rtl_sources):
        get_source_files.side_effect = [
            [
                SourceFile(name=_path("path_0.vhd"), library="libary_0"),
                SourceFile(name=_path("path_1.vhd"), library="libary_1"),
            ]
        ]

        find_rtl_sources.return_value = [
            Path(_path("some_header.vh")),
            Path(_path("some_header.svh")),
        ]

        builder = MagicMock()
        builder.builder_name = "msim"
        builder.file_types = {FileType.systemverilog}

        self.assertTrue(foundVunit(), "Need VUnit for this test")
        # Should only have VHDL files
        sources = list(getVunitSources(builder))

        get_source_files.assert_called_once()
        find_rtl_sources.assert_called_once()

        self.assertCountEqual(
            sources,
            {
                (Path(_path("path_0.vhd")), "libary_0", ("-2008",)),
                (Path(_path("path_1.vhd")), "libary_1", ("-2008",)),
                (Path(_path("some_header.vh")), None, ()),
                (Path(_path("some_header.svh")), None, ()),
            },
        )

    @patch("hdl_checker.builder_utils._getSourcesFromVUnitModule")
    def test_VerilogOnlyBuilder(self, meth):
        builder = MagicMock()
        builder.builder_name = "msim"
        builder.file_types = {FileType.verilog}

        self.assertTrue(foundVunit(), "Need VUnit for this test")
        self.assertFalse(list(getVunitSources(builder)))
        meth.assert_not_called()

    @patch("hdl_checker.builder_utils.findRtlSourcesByPath")
    @patch("vunit.VUnit.get_source_files")
    @patch("vunit.verilog.VUnit.get_source_files")
    def test_VhdlAndSystemverilogOnlyBuilder(
        self, vhdl_method, sv_method, find_rtl_sources
    ):
        vhdl_method.side_effect = [
            [
                SourceFile(name=_path("path_0.vhd"), library="libary_0"),
                SourceFile(name=_path("path_1.vhd"), library="libary_1"),
            ]
        ]

        sv_method.side_effect = [
            [
                SourceFile(name=_path("path_2.sv"), library="libary_2"),
                SourceFile(name=_path("path_3.sv"), library="libary_3"),
            ]
        ]

        find_rtl_sources.return_value = [
            Path(_path("some_header.vh")),
            Path(_path("some_header.svh")),
        ]

        builder = MagicMock()
        builder.builder_name = "xvhdl"
        builder.file_types = {FileType.vhdl, FileType.systemverilog}

        self.assertTrue(foundVunit(), "Need VUnit for this test")
        # Should only have VHDL files
        sources = list(getVunitSources(builder))

        vhdl_method.assert_called_once()
        sv_method.assert_called_once()

        self.assertCountEqual(
            sources,
            {
                (Path(_path("path_0.vhd")), "libary_0", ()),
                (Path(_path("path_1.vhd")), "libary_1", ()),
                (Path(_path("path_2.sv")), "libary_2", ()),
                (Path(_path("path_3.sv")), "libary_3", ()),
                (Path(_path("some_header.vh")), None, ()),
                (Path(_path("some_header.svh")), None, ()),
            },
        )
