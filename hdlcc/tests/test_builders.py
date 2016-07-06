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

import logging
import os
import os.path as p
import shutil as shell
import time
from nose2.tools import such
import hdlcc.builders
import hdlcc.utils as utils
from hdlcc.parsers.vhdl_source_file import VhdlSourceFile


BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = os.environ.get('BUILDER_PATH', p.expanduser("~/builders/ghdl/bin/"))
SOURCES_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'sources')

_logger = logging.getLogger(__name__)

with such.A("'%s' builder object" % str(BUILDER_NAME)) as it:
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
            if p.exists('._%s' % BUILDER_NAME):
                shell.rmtree('._%s' % BUILDER_NAME)

        @it.should('pass environment check')
        def test():
            it.builder.checkEnvironment()

        @it.should('compile a VHDL source without errors')
        def test():
            source = VhdlSourceFile(p.join(SOURCES_PATH, 'no_messages.vhd'))
            records, rebuilds = it.builder.build(source)
            it.assertNotIn('E', [x['error_type'] for x in records],
                           'This source should not generate errors.')
            it.assertEqual(rebuilds, [])

        @it.should('catch a known error on a VHDL source')
        def test():
            source = VhdlSourceFile(p.join(SOURCES_PATH,
                                           'source_with_error.vhd'))
            records, rebuilds = it.builder.build(source)

            for record in records:
                _logger.info(record)

            if BUILDER_NAME == 'msim':
                expected = [{
                    'line_number': '21',
                    'error_number': None,
                    'error_message': 'near "EOF": expecting \';\'',
                    'column': None,
                    'error_type': 'E',
                    'checker': 'msim'}]
            elif BUILDER_NAME == 'ghdl':
                expected = [{
                    'line_number': '21',
                    'error_number': None,
                    'error_message': "';' is expected instead of '<EOF>'",
                    'column': '1',
                    'error_type': 'E',
                    'checker': 'ghdl'}]
            elif BUILDER_NAME == 'xvhdl':
                expected = [{
                    'line_number': '21',
                    'error_number': 'VRFC 10-1491',
                    'error_message': 'unexpected EOF ',
                    'column': '',
                    'error_type': 'E',
                    'checker': 'xvhdl'}]

            it.assertEqual(len(records), 1)
            it.assertTrue(utils.samefile(records[0].pop('filename'),
                                         source.filename))
            it.assertEquals(records, expected)

            it.assertEqual(rebuilds, [])

if BUILDER_NAME is not None:
    it.createTests(globals())

