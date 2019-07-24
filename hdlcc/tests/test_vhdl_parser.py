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
import os.path as p

import six
from nose2.tools import such
from nose2.tools.params import params

import hdlcc
from hdlcc.parsers import DependencySpec, VhdlParser
from hdlcc.serialization import StateEncoder, jsonObjectHook
from hdlcc.utils import writeListToFile

_logger = logging.getLogger(__name__)

TEST_SUPPORT_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
_FILENAME = p.join(TEST_SUPPORT_PATH, 'source.vhd')

such.unittest.TestCase.maxDiff = None

with such.A('VHDL source file object') as it:

    it.assertSameFile = hdlcc.tests.utils.assertSameFile(it)

    if six.PY2:
        # Can't use assertCountEqual for lists of unhashable types.
        # Workaround for https://bugs.python.org/issue10242
        it.assertCountEqual = hdlcc.tests.utils.assertCountEqual(it)


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
                "use work.cherry_pick.one;",
                "use work.cherry_pick.two;",
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
            it.source = VhdlParser(_FILENAME, library='mylibrary')

        @it.should('return its entities')
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.info("Design units: %s", design_units)
            it.assertNotEqual(design_units, None, "No design_units units found")
            it.assertCountEqual([{'type' : 'entity',
                                  'name' : 'clock_divider',
                                  'line_number': 12}],
                                design_units)

        @it.should('parse its libraries')
        def test():
            libraries = it.source.getLibraries()
            _logger.info("Libraries found: %s",
                         ", ".join([repr(x) for x in libraries]))

            it.assertCountEqual(
                ['mylibrary', 'work', 'ieee', 'lib1', 'lib2', 'lib3', 'lib4'],
                libraries)

        @it.should('return its dependencies')
        def test():
            it.assertCountEqual(
                it.source.getDependencies(),
                [DependencySpec(library='ieee', name='std_logic_1164',
                                locations=[(_FILENAME, 1, None),]),
                 DependencySpec(library='ieee', name='std_logic_arith',
                                locations=[(_FILENAME, 2, None),]),
                 DependencySpec(library='mylibrary', name='package_with_constants',
                                locations=[(_FILENAME, 5, None),]),
                 DependencySpec(library='mylibrary', name='cherry_pick',
                                locations=[(_FILENAME, 6, None),
                                           (_FILENAME, 7, None),]),
                 ])


        @it.should('return source modification time')
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

        @it.should('find the matching library of a package')
        @params(
            ('package', 'std_logic_1164', 'ieee'),
            ('package', 'package_with_constants', 'mylibrary'))
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

            it.assertCountEqual(
                it.source.getDependencies(),
                [DependencySpec(library='ieee', name='std_logic_1164',
                                locations=[(_FILENAME, 3, None),]),
                 DependencySpec(library='ieee', name='std_logic_arith',
                                locations=[(_FILENAME, 4, None),]),
                 DependencySpec(library='mylibrary', name='package_with_constants',
                                locations=[(_FILENAME, 7, None),]),
                 DependencySpec(library='some_library', name='some_package',
                                locations=[(_FILENAME, 1, None),]),
                 DependencySpec(library='mylibrary', name='cherry_pick',
                                locations=[(_FILENAME, 8, None),
                                           (_FILENAME, 9, None),]),
                 ])

        @it.should('handle implicit libraries')
        def test():
            code = list(it._code)
            code.insert(0, '    use work.another_package;')
            writeListToFile(_FILENAME, code)

            it.assertCountEqual(
                it.source.getDependencies(),
                [DependencySpec(library='ieee', name='std_logic_1164',
                                locations=[(_FILENAME, 2, None),]),
                 DependencySpec(library='ieee', name='std_logic_arith',
                                locations=[(_FILENAME, 3, None),]),
                 DependencySpec(library='mylibrary', name='package_with_constants',
                                locations=[(_FILENAME, 6, None),]),
                 DependencySpec(library='mylibrary', name='another_package',
                                locations=[(_FILENAME, 0, None),]),
                 DependencySpec(library='mylibrary', name='cherry_pick',
                                locations=[(_FILENAME, 7, None),
                                           (_FILENAME, 8, None),]),
                 ],)

        @it.should('handle libraries without packages')
        def test():
            code = list(it._code)
            code.insert(0, 'library remove_me;')
            writeListToFile(_FILENAME, code)

            it.assertCountEqual(
                it.source.getDependencies(),
                [DependencySpec(library='ieee', name='std_logic_1164',
                                locations=[(_FILENAME, 2, None),]),
                 DependencySpec(library='ieee', name='std_logic_arith',
                                locations=[(_FILENAME, 3, None),]),
                 DependencySpec(library='mylibrary', name='package_with_constants',
                                locations=[(_FILENAME, 6, None),]),
                 DependencySpec(library='mylibrary', name='cherry_pick',
                                locations=[(_FILENAME, 7, None),
                                           (_FILENAME, 8, None),]),
                 ])


        @it.should('report as equal after recovering from cache via json')
        def test():
            state = json.dumps(it.source, cls=StateEncoder)
            _logger.info("State before: %s", state)
            recovered = json.loads(state, object_hook=jsonObjectHook)
            it.assertEqual(it.source.filename, recovered.filename)

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
            it.assertCountEqual(
                list(it.source.getDesignUnits()),
                [{'type' : 'package',
                  'name' : 'package_with_constants',
                  'line_number': 7}])

        @it.should('return its dependencies')
        def test():
            it.assertCountEqual(
                it.source.getDependencies(),
                [DependencySpec(library='ieee', name='std_logic_1164',
                                locations={(it.source.filename, 1, None)}),
                 DependencySpec(library='ieee', name='std_logic_arith',
                                locations={(it.source.filename, 2, None)}),
                 DependencySpec(library='ieee', name='std_logic_unsigned',
                                locations={(it.source.filename, 3, None)}),
                 DependencySpec(library='basic_library', name='very_common_pkg',
                                locations={(it.source.filename, 12, None)}),
                 DependencySpec(library='work', name='package_with_constants',
                                locations={(it.source.filename, 15, None)})])

        @it.should('return source modification time')
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

it.createTests(globals())
