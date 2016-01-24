
from nose2.tools import such
from testfixtures import LogCapture
import logging
import os

import hdlcc
import sys
sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'python'))
import time

from hdlcc.source_file import VhdlSourceFile

_logger = logging.getLogger(__name__)

_VHD_SAMPLE_ENTITY = """library ieee;
use ieee.std_logic_1164.all;
USE IEEE.STD_LOGIC_ARITH.ALL;

library work;
use work.package_with_constants;

entity clock_divider is
    generic (
        DIVIDER : integer := 10
    );
    port (
        reset : in std_logic;
        clk_input : in  std_logic;
        clk_output : out std_logic
    );

end clock_divider;

architecture clock_divider of clock_divider is

end clock_divider;
""".splitlines()

_VHD_SAMPLE_PACKAGE = """
library ieee;
use ieee.std_logic_1164.all;
use ieee.std_logic_arith.all;
use ieee.std_logic_unsigned.all;

library basic_library;

package package_with_constants is

    constant SOME_INTEGER_CONSTANT : integer := 10;
    constant SOME_STRING_CONSTANT  : string := "Hello";

    constant SOME_STRING : string := basic_library.very_common_pkg.VIM_HDL_VERSION;
end;

package body package_with_constants is

end package body;
""".splitlines()

_FILENAME = 'source.vhd'

with LogCapture() as l:
    with such.A('VHDL source file object') as it:
        with it.having('an entity code'):
            @it.has_setup
            def setup():
                open(_FILENAME, 'w').write('\n'.join(_VHD_SAMPLE_ENTITY))
                it._source_mtime = os.path.getmtime(_FILENAME)

            @it.should('parse a file without errors')
            def test(case):
                it.source = VhdlSourceFile(_FILENAME)

            @it.should('return its design units')
            def test(case):
                design_units = it.source.getDesignUnits()
                _logger.debug("Design units: %s", design_units)
                it.assertNotEqual(design_units, None, "No design_units units found")
                it.assertEqual([{'type' : 'entity', 'name' : 'clock_divider'}], design_units)

            @it.should('return its dependencies')
            def test(case):
                dependencies = it.source.getDependencies()
                _logger.warn("Dependencies: %s", dependencies)
                it.assertNotEqual(dependencies, None, "No dependencies found")
                it.assertEqual(
                    [{'unit': 'std_logic_1164', 'library': 'ieee'},
                     {'unit': 'std_logic_arith', 'library': 'ieee'},
                     {'unit': 'package_with_constants', 'library': 'work'}],
                    dependencies)

            @it.should('return source modification time')
            def test(case):
                it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

            @it.should('detect a file change')
            def test(case):
                time.sleep(0.1)
                with open(_FILENAME, 'w') as source_fd:
                    source_fd.write('\n'.join(_VHD_SAMPLE_ENTITY))
                    source_fd.write('\n')
                    source_fd.flush()
                it.assertTrue(it.source.changed(), "Source change not detected")

            @it.should('detect a file change')
            def test(case):
                time.sleep(0.1)
                with open(_FILENAME, 'w') as source_fd:
                    source_fd.write('\n'.join(_VHD_SAMPLE_ENTITY))
                    source_fd.write('\n')
                    source_fd.flush()
                it.assertTrue(it.source.changed(), "Source change not detected")

        with it.having('a package code'):
            @it.has_setup
            def setup():
                open(_FILENAME, 'w').write('\n'.join(_VHD_SAMPLE_PACKAGE))
                it._source_mtime = os.path.getmtime(_FILENAME)

            @it.should('parse a file without errors')
            def test(case):
                it.source = VhdlSourceFile(_FILENAME)

            @it.should('return its design units')
            def test(case):
                design_units = it.source.getDesignUnits()
                _logger.debug("Design units: %s", design_units)
                it.assertNotEqual(design_units, None, "No design_units units found")
                it.assertEqual([{'type' : 'package', 'name' : 'package_with_constants'}], design_units)

            @it.should('return its dependencies')
            def test(case):
                dependencies = it.source.getDependencies()
                _logger.warn("Dependencies: %s", dependencies)
                it.assertNotEqual(dependencies, None, "No dependencies found")
                it.assertEqual(
                    [{'unit': 'std_logic_1164', 'library': 'ieee'},
                     {'unit': 'std_logic_arith', 'library': 'ieee'},
                     {'unit': 'std_logic_unsigned', 'library': 'ieee'},
                     {'unit': 'very_common_pkg', 'library': 'basic_library'},
                     {'unit': 'package_with_constants', 'library': 'work'}],
                    dependencies)


            @it.should('return source modification time')
            def test(case):
                it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

            @it.should('detect a file change')
            def test(case):
                time.sleep(0.1)
                with open(_FILENAME, 'w') as source_fd:
                    source_fd.write('\n'.join(_VHD_SAMPLE_PACKAGE))
                    source_fd.write('\n')
                    source_fd.flush()
                it.assertTrue(it.source.changed(), "Source change not detected")

            @it.should('detect a file change')
            def test(case):
                time.sleep(0.1)
                with open(_FILENAME, 'w') as source_fd:
                    source_fd.write('\n'.join(_VHD_SAMPLE_PACKAGE))
                    source_fd.write('\n')
                    source_fd.flush()
                it.assertTrue(it.source.changed(), "Source change not detected")

it.createTests(globals())


