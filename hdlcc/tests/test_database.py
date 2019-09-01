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

# pylint: disable=function-redefined
# pylint: disable=invalid-name
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=useless-object-inheritance

import logging
import os.path as p

import six
import unittest2  # type: ignore

from nose2.tools import such  # type: ignore

import hdlcc.types as t
from hdlcc.builders import BuilderName
from hdlcc.database import Database
from hdlcc.parsers import DesignUnitType, VhdlDesignUnit

from hdlcc.tests.utils import (  # sanitizePath,; writeListToFile,
    SourceMock,
    assertCountEqual,
    getTestTempPath,
    setupTestSuport,
    logIterable,
)

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(TEST_TEMP_PATH, "test_config_parser")

such.unittest.TestCase.maxDiff = None


class _SourceMock(SourceMock):
    base_path = TEST_TEMP_PATH


class _Database(Database):
    def updateFromDict(self, config):
        super(_Database, self).updateFromDict(config)
        _logger.debug("State after updating:")
        _logger.debug("- %d paths:", len(self._paths))
        for path, timestamp in self._paths.items():
            dependencies = self._dependencies.get(path, {})
            _logger.debug("  - Path: %s (%f)", path, timestamp)
            _logger.debug("    - library:      : %s", self._libraries.get(path, "?"))
            _logger.debug("    - flags:        : %s", self._flags.get(path, "-"))
            _logger.debug("    - %d dependencies:", len(dependencies))
            for dependency in dependencies:
                _logger.debug("      - %s", dependency)

    #  #  @logCalls
    #  def getDependenciesPaths(self, path):
    #      # type: (...) -> str
    #      return list(super(_Database, self).getDependenciesPaths(path))


def _path(*args):
    # type: (...) -> t.Path
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return t.Path(p.join(TEST_TEMP_PATH, *args))


def _configFromDict(parsed_dict):
    class _ConfigParser(object):  # pylint: disable=too-few-public-methods
        _dict = parsed_dict.copy()

        def parse(self):  # pylint: disable=no-self-use
            return _ConfigParser._dict

    return _ConfigParser()


def _configFromSources(sources):
    srcs = {(x.library, x.filename, ()) for x in sources}

    class _ConfigParser(object):  # pylint: disable=too-few-public-methods
        _dict = {"sources": set(srcs)}

        def parse(self):  # pylint: disable=no-self-use
            return _ConfigParser._dict

    return _ConfigParser()


