
from nose2.tools import such
from testfixtures import LogCapture
import logging
import os

from hdlcc.compilers import GHDL as Compiler
from hdlcc.source_file import VhdlSourceFile

_logger = logging.getLogger(__name__)

_VHD_SAMPLE_ENTITY = """library ieee;
use ieee.std_logic_1164.all;

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

begin

end clock_divider;
""".splitlines()

with such.A('Compiler compiler object') as it:
    it._ok_file = 'some_file.vhd'
    it._error_file = 'some_file_with_error.vhd'
    with it.having('its binary executable'):
        @it.has_setup
        def setup():
            it.builder = Compiler('_ghdl_build')
        @it.has_teardown
        def teardown():
            os.remove(it._ok_file)
            os.remove(it._error_file)

        @it.should('pass environment check')
        def test(case):
            it.builder.checkEnvironment()

        @it.should('compile some source')
        def test(case):
            open(it._ok_file, 'w').write('\n'.join(_VHD_SAMPLE_ENTITY))
            source = VhdlSourceFile(it._ok_file)
            records, rebuilds = it.builder.build(source)
            for record in records:
                it.assertTrue(record['error_type'] != 'E',
                              'This source should not generate errors. '
                              'Error record: ' + str(record))

        @it.should('catch an error')
        def test(case):
            open(it._error_file, 'w').write('\n'.join(['hello\n'] + _VHD_SAMPLE_ENTITY))
            source = VhdlSourceFile(it._error_file)
            records, rebuilds = it.builder.build(source)
            it.assertTrue(('E', '1') in \
                    [(x['error_type'], x['line_number']) for x in records],
                    'Compiler failed to report an error at the first line')
            for record in records:
                _logger.info(record)

it.createTests(globals())

