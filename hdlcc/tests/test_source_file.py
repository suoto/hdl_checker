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

# pylint: disable=function-redefined, missing-docstring, protected-access

import os
import logging
from nose2.tools import such

from hdlcc.source_file import VhdlSourceFile

from hdlcc.tests.utils import writeListToFile

_logger = logging.getLogger(__name__)

_FILENAME = 'source.vhd'

with such.A('VHDL source file object') as it:
    with it.having('an entity code'):
        @it.has_setup
        def setup():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)
            it._code = [
                "library ieee;",
                "use ieee.std_logic_1164.all;",
                "USE IEEE.STD_LOGIC_ARITH.ALL;",
                "",
                "library work;",
                "use work.package_with_constants;",
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
            it.source = VhdlSourceFile(_FILENAME)


        @it.should('return its entities')
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.debug("Design units: %s", design_units)
            it.assertNotEqual(design_units, None, "No design_units units found")
            it.assertItemsEqual([{'type' : 'entity', 'name' : 'clock_divider'}],
                                design_units)

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
            it.source = VhdlSourceFile(_FILENAME)

        @it.should('return the names of the packages found')
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.debug("Design units: %s", design_units)
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


