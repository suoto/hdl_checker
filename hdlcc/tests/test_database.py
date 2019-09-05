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
from typing import Any, Iterable, List, Set, Tuple

from hdlcc.builders import BuilderName
from hdlcc.database import Database
from hdlcc.parsers import DesignUnitType, Identifier, VhdlDesignUnit
from hdlcc.path import Path

from hdlcc.tests.utils import (  # sanitizePath,; writeListToFile,
    assertCountEqual,
    disableVunit,
    getTestTempPath,
    logIterable,
    setupTestSuport,
    SourceMock,
    TestCase,
)

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(TEST_TEMP_PATH, "test_config_parser")


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
        # type: (Path) -> Set[Tuple[Identifier, Identifier]]
        return {
            (library.name, name.name)
            for library, name in super(_Database, self).getDependenciesUnits(path)
        }

    def test_reportCacheInfo(self):
        # Print cache stats
        lines = []
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                meth = getattr(getattr(self, attr_name), "cache_info")
                lines.append(" - Method '{}': {}".format(attr_name, meth()))
            except AttributeError:
                pass
        if lines:
            _logger.info("Cache info for %s", self)
            for line in lines:
                _logger.info(line)
        else:
            _logger.info("No cache info for %s", self)


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


def _Path(*args):
    # type: (str) -> Path
    return Path(_path(*args))


def _configFromDict(parsed_dict):
    class _ConfigParser(object):  # pylint: disable=too-few-public-methods
        _dict = parsed_dict.copy()

        def parse(self):  # pylint: disable=no-self-use
            return _ConfigParser._dict

    return _ConfigParser()


def _configFromSources(sources):
    srcs = {(x.library, x.filename.name, ()) for x in sources}

    class _ConfigParser(object):  # pylint: disable=too-few-public-methods
        _dict = {"sources": set(srcs)}

        def parse(self):  # pylint: disable=no-self-use
            return _ConfigParser._dict

    return _ConfigParser()


class TestDatabase(TestCase):
    maxDiff = None

    def setUp(self):
        # type: (...) -> Any
        setupTestSuport(TEST_TEMP_PATH)

        self.database = _Database()

    def test_accepts_empty_ConfigParser(self):
        # type: (...) -> Any
        self.database.accept(_configFromDict({}))

        self.assertEqual(self.database.builder_name, BuilderName.fallback)
        self.assertCountEqual(self.database.paths, ())
        #  self.assertEqual(self.database.getLibrary(Path("any")), None)
        self.assertEqual(self.database.getFlags(Path("any")), ())

    def test_accepts_empty_dict(self):
        # type: (...) -> Any
        self.database.updateFromDict({})

        self.assertEqual(self.database.builder_name, BuilderName.fallback)
        self.assertCountEqual(self.database.paths, ())
        #  self.assertEqual(self.database.getLibrary(Path("any")), None)
        self.assertEqual(self.database.getFlags(Path("any")), ())

    def test_accepts_basic_structure(self):
        # type: (...) -> Any
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
        self.assertCountEqual(self.database.paths, (_Path("foo.vhd"), _Path("oof.vhd")))
        self.assertEqual(self.database.getLibrary(_Path("foo.vhd")).name, "bar")
        self.assertEqual(self.database.getLibrary(_Path("oof.vhd")).name, "ooflib")
        self.assertEqual(self.database.getFlags(_Path("foo.vhd")), ("baz", "flag"))
        self.assertEqual(
            self.database.getFlags(_Path("oof.vhd")), ("oofflag0", "oofflag1")
        )

        logIterable(
            "Design units:",
            self.database.getDesignUnitsByPath(_Path("foo.vhd")),
            _logger.info,
        )

        self.assertCountEqual(
            self.database.getDesignUnitsByPath(_Path("foo.vhd")),
            {
                VhdlDesignUnit(
                    owner=_Path("foo.vhd"),
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
            {_Path("foo.vhd")},
        )

        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "ENTITY_A")
            ),
            {_Path("foo.vhd")},
        )

    def test_update_info_if_source_changed(self):
        # type: (...) -> Any
        self.test_accepts_basic_structure()

        # Make sure the env is sane before actually testing
        self.assertTrue(p.exists(_path("foo.vhd")))
        timestamp = p.getmtime(_path("foo.vhd"))

        time.sleep(0.5)

        # SourceMock object writes a dummy VHDL, that should cause the
        # timestamp to change
        _SourceMock(
            filename=_path("foo.vhd"),
            design_units=[{"name": "entity_b", "type": "entity"}],
            dependencies=[],
        )

        self.assertNotEqual(
            timestamp, p.getmtime(_path("foo.vhd")), "Timestamp should've changed"
        )

        self.assertCountEqual(
            self.database.getDesignUnitsByPath(_Path("foo.vhd")),
            [
                VhdlDesignUnit(
                    owner=_Path("foo.vhd"),
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
            [_Path("foo.vhd"), _Path("oof.vhd")],
        )


class TestDirectDependencies(TestCase):
    def setUp(self):
        # type: (...) -> Any
        self.database = _Database()

        self.sources = {
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

        self.database.accept(_configFromSources(self.sources))

    def tearDown(self):
        # type: (...) -> Any
        self.database.test_reportCacheInfo()
        del self.database

    #  @it.should("find paths defining dependencies")  # type: ignore
    #  def test():
    #      # type: (...) -> Any
    #      paths = it.database.getPathsDefining(
    #          name=Identifier("common_dep", False), library=Identifier("work", False)
    #      )

    #      logIterable("paths:", paths, _logger.fatal)

    #      it.fail("stop")

    def test_get_correct_dependencies_of_entity_a(self):
        # type: (...) -> Any
        deps = list(self.database.test_getDependenciesUnits(_Path("entity_a.vhd")))

        logIterable("Dependencies", deps, _logger.info)

        # Indirect dependencies should always come first
        self.assertCountEqual(
            deps,
            {
                ("ieee", "numeric_std"),
                ("work", "common_dep"),
                ("work", "indirect_dep"),
                ("work", "direct_dep_a"),
                ("work", "direct_dep_b"),
            },
        )

    def test_get_correct_build_sequency_of_entity_a(self):
        # type: (...) -> Any
        sequence = list(self.database.getBuildSequence(_Path("entity_a.vhd")))

        logIterable("Build sequence", sequence, _logger.info)

        # entity_a
        # '- common_dep
        # '- direct_dep_a
        #    '- common_dep
        #    '- indirect_dep
        # '- direct_dep_b
        #    '- common_dep

        common_dep = ("work", _Path("common_dep.vhd"))
        indirect_dep = ("work", _Path("indirect_dep.vhd"))
        direct_dep_a = ("work", _Path("direct_dep_a.vhd"))
        direct_dep_b = ("work", _Path("direct_dep_a.vhd"))

        # First item must be common dep
        self.assertEqual(sequence[0], common_dep)

        # indirect_dep must come before direct_dep_a
        self.assertIn(indirect_dep, sequence)
        self.assertIn(direct_dep_a, sequence)
        self.assertTrue(sequence.index(indirect_dep) < sequence.index(direct_dep_a))

        # If conditions above are respected, direct_dep_b can be anywhere
        self.assertIn(direct_dep_b, sequence)

    def test_get_correct_dependencies_of_indirect_dep(self):
        # type: (...) -> Any
        deps = self.database.test_getDependenciesUnits(_Path("indirect_dep.vhd"))

        logIterable("Dependencies", deps, _logger.info)

        self.assertCountEqual(deps, {("work", "common_dep")})


class TestDirectCircularDependencies(TestCase):
    def setUp(self):
        # type: (...) -> Any
        self.database = _Database()

        self.sources = {
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

        self.database.accept(_configFromSources(self.sources))

    def tearDown(self):
        # type: (...) -> Any
        self.database.test_reportCacheInfo()
        del self.database

    def test_should_handle_both_sides(self):
        # type: (...) -> Any
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_a.vhd")),
            (("work", "unit_b"),),
        )

        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_b.vhd")),
            (("work", "unit_a"),),
        )


class TestMultilevelCircularDependencies(TestCase):
    def setUp(self):
        # type: (...) -> Any
        self.database = _Database()

        self.sources = {
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

        self.database.accept(_configFromSources(self.sources))

    def tearDown(self):
        # type: (...) -> Any
        self.database.test_reportCacheInfo()
        del self.database

    def test_report_all_but_the_source_in_question(self):
        # type: (...) -> Any
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_a.vhd")),
            {("work", "unit_b"), ("work", "unit_c"), ("work", "unit_d")},
        )

        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_b.vhd")),
            {("work", "unit_a"), ("work", "unit_c"), ("work", "unit_d")},
        )

        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_c.vhd")),
            {("work", "unit_a"), ("work", "unit_b"), ("work", "unit_d")},
        )

        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_d.vhd")),
            {("work", "unit_a"), ("work", "unit_b"), ("work", "unit_c")},
        )

    def test_identifies_circular_dependencies(self):
        # type: (...) -> Any
        self.assertCountEqual(
            self.database.getBuildSequence(_Path("unit_a.vhd")),
            {("work", "unit_b"), ("work", "unit_c"), ("work", "unit_d")},
        )

        self.fail("stop")


