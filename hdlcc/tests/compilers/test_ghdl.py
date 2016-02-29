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

from nose2.tools import such
import logging
import os

if os.environ.get('BUILDER', None) == 'msim':
    from hdlcc.builders import MSim as Builder
    _PATH = "/opt/altera/15.1/modelsim_ase/bin/"
    #  _PATH = "/home/souto/modelsim/modeltech/linux_x86_64/"
else:
    from hdlcc.builders import GHDL as Builder
    _PATH = os.path.expanduser("~/ghdl/bin")

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

with such.A('Builder object') as it:
    it._ok_file = 'some_file.vhd'
    it._error_file = 'some_file_with_error.vhd'
    with it.having('its binary executable'):
        @it.has_setup
        def setup():
            it.original_path = os.environ['PATH']
            os.environ['PATH'] += ':' + _PATH
            it.builder = Builder('_ghdl_build')

        @it.has_teardown
        def teardown():
            os.environ['PATH'] = it.original_path
            os.remove(it._ok_file)
            os.remove(it._error_file)

        @it.should('pass environment check')
        def test():
            it.builder.checkEnvironment()

        @it.should('compile some source')
        def test():
            open(it._ok_file, 'w').write('\n'.join(_VHD_SAMPLE_ENTITY))
            source = VhdlSourceFile(it._ok_file)
            records, _ = it.builder.build(source)
            it.assertNotIn('E', [x['error_type'] for x in records],
                           'This source should not generate errors.')

        @it.should('catch an error')
        def test():
            open(it._error_file, 'w').write('\n'.join(['hello\n'] + _VHD_SAMPLE_ENTITY))
            source = VhdlSourceFile(it._error_file)
            records, _ = it.builder.build(source)
            it.assertIn(('E', '1'),
                        [(x['error_type'], x['line_number']) for x in records],
                        'Builder failed to report an error at the first line')
            for record in records:
                _logger.info(record)

it.createTests(globals())

