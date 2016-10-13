# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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

import os
import logging
from nose2.tools import such
from nose2.tools.params import params
import six

from hdlcc.parsers import VhdlParser
from hdlcc.utils import writeListToFile

_logger = logging.getLogger(__name__)

_FILENAME = 'source.vhd'

with such.A('VHDL source file object') as it:
    # Workaround for Python 2.x and 3.x differences
    if six.PY3:
        it.assertItemsEqual = it.assertCountEqual

    with it.having('an entity code'):
        @it.has_setup
        def setup():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)
            it._code = [
                "library ieee ;",
                "use ieee.std_logic_1164.all;",
                "USE IEEE.STD_LOGIC_ARITH.ALL;",
                "",
                "library work;",
                "use work.package_with_constants;",
                "",
                "library lib1,lib2;",
                "library lib3, lib4;",
                "",
                "entity clock_divider is",
                "    generic (",
                "        DIVIDER : integer := 10",
                "    );",
                "    port (",
                "        reset : in std_logic;",
                "        clk_input : in  std_logic;",
                "        clk_output : out std_logic",
                "    );",
                "end clock_divider;",
                "",
                "architecture clock_divider of clock_divider is",
                "",
                "begin",
                "",
                "end clock_divider;"]

            writeListToFile(_FILENAME, it._code)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should('parse a file without errors')
        def test():
            it.source = VhdlParser(_FILENAME)

        @it.should('return its entities')
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.info("Design units: %s", design_units)
            it.assertNotEqual(design_units, None, "No design_units units found")
            it.assertItemsEqual([{'type' : 'entity', 'name' : 'clock_divider'}],
                                design_units)

        @it.should('parse its libraries')
        def test():
            libraries = it.source.getLibraries()
            _logger.info("Libraries found: %s",
                         ", ".join([repr(x) for x in libraries]))

            it.assertItemsEqual(
                ['work', 'ieee', 'lib1', 'lib2', 'lib3', 'lib4'],
                libraries)

        @it.should('return its dependencies')
        def test():
            dependencies = it.source.getDependencies()
            _logger.info("Dependencies: %s", dependencies)
            it.assertNotEqual(dependencies, None, "No dependencies found")
            it.assertItemsEqual(
                [{'unit': 'std_logic_1164', 'library': 'ieee'},
                 {'unit': 'std_logic_arith', 'library': 'ieee'},
                 {'unit': 'package_with_constants', 'library': 'work'}],
                dependencies)

        @it.should('return source modification time')
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

        @it.should('find the matching library of a package')
        @params(
            ('package', 'std_logic_1164', 'ieee'),
            ('package', 'package_with_constants', 'work'))
        def test(case, unit_type, unit_name, result):
            _logger.info("Running test %s", case)
            _logger.info("Unit: '%s' is a '%s'. Expected result is '%s'",
                         unit_name, unit_type, result)

            it.assertEqual(
                result,
                it.source.getMatchingLibrary(unit_type, unit_name))

        @it.should('return updated dependencies')
        def test():
            code = list(it._code)

            code.insert(0, 'library some_library;')
            code.insert(1, '    use some_library.some_package;')
            writeListToFile(_FILENAME, code)

            dependencies = it.source.getDependencies()
            _logger.info("Dependencies: %s", dependencies)
            it.assertNotEqual(dependencies, None, "No dependencies found")
            it.assertItemsEqual(
                [{'unit': 'std_logic_1164', 'library': 'ieee'},
                 {'unit': 'std_logic_arith', 'library': 'ieee'},
                 {'unit': 'some_package', 'library': 'some_library'},
                 {'unit': 'package_with_constants', 'library': 'work'}],
                dependencies)

        @it.should('handle implicit libraries')
        def test():
            code = list(it._code)
            code.insert(0, '    use work.another_package;')
            writeListToFile(_FILENAME, code)

            dependencies = it.source.getDependencies()
            _logger.info("Dependencies: %s", dependencies)
            it.assertNotEqual(dependencies, None, "No dependencies found")
            it.assertItemsEqual(
                [{'unit': 'std_logic_1164', 'library': 'ieee'},
                 {'unit': 'std_logic_arith', 'library': 'ieee'},
                 {'unit': 'another_package', 'library': 'work'},
                 {'unit': 'package_with_constants', 'library': 'work'}],
                dependencies)

        @it.should('handle libraries without packages')
        def test():
            code = list(it._code)
            code.insert(0, 'library remove_me;')
            writeListToFile(_FILENAME, code)

            dependencies = it.source.getDependencies()
            if dependencies:
                _logger.info("Dependencies:")
                for dep in dependencies:
                    _logger.info(str(dep))
            else:
                _logger.warning("No dependencies found")
            it.assertNotEqual(dependencies, None, "No dependencies found")
            it.assertItemsEqual(
                [{'unit': 'std_logic_1164', 'library': 'ieee'},
                 {'unit': 'std_logic_arith', 'library': 'ieee'},
                 {'unit': 'package_with_constants', 'library': 'work'}],
                dependencies)

    with it.having('a package code'):
        @it.has_setup
        def setup():
            it._code = [
                "library ieee;",
                "use ieee.std_logic_1164.all;",
                "use ieee.std_logic_arith.all;",
                "use ieee.std_logic_unsigned.all;",
                "",
                "library basic_library;",
                "",
                "package package_with_constants is",
                "",
                "    constant SOME_INTEGER_CONSTANT : integer := 10;",
                "    constant SOME_STRING_CONSTANT  : string := \"Hello\";",
                "",
                "    constant SOME_STRING : string := " \
                "basic_library.very_common_pkg.VIM_HDL_VERSION;",
                "end;",
                "",
                "package body package_with_constants is",
                "",
                "end package body;",
            ]

            writeListToFile(_FILENAME, it._code)
            it._source_mtime = os.path.getmtime(_FILENAME)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should('parse a file without errors')
        def test():
            it.source = VhdlParser(_FILENAME)

        @it.should('return the names of the packages found')
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.info("Design units: %s", design_units)
            it.assertNotEqual(design_units, None, "No design_units units found")
            it.assertItemsEqual(
                [{'type' : 'package', 'name' : 'package_with_constants'}],
                design_units)

        @it.should('return its dependencies')
        def test():
            dependencies = it.source.getDependencies()
            _logger.info("Dependencies: %s", dependencies)
            it.assertNotEqual(dependencies, None, "No dependencies found")
            it.assertItemsEqual(
                [{'unit': 'std_logic_1164', 'library': 'ieee'},
                 {'unit': 'std_logic_arith', 'library': 'ieee'},
                 {'unit': 'std_logic_unsigned', 'library': 'ieee'},
                 {'unit': 'very_common_pkg', 'library': 'basic_library'},
                 {'unit': 'package_with_constants', 'library': 'work'}],
                dependencies)


        @it.should('return source modification time')
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

it.createTests(globals())