class TestDatabase(unittest2.TestCase):
    def setUp(self):
        # type: () -> None
        setupTestSuport(TEST_TEMP_PATH)

        self.database = _Database()

        if six.PY2:
            self.assertCountEqual = assertCountEqual(  # pylint: disable=invalid-name
                self
            )

    def test_accepts_empty_ConfigParser(self):
        # type: () -> None
        self.database.accept(_configFromDict({}))

        self.assertEqual(self.database.builder_name, BuilderName.fallback)
        self.assertCountEqual(self.database.paths, ())
        self.assertEqual(self.database.getLibrary("any"), None)
        self.assertEqual(self.database.getFlags(t.Path("any")), ())

    def test_accepts_empty_dict(self):
        # type: () -> None
        self.database.updateFromDict({})

        self.assertEqual(self.database.builder_name, BuilderName.fallback)
        self.assertCountEqual(self.database.paths, ())
        self.assertEqual(self.database.getLibrary("any"), None)
        self.assertEqual(self.database.getFlags(t.Path("any")), ())

    def test_accepts_basic_structure(self):
        # type: () -> None
        _SourceMock(
            filename=_path("foo.vhd"),
            design_units=[{"name": "entity_a", "type": "entity"}],
            dependencies={("some_entity",)},
        )

        _SourceMock(
            filename=_path("oof.vhd"),
            design_units=[{"name": "entity_b", "type": "entity"}],
            dependencies={("some_entity",)},
        )

        info = {
            "builder_name": BuilderName.fallback,
            "sources": {
                ("bar", _path("foo.vhd"), ("baz", "flag")),
                ("ooflib", _path("oof.vhd"), ("oofflag0", "oofflag1")),
            },
            "single_build_flags": {
                "vhdl": ("single_vhd_flag",),
                "verilog": ("single_verilog_flag",),
                "systemverilog": ("single_systemverilog_flag",),
            },
            "global_build_flags": {
                "vhdl": ("global_vhd_flag",),
                "verilog": ("global_verilog_flag",),
                "systemverilog": ("global_systemverilog_flag",),
            },
        }

        self.database.accept(_configFromDict(info))

        self.assertEqual(self.database.builder_name, BuilderName.fallback)
        self.assertCountEqual(self.database.paths, (_path("foo.vhd"), _path("oof.vhd")))
        self.assertEqual(self.database.getLibrary(_path("foo.vhd")), "bar")
        self.assertEqual(self.database.getLibrary(_path("oof.vhd")), "ooflib")
        self.assertEqual(self.database.getFlags(_path("foo.vhd")), ("baz", "flag"))
        self.assertEqual(
            self.database.getFlags(_path("oof.vhd")), ("oofflag0", "oofflag1")
        )

        logIterable(
            "Design units:",
            self.database.getDesignUnitsByPath(_path("foo.vhd")),
            _logger.info,
        )

        self.assertCountEqual(
            self.database.getDesignUnitsByPath(_path("foo.vhd")),
            {
                VhdlDesignUnit(
                    owner=_path("foo.vhd"),
                    name="entity_a",
                    type_=DesignUnitType.entity,
                    locations={(3, None)},
                )
            },
        )

        # VHDL world, should find regardless of lower or upper case
        self.assertCountEqual(
            self.database.findPathsByDesignUnit(
                VhdlDesignUnit(t.Path(""), DesignUnitType.entity, "entity_a")
            ),
            {_path("foo.vhd")},
        )

        self.assertCountEqual(
            self.database.findPathsByDesignUnit(
                VhdlDesignUnit(t.Path(""), DesignUnitType.entity, "ENTITY_A")
            ),
            {_path("foo.vhd")},
        )

    def test_update_info_if_source_changed(self):
        # type: () -> None
        self.test_accepts_basic_structure()

        # Make sure the env is sane before actually testing
        it.assertTrue(p.exists(_path("foo.vhd")))
        timestamp = p.getmtime(_path("foo.vhd"))

        # SourceMock object writes a dummy VHDL, that should cause the
        # timestamp to change
        _SourceMock(
            filename=_path("foo.vhd"),
            design_units=[{"name": "entity_b", "type": "entity"}],
            dependencies=[],
        )

        it.assertNotEqual(
            timestamp, p.getmtime(_path("foo.vhd")), "Timestamp should've changed"
        )

        self.assertCountEqual(
            self.database.getDesignUnitsByPath(_path("foo.vhd")),
            [
                VhdlDesignUnit(
                    owner=_path("foo.vhd"),
                    name="entity_b",
                    type_=DesignUnitType.entity,
                    locations={(0, None)},
                )
            ],
        )

        self.assertCountEqual(
            self.database.findPathsByDesignUnit(
                VhdlDesignUnit(t.Path(""), DesignUnitType.entity, "entity_a")
            ),
            (),
        )

        self.assertCountEqual(
            self.database.findPathsByDesignUnit(
                VhdlDesignUnit(t.Path(""), DesignUnitType.entity, "entity_B")
            ),
            [_path("foo.vhd"), _path("oof.vhd")],
        )


