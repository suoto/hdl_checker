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

# pylint: disable=function-redefined, missing-docstring, protected-access

import json
import logging
import os

import six
from nose2.tools import such  # type: ignore

from hdlcc.parsers import DesignUnit, DesignUnitType, Identifier, VerilogParser
from hdlcc.serialization import StateEncoder, jsonObjectHook
from hdlcc.tests.utils import assertCountEqual, writeListToFile

_logger = logging.getLogger(__name__)

_FILENAME = 'source.v'

with such.A('Verilog source file object') as it:
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    with it.having('a module code'):
        @it.has_setup
        def setup():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)
            it._code = """
module clock_divider
    #(parameter DIVISION = 5)
    (// Usual ports
    input clk,
    input rst,
    // Output clock divided
    output       clk_div);
""".splitlines()

            writeListToFile(_FILENAME, it._code)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should('parse a file without errors')  # type: ignore
        def test():
            it.source = VerilogParser(_FILENAME)

        @it.should('return its design units')  # type: ignore
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.debug("Design units: %s", design_units)
            it.assertCountEqual(
                design_units,
                [DesignUnit(owner=it.source.filename,
                            name=Identifier('clock_divider', case_sensitive=True),
                            type_=DesignUnitType.entity,
                            locations={(0, None),})])

        @it.should('return no dependencies')  # type: ignore
        def test():
            it.assertEqual(it.source.getDependencies(), [])

        @it.should('return source modification time')  # type: ignore
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

        @it.should('return no libraries')  # type: ignore
        def test():
            it.assertEqual(it.source.getLibraries(), [])

        @it.should('report as equal after recovering from cache via json')  # type: ignore
        def test():
            state = json.dumps(it.source, cls=StateEncoder)
            _logger.info("State before: %s", state)
            recovered = json.loads(state, object_hook=jsonObjectHook)
            it.assertEqual(it.source.filename, recovered.filename)

    with it.having('a package code'):
        @it.has_setup
        def setup():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)
            it._code = """
package msgPkg;
  integer  errCnt  = 0;
  integer  warnCnt = 0;
endpackage
""".splitlines()

            writeListToFile(_FILENAME, it._code)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should('return its design units')  # type: ignore
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.debug("Design units: %s", design_units)
            it.assertCountEqual(
                design_units,
                [DesignUnit(owner=it.source.filename,
                            name=Identifier('msgPkg', case_sensitive=True),
                            type_=DesignUnitType.package,
                            locations={(0, None),})])

        @it.should('return no libraries')  # type: ignore
        def test():
            it.assertEqual(it.source.getLibraries(), [])

it.createTests(globals())
