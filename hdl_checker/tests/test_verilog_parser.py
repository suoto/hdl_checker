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

# pylint: disable=function-redefined, missing-docstring, protected-access

import json
import logging
from tempfile import NamedTemporaryFile

from parameterized import parameterized_class  # type: ignore

from hdl_checker.tests import TestCase, writeListToFile

from hdl_checker.parsers.elements.dependency_spec import (
    RequiredDesignUnit,
    IncludedPath,
)
from hdl_checker.parsers.elements.identifier import VerilogIdentifier
from hdl_checker.parsers.elements.parsed_element import Location
from hdl_checker.parsers.verilog_parser import VerilogDesignUnit, VerilogParser
from hdl_checker.path import Path
from hdl_checker.serialization import StateEncoder, jsonObjectHook
from hdl_checker.types import DesignUnitType

_logger = logging.getLogger(__name__)


def parametrizeClassWithFileTypes(cls):
    keys = ["filetype"]
    values = [(x,) for x in ("v", "vh", "sv", "svh")]

    return parameterized_class(keys, values)(cls)


@parametrizeClassWithFileTypes
class TestVerilogSource(TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.filename = NamedTemporaryFile(suffix="." + cls.filetype).name

        writeListToFile(
            cls.filename,
            [
                '`include "some/include"',
                "",
                "import some_package::*;",
                "import  another_package :: some_name ;",
                "",
                "module clock_divider",
                "    #(parameter DIVISION = 5)",
                "    (// Usual ports",
                "    input clk,",
                "    input rst,",
                "    // Output clock divided",
                "    output       clk_div);",
                "   localparam foo::bar = std::randomize(cycles);",
                "endmodule",
                "",
                "package \\m$gPkg! ;",
                "  integer  errCnt  = 0;",
                "  integer  warnCnt = 0;",
                "endpackage",
                "",
            ],
        )

        cls.source = VerilogParser(Path(cls.filename))

    def test_GetDesignUnits(self):
        design_units = list(self.source.getDesignUnits())
        _logger.debug("Design units: %s", design_units)
        self.assertCountEqual(
            design_units,
            [
                VerilogDesignUnit(
                    owner=self.source.filename,
                    name="clock_divider",
                    type_=DesignUnitType.entity,
                    locations={(5, 7)},
                ),
                VerilogDesignUnit(
                    owner=self.source.filename,
                    name="\\m$gPkg!",
                    type_=DesignUnitType.package,
                    locations={(15, 8)},
                ),
            ],
        )

    def test_GetDependencies(self):
        expected = [
            IncludedPath(
                owner=Path(self.filename),
                name=VerilogIdentifier("some/include"),
                locations=(Location(line=0, column=8),),
            )
        ]

        if self.filetype in ("sv", "svh"):
            expected += [
                RequiredDesignUnit(
                    owner=Path(self.filename),
                    name=VerilogIdentifier("some_package"),
                    library=None,
                    locations=(Location(line=2, column=7),),
                ),
                RequiredDesignUnit(
                    owner=Path(self.filename),
                    name=VerilogIdentifier("another_package"),
                    library=None,
                    locations=(Location(line=3, column=8),),
                ),
                RequiredDesignUnit(
                    owner=Path(self.filename),
                    name=VerilogIdentifier("foo"),
                    library=None,
                    locations=(Location(line=12, column=14),),
                ),
            ]

        self.assertCountEqual(self.source.getDependencies(), expected)

    def test_CacheRecovery(self):
        state = json.dumps(self.source, cls=StateEncoder)
        _logger.info("State before: %s", state)
        recovered = json.loads(state, object_hook=jsonObjectHook)
        self.assertEqual(self.source.filename, recovered.filename)
