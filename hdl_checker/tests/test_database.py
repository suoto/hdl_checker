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
# pylint: disable=invalid-name
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=useless-object-inheritance

import json
import logging
import os.path as p
import tempfile
import time
from pprint import pformat
from typing import Any, Dict, Iterable, Set, Tuple

from mock import PropertyMock, patch

from hdl_checker.tests import (
    SourceMock,
    TestCase,
    getTestTempPath,
    logIterable,
    setupTestSuport,
)

from hdl_checker import DEFAULT_LIBRARY
from hdl_checker.database import Database
from hdl_checker.diagnostics import DependencyNotUnique, PathNotInProjectFile
from hdl_checker.parsers.elements.dependency_spec import (
    BaseDependencySpec,
    IncludedPath,
    RequiredDesignUnit,
)
from hdl_checker.parsers.elements.design_unit import VhdlDesignUnit
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.parsers.elements.parsed_element import Location
from hdl_checker.path import Path, TemporaryPath
from hdl_checker.serialization import StateEncoder, jsonObjectHook
from hdl_checker.types import BuildFlagScope, DesignUnitType, FileType

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(TEST_TEMP_PATH, "test_config_parser")


class _SourceMock(SourceMock):
    base_path = TEST_TEMP_PATH


class _Database(Database):
    def configure(self, root_config, root_path):
        # type: (Dict[str, Any], str) -> int
        _logger.info("Updating config from\n%s", pformat(root_config))
        result = super(_Database, self).configure(root_config, root_path)

        _logger.debug("State after updating:")

        _logger.debug("- %d design units:", len(self.design_units))
        for unit in self.design_units:
            _logger.debug("  - %s", unit)

        _logger.debug("- %d paths:", len(self._paths))
        for path in self._paths:
            timestamp = self._parse_timestamp[path]
            dependencies = self._dependencies_map.get(
                path, set()
            )  # type: Set[BaseDependencySpec]
            _logger.debug("  - Path: %s (%f)", path, timestamp)
            _logger.debug("    - library:      : %s", self._library_map.get(path, "?"))
            _logger.debug("    - flags:        : %s", self._flags_map.get(path, "-"))
            _logger.debug("    - %d dependencies:", len(dependencies))
            for dependency in dependencies:
                _logger.debug("      - %s", dependency)

        return result

    def __jsonEncode__(self):
        state = super(_Database, self).__jsonEncode__()
        state["__class__"] = "Database"  # super(_Database, self).__class__.__name__
        return state

    def _configFromSources(self, sources, root_path):
        "Creates the dict describing the sources and calls self.configure on it"
        config = []
        for source in sources:
            info = {}
            if source.library:
                info["library"] = source.library
            if source.flags:
                info["flags"] = source.flags

            # Yield a string only or a (str, dict) tuple to test both conversions
            # (this mimics the supported JSON scheme)
            if info:
                config.append((source.filename.name, info))
            else:
                config.append(source.filename.name)

        self.configure({"sources": config}, root_path)

    def test_getDependenciesUnits(self, path):
        # type: (Path) -> Iterable[Tuple[Identifier, Identifier]]
        _msg = []
        for library, name in super(_Database, self).getDependenciesUnits(path):
            yield getattr(library, "name", None), name.name
            _msg.append((library, name))

        _logger.debug("getDependenciesUnits('%s') => %s", path, _msg)

    def test_getBuildSequence(self, path):
        # type: (Path) -> Iterable[Tuple[Identifier, Path]]
        _msg = []
        for library, build_path in super(_Database, self).getBuildSequence(path):
            yield library, build_path
            _msg.append((getattr(library, "name", None), build_path.name))

        _logger.debug("getBuildSequence('%s') => %s", path, _msg)

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


