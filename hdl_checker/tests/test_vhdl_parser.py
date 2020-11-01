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

# pylint: disable=function-redefined
# pylint: disable=missing-docstring
# pylint: disable=protected-access

import json
import logging
import os
import os.path as p
import time

from nose2.tools import such  # type: ignore

from hdl_checker.tests import assertSameFile, writeListToFile

from hdl_checker.parsers.elements.dependency_spec import RequiredDesignUnit
from hdl_checker.parsers.elements.design_unit import VhdlDesignUnit
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.parsers.vhdl_parser import VhdlParser
from hdl_checker.path import Path
from hdl_checker.serialization import StateEncoder, jsonObjectHook
from hdl_checker.types import DesignUnitType

_logger = logging.getLogger(__name__)

TEST_SUPPORT_PATH = p.join(os.environ["TOX_ENV_DIR"], "tmp")
_FILENAME = p.join(TEST_SUPPORT_PATH, "source.vhd")

such.unittest.TestCase.maxDiff = None


def _DependencySpec(owner, name, library, locations=None):
    if library is not None:
        library = Identifier(library, case_sensitive=False)
    return RequiredDesignUnit(
        owner=owner,
        name=Identifier(name, case_sensitive=False),
        library=library,
        locations=locations,
    )


with such.A("VHDL source file object") as it:

    it.assertSameFile = assertSameFile(it)

    with it.having("an entity code"):

        @it.has_setup
        def setup():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)
            it._code = [
                "library ieee ;",
                "use ieee.std_logic_1164.all;",
                "USE  IEEE.STD_LOGIC_ARITH.ALL;",
                "",
                "library work;",
                " use work.package_with_constants;",
                " use  work.cherry_pick.one;",
                "use work.cherry_pick.two;",
                "",
                "-- library foo;",
                "library lib1,lib2;",
                "library lib3, lib4;",
                "library lib5; library lib6;",
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
                "end clock_divider;",
            ]

            writeListToFile(_FILENAME, it._code)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should("parse a file without errors")
        def test():
            it.source = VhdlParser(Path(_FILENAME))

        @it.should("return its entities")  # type: ignore
        def test():
            design_units = list(it.source.getDesignUnits())
            _logger.info("Design units: %s", design_units)
            it.assertNotEqual(design_units, None, "No design_units units found")
            it.assertCountEqual(
                design_units,
                [
                    VhdlDesignUnit(
                        owner=it.source.filename,
                        type_=DesignUnitType.entity,
                        name="clock_divider",
                        locations={(14, 7)},
                    )
                ],
            )

        @it.should("parse its libraries")  # type: ignore
        def test():
            libraries = it.source.getLibraries()
            _logger.info("Libraries found: %s", ", ".join([repr(x) for x in libraries]))

            it.assertCountEqual(
                libraries, ["ieee", "lib1", "lib2", "lib3", "lib4", "lib5", "lib6"]
            )

        @it.should("return its dependencies")  # type: ignore
        def test():
            it.assertCountEqual(
                it.source.getDependencies(),
                [
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_1164",
                        locations=[(1, 4)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_arith",
                        locations=[(2, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="package_with_constants",
                        locations=[(5, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="cherry_pick",
                        locations=[(6, 6), (7, 4)],
                    ),
                ],
            )

        @it.should("return source modification time")  # type: ignore
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

        @it.should("return updated dependencies")  # type: ignore
        def test():
            code = list(it._code)

            code.insert(0, "library some_library;")
            code.insert(1, "    use some_library.some_package;")
            writeListToFile(_FILENAME, code)

            time.sleep(0.1)

            it.assertCountEqual(
                it.source.getDependencies(),
                [
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_1164",
                        locations=[(3, 4)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_arith",
                        locations=[(4, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="package_with_constants",
                        locations=[(7, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="some_library",
                        name="some_package",
                        locations=[(1, 8)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="cherry_pick",
                        locations=[(8, 6), (9, 4)],
                    ),
                ],
            )

        @it.should("handle implicit libraries")  # type: ignore
        def test():
            code = list(it._code)
            code.insert(0, "    use work.another_package;")
            writeListToFile(_FILENAME, code)

            it.assertCountEqual(
                it.source.getDependencies(),
                [
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_1164",
                        locations=[(2, 4)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_arith",
                        locations=[(3, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="package_with_constants",
                        locations=[(6, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="another_package",
                        locations=[(0, 8)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="cherry_pick",
                        locations=[(7, 6), (8, 4)],
                    ),
                ],
            )

        @it.should("handle libraries without packages")  # type: ignore
        def test():
            code = list(it._code)
            code.insert(0, "library remove_me;")
            writeListToFile(_FILENAME, code)

            it.assertCountEqual(
                it.source.getDependencies(),
                [
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_1164",
                        locations=[(2, 4)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library="ieee",
                        name="std_logic_arith",
                        locations=[(3, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="package_with_constants",
                        locations=[(6, 5)],
                    ),
                    _DependencySpec(
                        owner=Path(_FILENAME),
                        library=None,
                        name="cherry_pick",
                        locations=[(7, 6), (8, 4)],
                    ),
                ],
            )

        @it.should(  # type: ignore
            "report as equal after recovering from cache via json"
        )
        def test():
            state = json.dumps(it.source, cls=StateEncoder)
            _logger.info("State before: %s", state)
            recovered = json.loads(state, object_hook=jsonObjectHook)
            it.assertEqual(it.source.filename, recovered.filename)

    with it.having("a package code"):

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
                '    constant SOME_STRING_CONSTANT  : string := "Hello";',
                "    constant ANOTHER_CONSTANT : string := work.foo.bar;",
                "",
                "    constant SOME_STRING : string := "
                "basic_library.very_common_pkg.VIM_HDL_VERSION;",
                "end;",
                "",
                "package body package_with_constants is",
                "",
                "end package body;",
                "",
                "package body package_body_only is",
                "",
                "end package body package_body_only;",
            ]

            writeListToFile(_FILENAME, it._code)
            it._source_mtime = os.path.getmtime(_FILENAME)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should("parse a file without errors")  # type: ignore
        def test():
            it.source = VhdlParser(Path(_FILENAME))

        @it.should("return the names of the packages found")  # type: ignore
        def test():
            it.assertCountEqual(
                list(it.source.getDesignUnits()),
                [
                    VhdlDesignUnit(
                        owner=it.source.filename,
                        type_=DesignUnitType.package,
                        name="package_with_constants",
                        locations={(7, 8)},
                    )
                ],
            )

        @it.should("return its dependencies")  # type: ignore
        def test():  # type: () -> None
            it.assertCountEqual(
                it.source.getDependencies(),
                [
                    _DependencySpec(
                        name="std_logic_1164",
                        library="ieee",
                        owner=it.source.filename,
                        locations={(1, 4)},
                    ),
                    _DependencySpec(
                        name="std_logic_arith",
                        library="ieee",
                        owner=it.source.filename,
                        locations={(2, 4)},
                    ),
                    _DependencySpec(
                        name="std_logic_unsigned",
                        library="ieee",
                        owner=it.source.filename,
                        locations={(3, 4)},
                    ),
                    _DependencySpec(
                        name="foo",
                        library=None,
                        owner=it.source.filename,
                        locations={(11, 42)},
                    ),
                    _DependencySpec(
                        name="very_common_pkg",
                        library="basic_library",
                        owner=it.source.filename,
                        locations={(13, 37)},
                    ),
                    _DependencySpec(
                        name="package_with_constants",
                        library=None,
                        owner=it.source.filename,
                        locations={(16, 0)},
                    ),
                    _DependencySpec(
                        name="package_body_only",
                        library=None,
                        owner=it.source.filename,
                        locations={(20, 0)},
                    ),
                ],
            )

        @it.should("return source modification time")  # type: ignore
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())

    with it.having("a context code"):

        @it.has_setup
        def setup():
            it._code = [
                "context context_name is",
                "  library lib0;",
                "  use lib0.pkg0.all;",
                "  use lib0.pkg1.name1;",
                "  library lib1;",
                "  use lib1.all;",
                "end context;",
            ]

            writeListToFile(_FILENAME, it._code)
            it._source_mtime = os.path.getmtime(_FILENAME)

        @it.has_teardown
        def teardown():
            if os.path.exists(_FILENAME):
                os.remove(_FILENAME)

        @it.should("create the object with no errors")  # type: ignore
        def test():
            it.source = VhdlParser(Path(_FILENAME))

        @it.should("return the names of the packages found")  # type: ignore
        def test():
            it.assertCountEqual(
                list(it.source.getDesignUnits()),
                [
                    VhdlDesignUnit(
                        owner=it.source.filename,
                        type_=DesignUnitType.context,
                        name="context_name",
                        locations={(0, 7)},
                    )
                ],
            )

        @it.should("return its dependencies")  # type: ignore
        def test():  # type: () -> None
            it.assertCountEqual(
                it.source.getDependencies(),
                [
                    _DependencySpec(
                        owner=it.source.filename,
                        name="pkg0",
                        library="lib0",
                        locations={(2, 6)},
                    ),
                    _DependencySpec(
                        owner=it.source.filename,
                        name="pkg1",
                        library="lib0",
                        locations={(3, 6)},
                    ),
                    _DependencySpec(
                        owner=it.source.filename,
                        name="all",
                        library="lib1",
                        locations={(5, 6)},
                    ),
                ],
            )

        @it.should("return source modification time")  # type: ignore
        def test():
            it.assertEqual(os.path.getmtime(_FILENAME), it.source.getmtime())


it.createTests(globals())
