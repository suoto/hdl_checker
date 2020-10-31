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

# pylint: disable=function-redefined, missing-docstring, protected-access

import logging
import re

from nose2.tools import such  # type: ignore
from nose2.tools.params import params  # type: ignore

import hdl_checker.static_check as static_check
from hdl_checker.diagnostics import DiagType, LibraryShouldBeOmited, StaticCheckerDiag

_logger = logging.getLogger(__name__)

with such.A("hdl_checker project") as it:

    @it.should("not repeat an object in the results")
    def test():
        text = ["", "library ieee;", "", "library ieee;", ""]

        it.assertDictEqual(
            {"ieee": {"end": 12, "lnum": 1, "start": 8, "type": "library"}},
            static_check._getObjectsFromText(text),
        )

    @it.should("not scan after specific end of scan delimiters")  # type: ignore
    @params(
        [" u0 : some_unit", "   generic map ("],
        [" u0 : some_unit", "   port map ("],
        [" u0 : entity work.some_unit"],
        [" p0 : process"],
        [" process(clk)"],
    )
    def test(case, parm):
        _logger.info("Running test case '%s'", case)
        text = ["library foo;"] + parm + ["library bar;"]

        it.assertDictEqual(
            {"foo": {"end": 11, "lnum": 0, "start": 8, "type": "library"}},
            static_check._getObjectsFromText(text),
        )

    @it.should("extract comment tags")  # type: ignore
    @params(
        " -- XXX: some warning",
        " -- TODO: something to do",
        " -- FIXME: something to fix",
    )
    def test(case, parm):
        _logger.info("Running test case '%s'", case)
        expected = re.sub(r"\s*--\s*", "", parm)

        text = [
            "library ieee;",
            "    use ieee.std_logic_1164.all;",
            "    use ieee.numeric_std.all;",
            "library basic_library;",
            "entity foo is",
            "",
            parm,
            "",
            "    generic (",
            "        DIVIDER_A : integer := 10;",
            "        DIVIDER_B : integer := 20",
            "    );",
            "    port (",
            "        clk_in_a : in std_logic;",
            "        clk_out_a : out std_logic;",
            "",
            "        clk_in_b : in std_logic;",
            "        clk_out_b : out std_logic",
            "",
            "    );",
            "end foo;",
            "",
            "architecture foo of foo is",
            "begin",
            "clk_out_a <= not clk_in_a;",
            "-- clk_out_b <= not clk_in_b;",
            "end architecture foo;",
        ]

        it.assertCountEqual(
            [
                StaticCheckerDiag(
                    line_number=6,
                    column_number=4,
                    severity=DiagType.STYLE_INFO,
                    text=expected,
                )
            ],
            static_check._getCommentTags(text),
        )

    @it.should("get misc checks")  # type: ignore
    def test():
        text = [
            "entity foo is",
            "    port (",
            "        clk_in_a : in std_logic;",
            "        clk_out_a : out std_logic;",
            "",
            "        clk_in_b : in std_logic;",
            "        clk_out_b : out std_logic",
            "",
            "    );",
            "end foo;",
        ]

        objects = static_check._getObjectsFromText(text)

        it.assertCountEqual([], static_check._getMiscChecks(objects))

    with it.having("an entity-architecture pair"):

        @it.has_setup
        def setup():
            it.text = [
                "library ieee;",
                "    use ieee.std_logic_1164.all;",
                "    use ieee.numeric_std.all;",
                "library work;",
                "    use work.some_package.all;",
                "library basic_library;",
                "entity foo is",
                "    generic (",
                "        DIVIDER_A : integer := 10;",
                "        DIVIDER_B : integer := 20",
                "    );",
                "    port (",
                "        clk_in_a : in std_logic;",
                "        clk_out_a : out std_logic;",
                "",
                "        clk_in_b : in std_logic;",
                "        clk_out_b : out std_logic",
                "",
                "    );",
                "end foo;",
                "",
                "architecture foo of foo is",
                "begin",
                "clk_out_a <= not clk_in_a;",
                "-- clk_out_b <= not clk_in_b;",
                "end architecture foo;",
            ]

        @it.should("get VHDL objects from an entity-architecture pair")  # type: ignore
        def test():
            it.assertDictEqual(
                {
                    "DIVIDER_A": {"end": 18, "lnum": 8, "start": 8, "type": "generic"},
                    "DIVIDER_B": {"end": 18, "lnum": 9, "start": 8, "type": "generic"},
                    "basic_library": {
                        "end": 21,
                        "lnum": 5,
                        "start": 8,
                        "type": "library",
                    },
                    "clk_in_a": {"end": 17, "lnum": 12, "start": 8, "type": "port"},
                    "clk_in_b": {"end": 17, "lnum": 15, "start": 8, "type": "port"},
                    "clk_out_a": {"end": 18, "lnum": 13, "start": 8, "type": "port"},
                    "clk_out_b": {"end": 18, "lnum": 16, "start": 8, "type": "port"},
                    "ieee": {"end": 12, "lnum": 0, "start": 8, "type": "library"},
                    "work": {"end": 12, "lnum": 3, "start": 8, "type": "library"},
                },
                static_check._getObjectsFromText(it.text),
            )

        @it.should("get misc checks")  # type: ignore
        def test():
            objects = static_check._getObjectsFromText(it.text)

            it.assertCountEqual(
                [LibraryShouldBeOmited(line_number=3, column_number=8, library="work")],
                static_check._getMiscChecks(objects),
            )

        @it.should("get unused VHDL objects")  # type: ignore
        def test():
            objects = static_check._getObjectsFromText(it.text)
            it.assertCountEqual(
                ["basic_library", "DIVIDER_A", "DIVIDER_B", "clk_in_b", "clk_out_b"],
                static_check._getUnusedObjects(it.text, objects),
            )

    with it.having("a package-package body pair"):

        @it.has_setup
        def setup():
            it.text = [
                "library ieee;",
                "package very_common_pkg is",
                '    constant VIM_HDL_VERSION : string := "0.1";',
                "end package;",
                "package body very_common_pkg is",
                "end package body;",
            ]

        @it.should("get VHDL objects from a package-package body pair")  # type: ignore
        def test():

            it.assertDictEqual(
                {"ieee": {"end": 12, "lnum": 0, "start": 8, "type": "library"}},
                static_check._getObjectsFromText(it.text),
            )

        @it.should("get unused VHDL objects")  # type: ignore
        def test():
            objects = static_check._getObjectsFromText(it.text)
            it.assertCountEqual(
                ["ieee"], static_check._getUnusedObjects(it.text, objects)
            )


it.createTests(globals())