with such.A("database") as it:
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    @it.has_setup
    def setup():
        it.database = _Database()

    #  @it.has_teardown
    #  def teardown():
    #      del it.database
    #      #  it.database.reset()

    with it.having("only direct dependencies"):

        @it.has_setup
        def setup():
            # type: () -> None

            it.sources = {
                _SourceMock(
                    filename=_path("entity_a.vhd"),
                    design_units=[{"name": "entity_a", "type": "entity"}],
                    dependencies=(
                        ("ieee", "numeric_std.all"),
                        ("common_dep",),
                        ("direct_dep_a",),
                        ("direct_dep_b",),
                    ),
                ),
                _SourceMock(
                    filename=_path("direct_dep_a.vhd"),
                    design_units=[
                        {"name": "direct_dep_a", "type": "entity"},
                        {"name": "side_effect_entity", "type": "entity"},
                    ],
                    dependencies=(("common_dep",), ("indirect_dep",)),
                ),
                _SourceMock(
                    filename=_path("direct_dep_b.vhd"),
                    design_units=[{"name": "direct_dep_b", "type": "entity"}],
                    dependencies=[("work", "common_dep")],
                ),
                _SourceMock(
                    filename=_path("indirect_dep.vhd"),
                    design_units=[
                        {"name": "indirect_dep", "type": "package"},
                        {"name": "indirect_dep", "type": "package body"},
                        {"name": "side_effect_package", "type": "package"},
                    ],
                    dependencies=[("work", "common_dep")],
                ),
                _SourceMock(
                    filename=_path("common_dep.vhd"),
                    design_units=[
                        {"name": "common_dep", "type": "package"},
                        {"name": "common_dep", "type": "package body"},
                    ],
                ),
                _SourceMock(
                    filename=_path("not_a_dependency.vhd"),
                    design_units=[{"name": "not_a_dependency", "type": "package"}],
                    dependencies=(("common_dep",), ("indirect_dep",)),
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            it.database.reset()

        @it.should("get correct dependencies of entity_a.vhd")
        def test():
            # type: () -> None
            path = _path("entity_a.vhd")
            deps = it.database.getDependenciesPaths(path)

            logIterable("Dependencies", deps, _logger.info)

            # Indirect dependencies should always come first
            it.assertCountEqual(
                deps,
                {
                    _path("common_dep.vhd"),
                    _path("indirect_dep.vhd"),
                    _path("direct_dep_a.vhd"),
                    _path("direct_dep_b.vhd"),
                },
            )

        @it.should("get correct build sequence of entity_a.vhd")  # type: ignore
        def test():
            # type: () -> None
            sequence = tuple(it.database.getBuildSequence(_path("entity_a.vhd")))

            logIterable("Build sequence", sequence, _logger.info)

            # entity_a
            # '- common_dep
            # '- direct_dep_a
            #    '- common_dep
            #    '- indirect_dep
            # '- direct_dep_b
            #    '- common_dep

            common_dep = ("work", _path("common_dep.vhd"))
            indirect_dep = ("work", _path("indirect_dep.vhd"))
            direct_dep_a = ("work", _path("direct_dep_a.vhd"))
            direct_dep_b = ("work", _path("direct_dep_a.vhd"))

            # First item must be common dep
            it.assertEqual(sequence[0], common_dep)

            # indirect_dep must come before direct_dep_a
            it.assertIn(indirect_dep, sequence)
            it.assertIn(direct_dep_a, sequence)
            it.assertTrue(sequence.index(indirect_dep) < sequence.index(direct_dep_a))

            # If conditions above are respected, direct_dep_b can be anywhere
            it.assertIn(direct_dep_b, sequence)

        @it.should("get correct dependencies of indirect_dep.vhd")  # type: ignore
        def test():
            path = _path("indirect_dep.vhd")
            deps = it.database.getDependenciesPaths(path)

            logIterable("Dependencies", deps, _logger.info)

            it.assertCountEqual(deps, {_path("common_dep.vhd")})

    with it.having("direct circular dependencies between 2 sources"):

        @it.has_setup
        def setup():
            # type: () -> None
            it.sources = {
                _SourceMock(
                    filename=_path("unit_a.vhd"),
                    design_units=[{"name": "unit_a", "type": "entity"}],
                    dependencies=[("work", "unit_b")],
                ),
                _SourceMock(
                    filename=_path("unit_b.vhd"),
                    design_units=[{"name": "unit_b", "type": "entity"}],
                    dependencies=[("work", "unit_a")],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            it.database.reset()

        @it.should("handle both sides")  # type: ignore
        def test():
            it.assertCountEqual(
                it.database.getDependenciesPaths(_path("unit_a.vhd")),
                {_path("unit_b.vhd")},
            )

            it.assertCountEqual(
                it.database.getDependenciesPaths(_path("unit_b.vhd")),
                {_path("unit_a.vhd")},
            )

    with it.having("multilevel circular dependencies"):

        @it.has_setup
        def setup():
            it.sources = {
                _SourceMock(
                    filename=_path("unit_a.vhd"),
                    design_units=[{"name": "unit_a", "type": "entity"}],
                    dependencies=[("work", "unit_b")],
                ),
                _SourceMock(
                    filename=_path("unit_b.vhd"),
                    design_units=[{"name": "unit_b", "type": "entity"}],
                    dependencies=[("work", "unit_c")],
                ),
                _SourceMock(
                    filename=_path("unit_c.vhd"),
                    design_units=[{"name": "unit_c", "type": "entity"}],
                    dependencies=[("work", "unit_d")],
                ),
                _SourceMock(
                    filename=_path("unit_d.vhd"),
                    design_units=[{"name": "unit_d", "type": "entity"}],
                    dependencies=[("work", "unit_a")],
                ),
                _SourceMock(
                    filename=_path("not_a_dependency.vhd"),
                    design_units=[{"name": "not_a_dependency", "type": "package"}],
                    dependencies=[("indirect_dep",), ("common_dep",)],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            it.database.reset()

        @it.should("report all but the source in question")  # type: ignore
        def test():
            # type: () -> None
            it.assertCountEqual(
                it.database.getDependenciesPaths(_path("unit_a.vhd")),
                {_path("unit_b.vhd"), _path("unit_c.vhd"), _path("unit_d.vhd")},
            )

            it.assertCountEqual(
                it.database.getDependenciesPaths(_path("unit_b.vhd")),
                {_path("unit_a.vhd"), _path("unit_c.vhd"), _path("unit_d.vhd")},
            )

            it.assertCountEqual(
                it.database.getDependenciesPaths(_path("unit_c.vhd")),
                {_path("unit_a.vhd"), _path("unit_b.vhd"), _path("unit_d.vhd")},
            )

            it.assertCountEqual(
                it.database.getDependenciesPaths(_path("unit_d.vhd")),
                {_path("unit_a.vhd"), _path("unit_b.vhd"), _path("unit_c.vhd")},
            )

    with it.having("source only depending on itself"):

        @it.has_setup
        def setup():
            it.sources = {
                _SourceMock(
                    filename=_path("unit_a.vhd"),
                    design_units=[{"name": "unit_a", "type": "entity"}],
                    dependencies=[("work", "unit_a")],
                ),
                _SourceMock(
                    filename=_path("not_a_dependency.vhd"),
                    design_units=[{"name": "not_a_dependency", "type": "package"}],
                    dependencies=[("indirect_dep",), ("common_dep",)],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            it.database.reset()

        @it.should("report all but the source in question")  # type: ignore
        def test():
            # type: () -> None
            deps = it.database.getDependenciesPaths(_path("unit_a.vhd"))

            it.assertCountEqual(deps, ())

        # Create the following setup:
        # - Library 'lib' with 'pkg_in_lib':
        #   - All sources using 'lib.pkg_in_lib' should work
        #   - Sources inside 'lib' should be able to use 'lib.pkg_in_lib' or
        #     'work.pkg_in_lib'
        # - Source without library set, with entity 'pkg_in_indirect'
        #   - Every source using this package should use
        #     'indirect.pkg_in_indirect'
        #   - At least one source in 'indirect' referring to 'pkg_in_indirect'
        #     as 'work.pkg_in_indirect'
        # - Source without library set, with entity 'pkg_in_implicit'
        #   - Every source using this package should use
        #     'implicit.pkg_in_implicit'

        # Test that we can infer the correct libraries:
        # If the library is not set for the a given path, try to guess it by
        # (1) given every design unit defined in this file
        # (2) search for every file that also depends on it and
        # (3) identify which library is used
        # If all of them converge on the same library name, just use that.
        # If there's no agreement, use the library that satisfies the path
        # in question but warn the user that something is not right

    with it.having("all libraries set"):

        @it.has_setup
        def setup():
            # type: () -> None

            it.sources = {
                _SourceMock(
                    filename=_path("top.vhd"),
                    library="lib",
                    design_units=[{"name": "top", "type": "entity"}],
                    dependencies=[
                        ("ieee", "std_logic_unsigned"),
                        ("lib", "some_package"),
                        ("lib", "some_entity"),
                    ],
                ),
                _SourceMock(
                    filename=_path("some_entity.vhd"),
                    library="lib",
                    design_units=[{"name": "some_entity", "type": "entity"}],
                ),
                _SourceMock(
                    filename=_path("some_package.vhd"),
                    library="lib",
                    design_units=[{"name": "some_package", "type": "package"}],
                ),
                _SourceMock(
                    filename=_path("not_a_dependency.vhd"),
                    design_units=[{"name": "not_a_dependency", "type": "package"}],
                    dependencies=[("lib", "top")],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            it.database.reset()

        @it.should("get the correct build sequence")  # type: ignore
        def test():
            # type: () -> None
            sequence = tuple(it.database.getBuildSequence(_path("top.vhd")))

            logIterable("Build sequence", sequence, _logger.warning)

            it.assertCountEqual(
                sequence,
                {("lib", _path("some_package.vhd")), ("lib", _path("some_entity.vhd"))},
            )

            #  path = _path("entity_a.vhd")
            #  deps = it.database.getDependenciesPaths(path)

            #  logIterable("Dependencies", deps, _logger.info)

            #  # Indirect dependencies should always come first
            #  it.assertCountEqual(
            #      deps,
            #      {
            #          _path("common_dep.vhd"),
            #          _path("indirect_dep.vhd"),
            #          _path("direct_dep_a.vhd"),
            #          _path("direct_dep_b.vhd"),
            #      },
            #  )

    #  with it.having("a package whose library can be determined indirectly"):

    #      @it.has_setup
    #      def setup():
    #          # type: () -> None

    #          it.sources = {
    #              _SourceMock(
    #                  filename=_path("the_package.vhd"),
    #                  library=None,
    #                  design_units=[{"name": "the_package", "type": "package"}],
    #              ),
    #              _SourceMock(
    #                  filename=_path("no_lib_but_use_it_directly.vhd"),
    #                  library=None,
    #                  design_units=[
    #                      {"name": "no_lib_but_use_it_directly", "type": "package"}
    #                  ],
    #                  dependencies=[("find_me", "the_package")],
    #              ),
    #              _SourceMock(
    #                  filename=_path("with_lib_but_use_it_directly.vhd"),
    #                  library="find_me",
    #                  design_units=[
    #                      {"name": "with_lib_but_use_it_directly", "type": "package"}
    #                  ],
    #                  dependencies=[("work", "the_package")],
    #              ),
    #          }

    #          it.database.accept(_configFromSources(it.sources))

    #      @it.has_teardown
    #      def teardown():
    #          it.database.reset()

    #      @it.should("get correct dependencies of entity_a.vhd")  # type: ignore
    #      def test():
    #          # type: () -> None
    #          #  filename=_path("no_lib_but_use_it_directly.vhd"),
    #          #  filename=_path("with_lib_but_use_it_directly.vhd"),

    #          logIterable("Libraries", it.database._libraries.items(), _logger.fatal)
    #          assert False, repr(it.database._libraries.items())

    #          sequence = it.database.getBuildSequence(
    #              _path("no_lib_but_use_it_directly.vhd")
    #          )

    #          logIterable("Build sequence", sequence, _logger.warning)

    #          it.assertEqual(sequence)

    #          it.fail("stop")

    #          #  path = _path("entity_a.vhd")
    #          #  deps = it.database.getDependenciesPaths(path)

    #          #  logIterable("Dependencies", deps, _logger.info)

    #          #  # Indirect dependencies should always come first
    #          #  it.assertCountEqual(
    #          #      deps,
    #          #      {
    #          #          _path("common_dep.vhd"),
    #          #          _path("indirect_dep.vhd"),
    #          #          _path("direct_dep_a.vhd"),
    #          #          _path("direct_dep_b.vhd"),
    #          #      },
    #          #  )


it.createTests(globals())
