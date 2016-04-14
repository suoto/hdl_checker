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
import os.path as p
import shutil as shell
import time
import hdlcc.builders
import hdlcc.utils as utils
from hdlcc.source_file import VhdlSourceFile


if not hasattr(p, 'samefile'):
    def samefile(file1, file2):
        return os.stat(file1) == os.stat(file2)
else:
    samefile = p.samefile # pylint: disable=invalid-name

BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = os.environ.get('BUILDER_PATH', p.expanduser("~/builders/ghdl/bin/"))

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

_ERRORS = {
    'ghdl' : {'line_number'   : '1',
              'error_number'  : None,
              'error_message' : "entity, architecture, package or "
                                "configuration keyword expected",
              'column'        : '1',
              'error_type'    : 'E',
              'filename'      : 'some_file_with_error.vhd',
              'checker'       : 'ghdl'},
    'msim' : {'line_number'   : '1',
              'error_number'  : None,
              'error_message' : "near \"hello\": syntax error",
              'column'        : None,
              'error_type'    : 'E',
              'filename'      : 'some_file_with_error.vhd',
              'checker'       : 'msim'},
    'xvhdl' : {'line_number'   : '1',
               'error_number'  : 'VRFC 10-1412',
               'error_message' : 'syntax error near hello ',
               'column'        : '',
               'error_type'    : 'E',
               'filename'      : 'some_file_with_error.vhd',
               'checker'       : 'xvhdl'},
    }

with such.A("'%s' builder object" % str(BUILDER_NAME)) as it:
    it._ok_file = 'some_file.vhd'
    it._error_file = 'some_file_with_error.vhd'
    with it.having('its binary executable'):
        @it.has_setup
        def setup():
            it.original_env = os.environ.copy()

            utils.addToPath(BUILDER_PATH)

            cls = hdlcc.builders.getBuilderByName(BUILDER_NAME)
            it.builder = cls('._%s' % BUILDER_NAME)

        @it.has_teardown
        def teardown():
            utils.removeFromPath(BUILDER_PATH)
            os.remove(it._ok_file)
            os.remove(it._error_file)
            if p.exists('._%s' % BUILDER_NAME):
                shell.rmtree('._%s' % BUILDER_NAME)

        @it.should('pass environment check')
        def test():
            it.builder.checkEnvironment()

        @it.should('compile some source without errors')
        def test():
            open(it._ok_file, 'w').write('\n'.join(_VHD_SAMPLE_ENTITY))
            source = VhdlSourceFile(it._ok_file)
            records, rebuilds = it.builder.build(source)
            it.assertNotIn('E', [x['error_type'] for x in records],
                           'This source should not generate errors.')
            it.assertEqual(rebuilds, [])

        @it.should('catch an error')
        def test():
            open(it._error_file, 'w').write('\n'.join(['hello\n'] + _VHD_SAMPLE_ENTITY))
            time.sleep(1)
            source = VhdlSourceFile(it._error_file)
            records, rebuilds = it.builder.build(source)

            for record in records:
                _logger.info(record)

            ref = _ERRORS[BUILDER_NAME]

            # We check everything except the filename. XVHDL returns
            # an absolute path but we should work based on relative
            # paths. Any conversion needed should be handled by the
            # editor client
            for item in ('line_number', 'error_number', 'error_message',
                         'column', 'error_type', 'checker'):
                it.assertIn(ref[item], [x[item] for x in records])

            it.assertIn(
                True,
                [samefile(ref['filename'], x['filename']) for x in records],
                "Mention to file '%s' not found in '%s'" % \
                        (ref['filename'], [x['filename'] for x in records]))

            it.assertEqual(rebuilds, [])

if BUILDER_NAME is not None:
    it.createTests(globals())