class TestAmbiguousSourceSet(TestCase):
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

    def setUp(self):
        # type: (...) -> Any
        self.database = _Database()

        self.sources = {
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

        self.database.accept(_configFromSources(self.sources))

    def tearDown(self):
        # type: (...) -> Any
        self.database.test_reportCacheInfo()
        del self.database

    def test_get_the_correct_build_sequence(self):
        # type: (...) -> Any
        sequence = tuple(self.database.getBuildSequence(_Path("top.vhd")))

        logIterable("Build sequence", sequence, _logger.debug)

        # Both are on the same level, their order don't matter
        self.assertCountEqual(
            sequence,
            {("lib", _Path("some_package.vhd")), ("lib", _Path("some_entity.vhd"))},
        )


class TestPackageWhoseLibraryCanBeDeterminedIndirectly(TestCase):
    def setUp(self):
        # type: (...) -> Any
        self.database = _Database()

        self.sources = {
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

        self.database.accept(_configFromSources(self.sources))

    def tearDown(self):
        # type: (...) -> Any
        self.database.test_reportCacheInfo()
        del self.database

    def test_get_correct_dependencies_of_entity_a(self):
        # type: (...) -> Any
        sequence = tuple(
            self.database.getBuildSequence(_Path("no_lib_but_use_it_directly.vhd"))
        )

        logIterable("Build sequence", sequence, _logger.info)

        self.assertEqual(sequence, (("find_me", _Path("target_pkg.vhd")),))

        #  self.fail("stop")

        #  path = _path("entity_a.vhd")
        #  deps = self.database.test_getDependenciesUnits(path)

        #  logIterable("Dependencies", deps, _logger.info)

        #  # Indirect dependencies should always come first
        #  self.assertCountEqual(
        #      deps,
        #      {
        #          _path("common_dep.vhd"),
        #          _path("indirect_dep.vhd"),
        #          _path("direct_dep_a.vhd"),
        #          _path("direct_dep_b.vhd"),
        #      },
        #  )
