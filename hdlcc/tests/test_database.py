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
import time

import six
import unittest2  # type: ignore

from nose2.tools import such  # type: ignore

import hdlcc.types as t
from hdlcc.builders import BuilderName
from hdlcc.database import Database
from hdlcc.parsers import DesignUnitType, VhdlDesignUnit
from hdlcc.path import Path

from hdlcc.tests.utils import (  # sanitizePath,; writeListToFile,
    assertCountEqual,
    disableVunit,
    getTestTempPath,
    logIterable,
    setupTestSuport,
    SourceMock,
)

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(TEST_TEMP_PATH, "test_config_parser")

such.unittest.TestCase.maxDiff = None


class _SourceMock(SourceMock):
    base_path = TEST_TEMP_PATH


class _Database(Database):
    def __init__(self, *args, **kwargs):
        with disableVunit:
            super(_Database, self).__init__(*args, **kwargs)

    def updateFromDict(self, config):
        super(_Database, self).updateFromDict(config)
        _logger.debug("State after updating:")

        _logger.debug("- %d design units:", len(self.design_units))
        for unit in self.design_units:
            _logger.debug("  - %s", unit)

        _logger.debug("- %d paths:", len(self._paths))
        for path, timestamp in self._paths.items():
            dependencies = self._dependencies.get(path, {})
            _logger.debug("  - Path: %s (%f)", path, timestamp)
            _logger.debug("    - library:      : %s", self._libraries.get(path, "<??>"))
            _logger.debug("    - flags:        : %s", self._flags.get(path, "-"))
            _logger.debug("    - %d dependencies:", len(dependencies))
            for dependency in dependencies:
                _logger.debug("      - %s", dependency)

    def test_getDependenciesUnits(self, path):
        return {
            (library.name, name.name)
            for library, name in super(_Database, self).getDependenciesUnits(path)
        }
        #  yield library.name, name.name


def _path(*args):
    # type: (...) -> Path
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return Path(p.join(TEST_TEMP_PATH, *args))


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
    maxDiff = None

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
        #  self.assertEqual(self.database.getLibrary(Path("any")), None)
        self.assertEqual(self.database.getFlags(Path("any")), ())

    def test_accepts_empty_dict(self):
        # type: () -> None
        self.database.updateFromDict({})

        self.assertEqual(self.database.builder_name, BuilderName.fallback)
        self.assertCountEqual(self.database.paths, ())
        #  self.assertEqual(self.database.getLibrary(Path("any")), None)
        self.assertEqual(self.database.getFlags(Path("any")), ())

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
        self.assertEqual(self.database.getLibrary(_path("foo.vhd")).name, "bar")
        self.assertEqual(self.database.getLibrary(_path("oof.vhd")).name, "ooflib")
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
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "entity_a")
            ),
            {_path("foo.vhd")},
        )

        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "ENTITY_A")
            ),
            {_path("foo.vhd")},
        )

    def test_update_info_if_source_changed(self):
        # type: () -> None
        self.test_accepts_basic_structure()

        # Make sure the env is sane before actually testing
        it.assertTrue(p.exists(_path("foo.vhd").name))
        timestamp = p.getmtime(_path("foo.vhd").name)

        time.sleep(0.5)

        # SourceMock object writes a dummy VHDL, that should cause the
        # timestamp to change
        _SourceMock(
            filename=_path("foo.vhd"),
            design_units=[{"name": "entity_b", "type": "entity"}],
            dependencies=[],
        )

        it.assertNotEqual(
            timestamp, p.getmtime(_path("foo.vhd").name), "Timestamp should've changed"
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
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "entity_a")
            ),
            (),
        )

        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "entity_B")
            ),
            [_path("foo.vhd"), _path("oof.vhd")],
        )