class TestDatabase(TestCase):
    maxDiff = None

    def setUp(self):
        # type: (...) -> Any
        _logger.info("Setting up %s", self)
        setupTestSuport(TEST_TEMP_PATH)
        self.database = _Database()

    @patch("hdl_checker.parser_utils.findRtlSourcesByPath")
    def test_AcceptsEmptySourcesList(self, meth):
        # type: (...) -> Any
        # Make TEST_TEMP_PATH/some_path.vhd readable so it is returned by
        # findRtlSourcesByPath
        with tempfile.NamedTemporaryFile(suffix=".vhd", delete=False) as path:
            meth.return_value = [Path(path.name)]
            path.close()

            self.database.configure(dict(), TEST_TEMP_PATH)

            #  self.assertEqual(self.database.builder_name, None)
            self.assertCountEqual(self.database.paths, (Path(path.name),))

            # Make sure the path exists
            for test_path in (_Path("some_vhd.vhd"), _Path("some_sv.sv")):
                self.assertFalse(self.database.getDependenciesByPath(test_path))
                self.assertEqual(self.database.getFlags(test_path), ())

            self.assertEqual(
                self.database.getLibrary(_Path("some_vhd.vhd")),
                Identifier("not_in_project", False),
            )

            self.assertEqual(
                self.database.getLibrary(_Path("some_sv.sv")),
                Identifier("not_in_project", False),
            )

            meth.assert_called_once_with(Path(TEST_TEMP_PATH))

    @patch("hdl_checker.parser_utils.findRtlSourcesByPath")
    def test_AcceptsEmptyDict(self, meth):
        # type: (...) -> Any
        # Make TEST_TEMP_PATH/some_path.vhd readable so it is returned by
        # findRtlSourcesByPath
        with tempfile.NamedTemporaryFile(suffix=".vhd", delete=False) as path:
            meth.return_value = [Path(path.name)]
            path.close()

            self.database.configure({}, TEST_TEMP_PATH)

            self.assertCountEqual(self.database.paths, (Path(path.name),))
            self.assertEqual(self.database.getFlags(Path("any")), ())
            meth.assert_called_once_with(Path(TEST_TEMP_PATH))

    def test_AcceptsBasicStructure(self):
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

        self.database.configure(
            {
                "sources": [
                    (_path("foo.vhd"), {"library": "bar", "flags": ("baz", "flag")}),
                    (
                        _path("oof.vhd"),
                        {"library": "ooflib", "flags": ("oofflag0", "oofflag1")},
                    ),
                ],
                FileType.vhdl.value: {
                    "flags": {
                        BuildFlagScope.single.value: ("vhdl", "single"),
                        BuildFlagScope.dependencies.value: ("vhdl", "dependencies"),
                        BuildFlagScope.all.value: ("vhdl", "all"),
                    }
                },
                FileType.verilog.value: {
                    "flags": {
                        BuildFlagScope.single.value: ("verilog", "single"),
                        BuildFlagScope.dependencies.value: ("verilog", "dependencies"),
                        BuildFlagScope.all.value: ("verilog", "all"),
                    }
                },
                FileType.systemverilog.value: {
                    "flags": {
                        BuildFlagScope.single.value: ("systemverilog", "single"),
                        BuildFlagScope.dependencies.value: (
                            "systemverilog",
                            "dependencies",
                        ),
                        BuildFlagScope.all.value: ("systemverilog", "all"),
                    }
                },
            },
            TEST_TEMP_PATH,
        )

        foo_path = _Path("foo.vhd")
        oof_path = _Path("oof.vhd")

        self.assertCountEqual(self.database.paths, (foo_path, oof_path))
        self.assertEqual(self.database.getLibrary(foo_path), Identifier("bar", False))
        self.assertEqual(
            self.database.getLibrary(oof_path), Identifier("ooflib", False)
        )

        self.assertEqual(
            self.database.getFlags(foo_path, BuildFlagScope.single),
            ("vhdl", "all", "vhdl", "single", "baz", "flag"),
        )
        self.assertEqual(
            self.database.getFlags(foo_path),
            ("vhdl", "all", "vhdl", "single", "baz", "flag"),
        )

        #  self.assertEqual(self.database.getFlags(oof_path), ("oofflag0", "oofflag1"))

        logIterable(
            "Design units:", self.database.getDesignUnitsByPath(foo_path), _logger.info
        )

        self.assertCountEqual(
            self.database.getDesignUnitsByPath(foo_path),
            {
                VhdlDesignUnit(
                    owner=foo_path,
                    name="entity_a",
                    type_=DesignUnitType.entity,
                    locations={Location(3, 7)},
                )
            },
        )

        # VHDL world, should find regardless of lower or upper case
        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "entity_a")
            ),
            {foo_path},
        )

        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "ENTITY_A")
            ),
            {foo_path},
        )

    def test_UpdateInfoIfSourceChanged(self):
        # type: (...) -> Any
        self.test_AcceptsBasicStructure()

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
                    locations={Location(0, 6)},
                )
            ],
        )

        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "entity_a")
            ),
            (),
        )

        oof_path = _Path("oof.vhd")

        self.assertCountEqual(
            self.database.getPathsByDesignUnit(
                VhdlDesignUnit(Path(""), DesignUnitType.entity, "entity_B")
            ),
            [_Path("foo.vhd"), oof_path],
        )

    def test_UpdatePathLibrary(self):
        # type: (...) -> Any
        sources = {
            _SourceMock(
                filename=_path("file_0.vhd"),
                library="some_library",
                design_units=[{"name": "some_package", "type": "package"}],
                dependencies=(
                    ("work", "relative_dependency"),
                    ("lib", "direct_dependency"),
                ),
            ),
            _SourceMock(
                filename=_path("collateral.vhd"),
                library="another_library",
                design_units=[{"name": "collateral_package", "type": "package"}],
                dependencies=(("work", "foo"), ("lib", "bar")),
            ),
        }

        self.database._configFromSources(sources, TEST_TEMP_PATH)

        # Check libraries before actually testing
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("file_0.vhd")),
            {("some_library", "relative_dependency"), ("lib", "direct_dependency")},
        )
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("collateral.vhd")),
            {("another_library", "foo"), ("lib", "bar")},
        )

        # Update the library of a path
        self.database._updatePathLibrary(
            _Path("file_0.vhd"), Identifier("file_0_lib", False)
        )

        # Check that reflected only where intended
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("file_0.vhd")),
            {("file_0_lib", "relative_dependency"), ("lib", "direct_dependency")},
        )
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("collateral.vhd")),
            {("another_library", "foo"), ("lib", "bar")},
        )

    def test_InfersUsesMostCommonLibraryIfNeeded(self):
        # type: (...) -> Any
        # Given a design unit used in multiple ways, use the most common one
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("file_0.vhd"),
                    library=None,
                    design_units=[{"name": "package_0", "type": "package"}],
                    dependencies=(("lib_a", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_1.vhd"),
                    library=None,
                    design_units=[{"name": "package_1", "type": "package"}],
                    dependencies=(("lib_b", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_2.vhd"),
                    library=None,
                    design_units=[{"name": "package_2", "type": "package"}],
                    dependencies=(("lib_c", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_3.vhd"),
                    library=None,
                    design_units=[{"name": "package_2", "type": "package"}],
                    dependencies=(("lib_a", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("some_dependency.vhd"),
                    library=None,
                    design_units=[{"name": "some_dependency", "type": "package"}],
                ),
            },
            TEST_TEMP_PATH,
        )

        self.assertEqual(
            self.database.getLibrary(_Path("some_dependency.vhd")),
            Identifier("lib_a", False),
        )

        # Change one of the sources to use a different library to force the
        # most common one to change
        _SourceMock(
            filename=_path("file_0.vhd"),
            library=None,
            design_units=[{"name": "package_1", "type": "package"}],
            dependencies=(("lib_b", "some_dependency"),),
        )

        self.database.refresh()

        time.sleep(0.1)

        self.assertEqual(
            self.database.getLibrary(_Path("some_dependency.vhd")),
            Identifier("lib_b", False),
        )

    def test_LibraryInferenceIgnoresWorkReferences(self):
        # type: (...) -> Any
        # When using work.something, 'work' means the current library and
        # should be ignored
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("file_0.vhd"),
                    library=None,
                    #  library="file_0_library",
                    design_units=[{"name": "package_0", "type": "package"}],
                    dependencies=(("work", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_1.vhd"),
                    library=None,
                    design_units=[{"name": "package_1", "type": "package"}],
                    dependencies=(("work", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_2.vhd"),
                    library=None,
                    design_units=[{"name": "package_2", "type": "package"}],
                    dependencies=(("work", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_3.vhd"),
                    library=None,
                    design_units=[{"name": "package_3", "type": "package"}],
                    dependencies=(("some_dep_lib", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("some_dependency.vhd"),
                    library=None,
                    design_units=[{"name": "some_dependency", "type": "package"}],
                ),
            },
            TEST_TEMP_PATH,
        )

        self.assertEqual(
            self.database.getLibrary(_Path("some_dependency.vhd")),
            Identifier("some_dep_lib", False),
        )

    def test_LibraryInferenceUsesTheMostCommon(self):
        # type: (...) -> Any
        # When using work.something and on a source whose library has been set,
        # should use that instead of the most common
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("file_0.vhd"),
                    library="file_0_library",
                    design_units=[{"name": "package_0", "type": "package"}],
                    dependencies=(("work", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_1.vhd"),
                    library=None,
                    design_units=[{"name": "package_1", "type": "package"}],
                    dependencies=(("work", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_2.vhd"),
                    library=None,
                    design_units=[{"name": "package_2", "type": "package"}],
                    dependencies=(("some_dep_lib", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_3.vhd"),
                    library=None,
                    design_units=[{"name": "package_3", "type": "package"}],
                    dependencies=(("some_dep_lib", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("some_dependency.vhd"),
                    library=None,
                    design_units=[{"name": "some_dependency", "type": "package"}],
                ),
            },
            TEST_TEMP_PATH,
        )

        self.assertEqual(
            self.database.getLibrary(_Path("some_dependency.vhd")),
            Identifier("some_dep_lib", False),
        )

    def test_JsonEncodingAndDecoding(self):
        database = _Database()

        database._configFromSources(
            {
                _SourceMock(
                    filename=_path("file_0.vhd"),
                    library="some_library",
                    design_units=[{"name": "some_package", "type": "package"}],
                    dependencies=(
                        ("work", "relative_dependency"),
                        ("lib", "direct_dependency"),
                    ),
                ),
                _SourceMock(
                    filename=_path("collateral.vhd"),
                    library="another_library",
                    design_units=[{"name": "collateral_package", "type": "package"}],
                    dependencies=(("work", "foo"), ("lib", "bar")),
                ),
            },
            TEST_TEMP_PATH,
        )

        state = json.dumps(database, cls=StateEncoder, indent=True)

        _logger.info("database in json:\n%s", state)

        recovered = json.loads(state, object_hook=jsonObjectHook)

        self.assertCountEqual(database.design_units, recovered.design_units)
        self.assertCountEqual(database._paths, recovered._paths)
        self.assertDictEqual(database._parse_timestamp, recovered._parse_timestamp)
        self.assertDictEqual(database._library_map, recovered._library_map)
        self.assertCountEqual(
            database._inferred_libraries, recovered._inferred_libraries
        )
        self.assertDictEqual(database._flags_map, recovered._flags_map)
        self.assertDictEqual(database._dependencies_map, recovered._dependencies_map)

    def test_RemovingAPathThatWasAdded(self):
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("file_0.vhd"),
                    library="some_library",
                    design_units=[{"name": "some_package", "type": "package"}],
                    dependencies=(
                        ("work", "relative_dependency"),
                        ("lib", "direct_dependency"),
                    ),
                ),
                _SourceMock(
                    filename=_path("collateral.vhd"),
                    library="another_library",
                    design_units=[{"name": "collateral_package", "type": "package"}],
                    dependencies=(("work", "foo"), ("lib", "bar")),
                ),
            },
            TEST_TEMP_PATH,
        )

        file_0 = _Path("file_0.vhd")
        collateral = _Path("collateral.vhd")
        # Make sure there's design units detected for all files
        self.assertTrue(list(self.database.getDesignUnitsByPath(file_0)))
        self.assertTrue(list(self.database.getDesignUnitsByPath(collateral)))
        self.assertEqual(str(self.database.getLibrary(file_0)), "some_library")
        self.assertEqual(str(self.database.getLibrary(collateral)), "another_library")

        self.database.removeSource(file_0)

        # file_0.vhd units will still be found (parsing does not depent on the
        # source being added or not)
        self.assertTrue(list(self.database.getDesignUnitsByPath(file_0)))
        # collateral.vhd units should continue to be found
        self.assertTrue(list(self.database.getDesignUnitsByPath(collateral)))

        # file_0.vhd is not on the project anymore, so library should reflect
        # that
        self.assertEqual(str(self.database.getLibrary(file_0)), "not_in_project")
        # collateral.vhd units should continue to be found
        self.assertEqual(str(self.database.getLibrary(collateral)), "another_library")

    def test_RemovingAnExistingPathThatWasNotAdded(self):
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("collateral.vhd"),
                    library="another_library",
                    design_units=[{"name": "collateral_package", "type": "package"}],
                    dependencies=(("work", "foo"), ("lib", "bar")),
                )
            },
            TEST_TEMP_PATH,
        )

        file_0 = _Path("file_0.vhd")
        collateral = _Path("collateral.vhd")
        # Same as previous test, but file_0.vhd is not on the project
        self.assertTrue(list(self.database.getDesignUnitsByPath(file_0)))
        self.assertTrue(list(self.database.getDesignUnitsByPath(collateral)))
        # In this case, the library will change to the default library used for
        # files that weren't added
        self.assertEqual(str(self.database.getLibrary(file_0)), "not_in_project")
        self.assertEqual(str(self.database.getLibrary(collateral)), "another_library")

        self.database.removeSource(file_0)

        # file_0.vhd units will still be found (parsing does not depent on the
        # source being added or not)
        self.assertTrue(list(self.database.getDesignUnitsByPath(file_0)))
        # collateral.vhd units should continue to be found
        self.assertTrue(list(self.database.getDesignUnitsByPath(collateral)))

        # file_0.vhd is not on the project anymore, so library should reflect
        # that
        self.assertEqual(str(self.database.getLibrary(file_0)), "not_in_project")
        # collateral.vhd units should continue to be found
        self.assertEqual(str(self.database.getLibrary(collateral)), "another_library")

    def test_RemovingANonExistingPathThatWasNotAdded(self):
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("collateral.vhd"),
                    library="another_library",
                    design_units=[{"name": "collateral_package", "type": "package"}],
                    dependencies=(("work", "foo"), ("lib", "bar")),
                )
            },
            TEST_TEMP_PATH,
        )

        path = Path("/some/path.vhd")
        self.assertFalse(p.exists(str(path)))

        # Try removing before any operation fills any table inside the
        # database. Nothing should change before and after
        before = self.database.__jsonEncode__()
        self.database.removeSource(path)
        self.assertDictEqual(self.database.__jsonEncode__(), before)

        collateral = _Path("collateral.vhd")

        # Same as previous test, but path.vhd is not on the project
        self.assertFalse(list(self.database.getDesignUnitsByPath(path)))
        self.assertTrue(list(self.database.getDesignUnitsByPath(collateral)))
        # In this case, the library will change to the default library used for
        # files that weren't added
        self.assertEqual(str(self.database.getLibrary(path)), "not_in_project")
        self.assertEqual(str(self.database.getLibrary(collateral)), "another_library")

        self.database.removeSource(path)

        # path.vhd units shouldn't be found anymore
        self.assertFalse(list(self.database.getDesignUnitsByPath(path)))
        # collateral.vhd units should continue to be found
        self.assertTrue(list(self.database.getDesignUnitsByPath(collateral)))

        # path.vhd is not on the project anymore
        self.assertEqual(str(self.database.getLibrary(path)), "not_in_project")
        # collateral.vhd units should continue to be found
        self.assertEqual(str(self.database.getLibrary(collateral)), "another_library")

        # Also test that a diagnostic indicating the path hasn't been added has
        # been created
        self.assertCountEqual(
            self.database.getDiagnosticsForPath(path), [PathNotInProjectFile(path)]
        )

    def test_TemporaryPathsDontGeneratePathNotInProject(self):
        # type: (...) -> Any
        path = _path("foo.vhd")

        self.database._clearLruCaches()

        # Temporary paths should NOT generate PathNotInProjectFile diagnostic
        with patch.object(self.database, "_addDiagnostic") as meth:
            self.database.getLibrary(TemporaryPath(path))
            meth.assert_not_called()

        self.database._clearLruCaches()

        # Regular paths should generate PathNotInProjectFile diagnostic
        with patch.object(self.database, "_addDiagnostic") as meth:
            self.database.getLibrary(Path(path))
            meth.assert_called_once_with(PathNotInProjectFile(Path(path)))

    def test_GetReferencesToDesignUnit(self):
        # type: (...) -> Any
        self.database._configFromSources(
            {
                _SourceMock(
                    filename=_path("file_0.vhd"),
                    library="file_0_library",
                    design_units=[{"name": "package_0", "type": "package"}],
                    dependencies=(("work", "some_other_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_1.vhd"),
                    library=None,
                    design_units=[{"name": "package_1", "type": "package"}],
                    dependencies=(("work", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_2.vhd"),
                    library=None,
                    design_units=[{"name": "package_2", "type": "package"}],
                    dependencies=(("some_dep_lib", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("file_3.vhd"),
                    library=None,
                    design_units=[{"name": "package_3", "type": "package"}],
                    dependencies=(("some_dep_lib", "some_dependency"),),
                ),
                _SourceMock(
                    filename=_path("some_dependency.vhd"),
                    library=None,
                    design_units=[{"name": "some_dependency", "type": "package"}],
                ),
            },
            TEST_TEMP_PATH,
        )

        # A design unit from a file whose library hasn't been set
        unit = VhdlDesignUnit(
            owner=_Path("some_dependency.vhd"),
            name="some_dependency",
            type_=DesignUnitType.package,
            locations={},
        )

        self.assertCountEqual(
            self.database.getReferencesToDesignUnit(unit),
            {
                RequiredDesignUnit(
                    name=Identifier("some_dependency"),
                    library=None,
                    owner=_Path("file_1.vhd"),
                    locations=(Location(line=1, column=4),),
                ),
                RequiredDesignUnit(
                    name=Identifier("some_dependency"),
                    library=Identifier("some_dep_lib"),
                    owner=_Path("file_2.vhd"),
                    locations=(Location(line=1, column=4),),
                ),
                RequiredDesignUnit(
                    name=Identifier("some_dependency"),
                    library=Identifier("some_dep_lib"),
                    owner=_Path("file_3.vhd"),
                    locations=(Location(line=1, column=4),),
                ),
            },
        )

class TestDirectDependencies(TestCase):
    def setUp(self):
        # type: (...) -> Any
        _logger.info("Setting up %s", self)
        self.database = _Database()

        sources = {
            _SourceMock(
                filename=_path("entity_a.vhd"),
                library="lib",
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
                library="lib",
                design_units=[
                    {"name": "direct_dep_a", "type": "entity"},
                    {"name": "side_effect_entity", "type": "entity"},
                ],
                dependencies=(("common_dep",), ("indirect_dep",)),
            ),
            _SourceMock(
                filename=_path("direct_dep_b.vhd"),
                library="lib",
                design_units=[{"name": "direct_dep_b", "type": "entity"}],
                dependencies=[("work", "common_dep")],
            ),
            _SourceMock(
                filename=_path("indirect_dep.vhd"),
                library="lib",
                design_units=[
                    {"name": "indirect_dep", "type": "package"},
                    {"name": "indirect_dep", "type": "package body"},
                    {"name": "side_effect_package", "type": "package"},
                ],
                dependencies=[("work", "common_dep")],
            ),
            _SourceMock(
                filename=_path("common_dep.vhd"),
                library="lib",
                design_units=[
                    {"name": "common_dep", "type": "package"},
                    {"name": "common_dep", "type": "package body"},
                ],
            ),
            _SourceMock(
                filename=_path("not_a_dependency.vhd"),
                library="lib",
                design_units=[{"name": "not_a_dependency", "type": "package"}],
                dependencies=(("common_dep",), ("indirect_dep",)),
            ),
        }

        self.database._configFromSources(sources, TEST_TEMP_PATH)

    def tearDown(self):
        # type: (...) -> Any
        _logger.info("Tearing down %s", self)
        self.database.test_reportCacheInfo()
        del self.database

    def test_GetCorrectDependenciesOfEntityA(self):
        # type: (...) -> Any
        deps = list(self.database.test_getDependenciesUnits(_Path("entity_a.vhd")))

        # Indirect dependencies should always come first
        self.assertCountEqual(
            deps,
            {
                ("ieee", "numeric_std"),
                ("lib", "common_dep"),
                ("lib", "indirect_dep"),
                ("lib", "direct_dep_a"),
                ("lib", "direct_dep_b"),
            },
        )

    def test_GetCorrectBuildSequencyOfEntityA(self):
        # type: (...) -> Any
        sequence = list(self.database.test_getBuildSequence(_Path("entity_a.vhd")))

        # entity_a
        # '- common_dep
        # '- direct_dep_a
        #    '- common_dep
        #    '- indirect_dep
        # '- direct_dep_b
        #    '- common_dep

        common_dep = (Identifier("lib"), _Path("common_dep.vhd"))
        indirect_dep = (Identifier("lib"), _Path("indirect_dep.vhd"))
        direct_dep_a = (Identifier("lib"), _Path("direct_dep_a.vhd"))
        direct_dep_b = (Identifier("lib"), _Path("direct_dep_a.vhd"))

        # First item must be common dep
        self.assertEqual(sequence[0], common_dep)

        # indirect_dep must come before direct_dep_a
        self.assertIn(indirect_dep, sequence)
        self.assertIn(direct_dep_a, sequence)
        self.assertTrue(sequence.index(indirect_dep) < sequence.index(direct_dep_a))

        # If conditions above are respected, direct_dep_b can be anywhere
        self.assertIn(direct_dep_b, sequence)

    def test_GetCorrectDependenciesOfIndirectDep(self):
        # type: (...) -> Any
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("indirect_dep.vhd")),
            {("lib", "common_dep")},
        )


class TestDirectCircularDependencies(TestCase):
    def setUp(self):
        # type: (...) -> Any
        _logger.info("Setting up %s", self)
        self.database = _Database()

        sources = {
            _SourceMock(
                filename=_path("unit_a.vhd"),
                library="lib",
                design_units=[{"name": "unit_a", "type": "entity"}],
                dependencies=[("work", "unit_b")],
            ),
            _SourceMock(
                filename=_path("unit_b.vhd"),
                library="lib",
                design_units=[{"name": "unit_b", "type": "entity"}],
                dependencies=[("work", "unit_a")],
            ),
        }

        self.database._configFromSources(sources, TEST_TEMP_PATH)

    def tearDown(self):
        # type: (...) -> Any
        _logger.info("Tearing down %s", self)
        self.database.test_reportCacheInfo()
        del self.database

    def test_ShouldHandleBothSides(self):
        # type: (...) -> Any
        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_a.vhd")),
            (("lib", "unit_b"),),
        )

        self.assertCountEqual(
            self.database.test_getDependenciesUnits(_Path("unit_b.vhd")),
            (("lib", "unit_a"),),
        )


class TestMultilevelCircularDependencies(TestCase):
    def setUp(self):
        # type: (...) -> Any
        _logger.info("Setting up %s", self)
        self.database = _Database()

        sources = {
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

        self.database._configFromSources(sources, TEST_TEMP_PATH)

    def tearDown(self):
        # type: (...) -> Any
        _logger.info("Tearing down %s", self)
        self.database.test_reportCacheInfo()
        del self.database

    def test_ReportAllButTheSourceInQuestion(self):
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


class TestIndirectLibraryInference(TestCase):
    def setUp(self):
        # type: (...) -> Any
        _logger.info("Setting up %s", self)
        self.database = _Database()

        sources = {
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

        self.database._configFromSources(sources, TEST_TEMP_PATH)

    def tearDown(self):
        # type: (...) -> Any
        _logger.info("Tearing down %s", self)
        self.database.test_reportCacheInfo()
        del self.database

    def test_InferLibraryWhenUsingDirectly(self):
        # type: (...) -> Any
        sequence = tuple(
            self.database.test_getBuildSequence(_Path("no_lib_but_use_it_directly.vhd"))
        )

        self.assertEqual(sequence, ((Identifier("find_me"), _Path("target_pkg.vhd")),))

    def test_InferLibraryFromPath(self):
        # type: (...) -> Any
        sequence = tuple(
            self.database.test_getBuildSequence(
                _Path("with_lib_but_use_it_directly.vhd")
            )
        )

        self.assertEqual(sequence, ((Identifier("find_me"), _Path("target_pkg.vhd")),))


class TestUnitsDefinedInMultipleSources(TestCase):
    maxDiff = None

    def setUp(self):
        # type: (...) -> Any
        _logger.info("Setting up %s", self)
        self.database = _Database()

        sources = {
            _SourceMock(
                filename=_path("no_lib_target.vhd"),
                library=None,
                design_units=[{"name": "no_lib_target", "type": "entity"}],
                dependencies=[
                    ("work", "no_lib_package"),
                    ("work", "dependency"),
                    ("work", "no_lib_package"),
                ],
            ),
            _SourceMock(
                filename=_path("dependency.vhd"),
                library=None,
                design_units=[{"name": "dependency", "type": "package"}],
            ),
            _SourceMock(
                filename=_path("no_lib_package_1.vhd"),
                library=None,
                design_units=[{"name": "no_lib_package", "type": "package"}],
            ),
            _SourceMock(
                filename=_path("no_lib_package_2.vhd"),
                library=None,
                design_units=[{"name": "no_lib_package", "type": "package"}],
            ),
            _SourceMock(
                filename=_path("collateral.vhd"),
                library=None,
                design_units=[{"name": "collateral", "type": "package"}],
            ),
        }

        self.database._configFromSources(sources, TEST_TEMP_PATH)

    def tearDown(self):
        # type: (...) -> Any
        _logger.info("Tearing down %s", self)
        self.database.test_reportCacheInfo()
        del self.database

    def test_BuildSequenceUnitsAreUnique(self):
        # type: (...) -> Any
        # If a design unit is defined in multiple places, we should not include
        # all of them

        # The exact one picked is not fixed (but it has to be constant
        # throughout a session to avoid bouncing)
        self.assertIn(
            set(self.database.test_getBuildSequence(_Path("no_lib_target.vhd"))),
            (
                {
                    (DEFAULT_LIBRARY, _Path("dependency.vhd")),
                    (DEFAULT_LIBRARY, _Path("no_lib_package_1.vhd")),
                },
                {
                    (DEFAULT_LIBRARY, _Path("dependency.vhd")),
                    (DEFAULT_LIBRARY, _Path("no_lib_package_2.vhd")),
                },
            ),
        )

    def test_NonUniqueUnitsAreReported(self):
        # type: (...) -> Any

        # Design units defined in multiple places should trigger
        # DependencyNotUnique in the path's diagnostics

        # Need to get the build sequence before this diag is populated
        list(self.database.test_getBuildSequence(_Path("no_lib_target.vhd")))

        logIterable("all diags", self.database._diags.items(), _logger.info)

        self.assertCountEqual(
            {
                DependencyNotUnique(
                    filename=_Path("no_lib_target.vhd"),
                    dependency=RequiredDesignUnit(
                        owner=_Path("no_lib_target.vhd"),
                        name=Identifier("no_lib_package", False),
                    ),
                    choices={
                        _Path("no_lib_package_1.vhd"),
                        _Path("no_lib_package_2.vhd"),
                    },
                    line_number=1,
                    column_number=4,
                ),
                DependencyNotUnique(
                    filename=_Path("no_lib_target.vhd"),
                    dependency=RequiredDesignUnit(
                        owner=_Path("no_lib_target.vhd"),
                        name=Identifier("no_lib_package", False),
                    ),
                    choices={
                        _Path("no_lib_package_1.vhd"),
                        _Path("no_lib_package_2.vhd"),
                    },
                    line_number=3,
                    column_number=4,
                ),
            },
            self.database.getDiagnosticsForPath(_Path("no_lib_target.vhd")),
        )
        self.assertNotEqual(
            list(
                self.database.getPathsDefining(
                    name=Identifier("no_lib_package"), library=None
                )
            ),
            [],
        )

    def test_TemporaryPathsDontGenerateDiagnostics(self):
        # type: (...) -> Any

        # Create a copy of a source file with same contents but a different
        # name to mimic getting info from a dump (which is in itself a version
        # of an existing file)
        _SourceMock(
            filename=_path("no_lib_package_3.vhd"),
            library=None,
            design_units=[{"name": "no_lib_package", "type": "package"}],
        )
        # This file should be added so that the database is aware of its
        # existence.

        # Add this as a regular file to make sure the test will fail
        self.database.addSource(_Path("no_lib_package_3.vhd"), None)
        with self.assertRaises(AssertionError):
            self.test_NonUniqueUnitsAreReported()
        self.database.removeSource(_Path("no_lib_package_3.vhd"))

        # Now add the same path using TemporaryPath, which should make the
        # previous test pass
        self.database.addSource(TemporaryPath(_path("no_lib_package_3.vhd")), None)

        # Test should run exactly the same as before. If we added using the
        # path.Path class, the test would have failed
        self.test_NonUniqueUnitsAreReported()

    def test_TemporaryPathsAreExcluded(self):
        # type: (...) -> Any
        # This should add diagnostics
        with patch.object(self.database, "_addDiagnostic") as meth:
            name = Identifier("no_lib_package")
            choices = {_Path("no_lib_package_1.vhd"), _Path("no_lib_package_2.vhd")}
            self.database._reportDependencyNotUnique(
                name=name, library=None, choices=choices
            )

            meth.assert_called()

        # This should not
        with patch.object(self.database, "_addDiagnostic") as meth:
            name = Identifier("no_lib_package")
            choices = {
                _Path("no_lib_package_1.vhd"),
                TemporaryPath(_path("no_lib_package_2.vhd")),
            }
            self.database._reportDependencyNotUnique(
                name=name, library=None, choices=choices
            )

            meth.assert_not_called()


class TestResolveIncludes(TestCase):
    @patch("hdl_checker.database.Database._addDiagnostic")
    @patch("hdl_checker.database.Database.paths", new_callable=PropertyMock)
    def test_ResolveIncludePath(self, paths, add_diagnostic):
        # type: (...) -> Any
        database = Database()

        paths.return_value = frozenset(
            [
                Path("/some/path/path_0"),
                Path("/some/path/path_1"),
                Path("/another/base/path/path_1"),
                Path("/yet/another/base/path/path_1"),
                Path("/yet/another/base/path/path_2"),
                Path("/foo/bar/path_2"),
            ]
        )

        def includedPath(name):
            return IncludedPath(
                name=Identifier(name),
                owner=Path("owner"),
                locations=frozenset([Location(0, 0)]),
            )

        self.assertEqual(
            database.resolveIncludedPath(includedPath("path_0")),
            Path("/some/path/path_0"),
        )
        self.assertEqual(
            database.resolveIncludedPath(includedPath("path/path_0")),
            Path("/some/path/path_0"),
        )
        self.assertEqual(database.resolveIncludedPath(includedPath("/path_0")), None)
        add_diagnostic.assert_not_called()

        # Test multiple matches
        self.assertIn(
            database.resolveIncludedPath(includedPath("path/path_1")),
            {
                Path("/some/path/path_1"),
                Path("/another/base/path/path_1"),
                Path("/yet/another/base/path/path_1"),
            },
        )

        add_diagnostic.assert_called_once()
        add_diagnostic.reset_mock()

        self.assertIn(
            database.resolveIncludedPath(includedPath("path_1")),
            {
                Path("/some/path/path_1"),
                Path("/another/base/path/path_1"),
                Path("/yet/another/base/path/path_1"),
            },
        )

        add_diagnostic.assert_called_once()
        add_diagnostic.reset_mock()

        self.assertIn(
            database.resolveIncludedPath(includedPath("path_2")),
            {Path("/yet/another/base/path/path_2"), Path("/foo/bar/path_2")},
        )

        add_diagnostic.assert_called_once()
        paths.assert_called()