with such.A("database") as it:
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    with it.having("only direct dependencies"):

        @it.has_setup
        def setup():
            # type: () -> None
            it.database = _Database()

            it.sources = {
                _SourceMock(
                    filename=_path("entity_a.vhd"),
                    library="work",
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
                    library="work",
                    design_units=[
                        {"name": "direct_dep_a", "type": "entity"},
                        {"name": "side_effect_entity", "type": "entity"},
                    ],
                    dependencies=(("common_dep",), ("indirect_dep",)),
                ),
                _SourceMock(
                    filename=_path("direct_dep_b.vhd"),
                    library="work",
                    design_units=[{"name": "direct_dep_b", "type": "entity"}],
                    dependencies=[("work", "common_dep")],
                ),
                _SourceMock(
                    filename=_path("indirect_dep.vhd"),
                    library="work",
                    design_units=[
                        {"name": "indirect_dep", "type": "package"},
                        {"name": "indirect_dep", "type": "package body"},
                        {"name": "side_effect_package", "type": "package"},
                    ],
                    dependencies=[("work", "common_dep")],
                ),
                _SourceMock(
                    filename=_path("common_dep.vhd"),
                    library="work",
                    design_units=[
                        {"name": "common_dep", "type": "package"},
                        {"name": "common_dep", "type": "package body"},
                    ],
                ),
                _SourceMock(
                    filename=_path("not_a_dependency.vhd"),
                    library="work",
                    design_units=[{"name": "not_a_dependency", "type": "package"}],
                    dependencies=(("common_dep",), ("indirect_dep",)),
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            del it.database

        #  @it.should("find paths defining dependencies")  # type: ignore
        #  def test():
        #      # type: () -> None
        #      paths = it.database.getPathsDefining(
        #          name=Identifier("common_dep", False), library=Identifier("work", False)
        #      )

        #      logIterable("paths:", paths, _logger.fatal)

        #      it.fail("stop")

        @it.should("get correct dependencies of entity_a.vhd")  # type: ignore
        def test():
            # type: () -> None
            path = _path("entity_a.vhd")
            deps = list(it.database.test_getDependenciesUnits(path))

            logIterable("Dependencies", deps, _logger.info)

            # Indirect dependencies should always come first
            it.assertCountEqual(
                deps,
                {
                    ("ieee", "numeric_std"),
                    ("work", "common_dep"),
                    ("work", "indirect_dep"),
                    ("work", "direct_dep_a"),
                    ("work", "direct_dep_b"),
                },
            )

        @it.should("get correct build sequence of entity_a.vhd")  # type: ignore
        def test():
            # type: () -> None
            sequence = list(it.database.getBuildSequence(_path("entity_a.vhd")))

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
            deps = it.database.test_getDependenciesUnits(path)

            logIterable("Dependencies", deps, _logger.info)

            it.assertCountEqual(deps, {("work", "common_dep")})

    with it.having("direct circular dependencies between 2 sources"):

        @it.has_setup
        def setup():
            # type: () -> None
            it.database = _Database()

            it.sources = {
                _SourceMock(
                    filename=_path("unit_a.vhd"),
                    library="work",
                    design_units=[{"name": "unit_a", "type": "entity"}],
                    dependencies=[("work", "unit_b")],
                ),
                _SourceMock(
                    filename=_path("unit_b.vhd"),
                    library="work",
                    design_units=[{"name": "unit_b", "type": "entity"}],
                    dependencies=[("work", "unit_a")],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            del it.database

        @it.should("handle both sides")  # type: ignore
        def test():
            it.assertCountEqual(
                it.database.test_getDependenciesUnits(_path("unit_a.vhd")),
                (("work", "unit_b"),),
            )

            it.assertCountEqual(
                it.database.test_getDependenciesUnits(_path("unit_b.vhd")),
                (("work", "unit_a"),),
            )

    with it.having("multilevel circular dependencies"):

        @it.has_setup
        def setup():
            # type: () -> None
            it.database = _Database()

            it.sources = {
                _SourceMock(
                    filename=_path("unit_a.vhd"),
                    library="work",
                    design_units=[{"name": "unit_a", "type": "entity"}],
                    dependencies=[("work", "unit_b")],
                ),
                _SourceMock(
                    filename=_path("unit_b.vhd"),
                    library="work",
                    design_units=[{"name": "unit_b", "type": "entity"}],
                    dependencies=[("work", "unit_c")],
                ),
                _SourceMock(
                    filename=_path("unit_c.vhd"),
                    library="work",
                    design_units=[{"name": "unit_c", "type": "entity"}],
                    dependencies=[("work", "unit_d")],
                ),
                _SourceMock(
                    filename=_path("unit_d.vhd"),
                    library="work",
                    design_units=[{"name": "unit_d", "type": "entity"}],
                    dependencies=[("work", "unit_a")],
                ),
                _SourceMock(
                    filename=_path("not_a_dependency.vhd"),
                    library="work",
                    design_units=[{"name": "not_a_dependency", "type": "package"}],
                    dependencies=[("indirect_dep",), ("common_dep",)],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            del it.database

        @it.should("report all but the source in question")  # type: ignore
        def test():
            # type: () -> None
            it.assertCountEqual(
                it.database.test_getDependenciesUnits(_path("unit_a.vhd")),
                {("work", "unit_b"), ("work", "unit_c"), ("work", "unit_d")},
            )

            it.assertCountEqual(
                it.database.test_getDependenciesUnits(_path("unit_b.vhd")),
                {("work", "unit_a"), ("work", "unit_c"), ("work", "unit_d")},
            )

            it.assertCountEqual(
                it.database.test_getDependenciesUnits(_path("unit_c.vhd")),
                {("work", "unit_a"), ("work", "unit_b"), ("work", "unit_d")},
            )

            it.assertCountEqual(
                it.database.test_getDependenciesUnits(_path("unit_d.vhd")),
                {("work", "unit_a"), ("work", "unit_b"), ("work", "unit_c")},
            )

        @it.should("identify circular dependencies")  # type: ignore
        def test():
            # type: () -> None
            it.assertCountEqual(
                it.database.getBuildSequence(_path("unit_a.vhd")),
                {("work", "unit_b"), ("work", "unit_c"), ("work", "unit_d")},
            )

            it.fail("stop")

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
            it.database = _Database()

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
            del it.database

        @it.should("get the correct build sequence")  # type: ignore
        def test():
            # type: () -> None
            sequence = tuple(it.database.getBuildSequence(_path("top.vhd")))

            logIterable("Build sequence", sequence, _logger.debug)

            # Both are on the same level, their order don't matter
            it.assertCountEqual(
                sequence,
                {("lib", _path("some_package.vhd")), ("lib", _path("some_entity.vhd"))},
            )

    with it.having("a package whose library can be determined indirectly"):

        @it.has_setup
        def setup():
            # type: () -> None
            it.database = _Database()

            it.sources = {
                _SourceMock(
                    filename=_path("target_pkg.vhd"),
                    library=None,
                    design_units=[{"name": "target_pkg", "type": "package"}],
                ),
                _SourceMock(
                    filename=_path("no_lib_but_use_it_directly.vhd"),
                    library=None,
                    design_units=[
                        {"name": "no_lib_but_use_it_directly", "type": "package"}
                    ],
                    dependencies=[("find_me", "target_pkg")],
                ),
                _SourceMock(
                    filename=_path("with_lib_but_use_it_directly.vhd"),
                    library="find_me",
                    design_units=[
                        {"name": "with_lib_but_use_it_directly", "type": "package"}
                    ],
                    dependencies=[("work", "target_pkg")],
                ),
            }

            it.database.accept(_configFromSources(it.sources))

        @it.has_teardown
        def teardown():
            del it.database

        @it.should("get correct dependencies of entity_a.vhd")  # type: ignore
        def test():
            # type: () -> None
            sequence = tuple(
                it.database.getBuildSequence(_path("no_lib_but_use_it_directly.vhd"))
            )

            logIterable("Build sequence", sequence, _logger.info)

            it.assertEqual(sequence, (("find_me", _path("target_pkg.vhd")),))

            #  it.fail("stop")

            #  path = _path("entity_a.vhd")
            #  deps = it.database.test_getDependenciesUnits(path)

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


it.createTests(globals())
