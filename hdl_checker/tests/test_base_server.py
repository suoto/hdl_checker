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
import shutil
import tempfile
import time
from pprint import pformat

from mock import patch

from nose2.tools import such  # type: ignore

from hdl_checker.tests import (
    DummyServer,
    FailingBuilder,
    MockBuilder,
    PatchBuilder,
    SourceMock,
    assertSameFile,
    getTestTempPath,
    linuxOnly,
    logIterable,
    setupTestSuport,
    writeListToFile,
)

import hdl_checker
from hdl_checker import CACHE_NAME, WORK_PATH
from hdl_checker.builders.fallback import Fallback
from hdl_checker.diagnostics import (
    CheckerDiagnostic,
    DiagType,
    LibraryShouldBeOmited,
    ObjectIsNeverUsed,
    PathNotInProjectFile,
    UnresolvedDependency,
)
from hdl_checker.parsers.elements.dependency_spec import RequiredDesignUnit
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import (
    BuildFlagScope,
    ConfigFileOrigin,
    FileType,
    Location,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)
from hdl_checker.utils import removeIfExists

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")


class _SourceMock(SourceMock):
    base_path = TEST_TEMP_PATH


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


def _Path(*args):
    # type: (str) -> Path
    return Path(_path(*args))


def patchClassMap(**kwargs):
    class_map = hdl_checker.serialization.CLASS_MAP.copy()
    for name, value in kwargs.items():
        class_map.update({name: value})

    return patch("hdl_checker.serialization.CLASS_MAP", class_map)


def _makeConfigFromDict(dict_):
    # type: (...) -> str
    filename = p.join(TEST_TEMP_PATH, "mock.prj")
    json.dump(dict_, open(filename, "w"))
    return filename


such.unittest.TestCase.maxDiff = None

with such.A("hdl_checker project") as it:
    it.assertSameFile = assertSameFile(it)

    @it.should("warn when setup is taking too long")
    @patch("hdl_checker.base_server._HOW_LONG_IS_TOO_LONG", 0.1)
    @patch.object(
        hdl_checker.base_server.BaseServer, "configure", lambda *_: time.sleep(0.5)
    )
    @patch("hdl_checker.tests.DummyServer._handleUiInfo")
    def test(handle_ui_info):

        path = tempfile.mkdtemp()

        config = p.join(path, "config.json")
        source = p.join(path, "source.vhd")

        # Make sure the files exist
        open(config, "w").write("")
        open(source, "w").write("")

        project = DummyServer(_Path(path))
        project.setConfig(_Path(config), origin=ConfigFileOrigin.generated)
        # Get messages of anything to trigger reading the config
        project.getMessagesByPath(Path(source))

        handle_ui_info.assert_called_once_with(
            hdl_checker.base_server._HOW_LONG_IS_TOO_LONG_MSG
        )

        removeIfExists(path)

    @it.should(  # type: ignore
        "not warn when setup is taking too long if the user provides the config file"
    )
    @patch("hdl_checker.base_server._HOW_LONG_IS_TOO_LONG", 0.1)
    @patch.object(
        hdl_checker.base_server.BaseServer, "configure", lambda *_: time.sleep(0.5)
    )
    @patch("hdl_checker.tests.DummyServer._handleUiInfo")
    def test(handle_ui_info):

        path = tempfile.mkdtemp()

        config = p.join(path, "config.json")
        source = p.join(path, "source.vhd")

        # Make sure the files exist
        open(config, "w").write("")
        open(source, "w").write("")

        project = DummyServer(_Path(path))
        project.setConfig(Path(config), origin=ConfigFileOrigin.user)
        # Get messages of anything to trigger reading the config
        project.getMessagesByPath(Path(source))

        handle_ui_info.assert_not_called()

        removeIfExists(path)

    @it.should(  # type: ignore
        "not warn when setup takes less than _HOW_LONG_IS_TOO_LONG"
    )
    @patch("hdl_checker.tests.DummyServer._handleUiInfo")
    def test(handle_ui_info):
        path = tempfile.mkdtemp()

        config = p.join(path, "config.json")
        source = p.join(path, "source.vhd")

        # Make sure the files exists
        open(config, "w").write("")
        open(source, "w").write("")

        project = DummyServer(_Path(path))
        project.setConfig(Path(config), origin=ConfigFileOrigin.user)
        # Get messages of anything to trigger reading the config
        project.getMessagesByPath(Path(source))

        handle_ui_info.assert_called_once_with("No sources were added")

        removeIfExists(path)

    @it.should("warn when unable to resolve non-builtin dependencies")  # type: ignore
    @patch(
        "hdl_checker.builders.fallback.Fallback._parseBuiltinLibraries",
        return_value=[Identifier("builtin")],
    )
    def test(parse_builtins):
        # type: (...) -> None
        root = tempfile.mkdtemp()
        server = DummyServer(Path(root))

        with tempfile.NamedTemporaryFile(suffix=".vhd") as filename:
            diags = server.getMessagesWithText(
                Path(filename.name),
                "library lib; use lib.pkg.all; library builtin; use builtin.foo;",
            )

            parse_builtins.assert_called()

            logIterable("Diags", diags, _logger.info)

            it.assertCountEqual(
                diags,
                [
                    UnresolvedDependency(
                        RequiredDesignUnit(
                            name=Identifier("pkg"),
                            library=Identifier("lib"),
                            owner=Path(filename.name),
                            locations=[Location(0, 17)],
                        ),
                        Location(0, 17),
                    )
                ],
            )

    with it.having("non existing root dir"):

        @it.has_setup
        def setup():
            it.project_file = Path("non_existing_file")
            it.assertFalse(p.exists(it.project_file.name))

        @it.should("raise exception when trying to instantiate")  # type: ignore
        def test():
            project = DummyServer(_Path("nonexisting"))
            with it.assertRaises(FileNotFoundError):
                project.setConfig(str(it.project_file), origin=ConfigFileOrigin.user)

    with it.having("no project file at all"):

        @it.has_setup
        def setup():
            it.project = DummyServer(Path(TEST_PROJECT))

        @it.should("use fallback to Fallback builder")  # type: ignore
        def test():
            it.assertIsInstance(it.project.builder, Fallback)

        @it.should("restore state from a saved cache")  # type: ignore
        def test():
            it.project._saveCache()
            it.project._recoverCacheIfPossible()
            it.assertIsNone(it.project.config_file)

        @it.should("still report static messages")  # type: ignore
        @patch(
            "hdl_checker.base_server.getStaticMessages",
            return_value=[CheckerDiagnostic(text="some text")],
        )
        def test(meth):

            _logger.info("Files: %s", it.project.database._paths)

            source = _SourceMock(
                filename=_path("some_lib_target.vhd"),
                library="some_lib",
                design_units=[{"name": "target", "type": "entity"}],
                dependencies={("work", "foo")},
            )

            it.assertIn(
                CheckerDiagnostic(filename=Path(source.filename), text="some text"),
                it.project.getMessagesByPath(source.filename),
            )

            # Will be called with the file's contents
            meth.assert_called_once()

    with it.having("an existing and valid project file"):

        @it.has_setup
        def setup():
            setupTestSuport(TEST_TEMP_PATH)

            it.project = DummyServer(_Path(TEST_TEMP_PATH))

            it.config_file = _makeConfigFromDict(
                {
                    "builder": MockBuilder.builder_name,
                    FileType.vhdl.value: {
                        "flags": {
                            BuildFlagScope.all.value: (
                                "-globalvhdl",
                                "-global-vhdl-flag",
                            ),
                            BuildFlagScope.dependencies.value: ("--vhdl-batch",),
                            BuildFlagScope.single.value: ("-single_build_flag_0",),
                        }
                    },
                    FileType.verilog.value: {
                        "flags": {
                            BuildFlagScope.all.value: (
                                "-globalverilog",
                                "-global-verilog-flag",
                            ),
                            BuildFlagScope.dependencies.value: ("--verilog-batch",),
                            BuildFlagScope.single.value: ("-single_build_flag_0",),
                        }
                    },
                    FileType.systemverilog.value: {
                        "flags": {
                            BuildFlagScope.all.value: (
                                "-globalsystemverilog",
                                "-global-systemverilog-flag",
                            ),
                            BuildFlagScope.dependencies.value: (
                                "--systemverilog-batch",
                            ),
                            BuildFlagScope.single.value: ("-single_build_flag_0",),
                        }
                    },
                }
            )

            with PatchBuilder():
                it.project.setConfig(it.config_file, origin=ConfigFileOrigin.user)

        @it.should("use MockBuilder builder")  # type: ignore
        def test():
            # Just to make sure patch worked
            it.assertEqual(it.project.builder.builder_name, MockBuilder.builder_name)

        @it.should("save cache after checking a source")  # type: ignore
        def test():
            source = _SourceMock(
                library="some_lib", design_units=[{"name": "target", "type": "entity"}]
            )

            with patch("hdl_checker.base_server.json.dump", spec=json.dump) as func:
                it.project.getMessagesByPath(source.filename)
                func.assert_called_once()

        @it.should("restore state from a saved cache")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        def test():
            it.project._saveCache()
            it.project._recoverCacheIfPossible()
            it.assertIsNotNone(it.project.config_file)

        @it.should("not reparse when setting the config file")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        def test():
            it.project._saveCache()

            _ = DummyServer(_Path(TEST_TEMP_PATH))

            # Setting the config file should not trigger reparsing
            with patch(
                "hdl_checker.base_server.WatchedFile.__init__", side_effect=[None]
            ) as watched_file:
                old = it.project.config_file
                it.project.setConfig(it.config_file, origin=ConfigFileOrigin.user)
                it.project._updateConfigIfNeeded()
                it.assertEqual(it.project.config_file, old)
                watched_file.assert_not_called()
                it.assertIsNotNone(it.project.config_file)

        @it.should("not recover cache if versions differ")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        @patch("hdl_checker.base_server.json.load", return_value={"__version__": None})
        def test(json_load):
            source = _SourceMock(
                library="some_lib", design_units=[{"name": "target", "type": "entity"}]
            )

            it.project.getMessagesByPath(source.filename)

            # Set state must only be called when recovering from cache
            with patch.object(it.project, "_setState") as set_state:
                it.project._recoverCacheIfPossible()
                json_load.assert_called_once()
                set_state.assert_not_called()

        @it.should("clean up and reparse if the config file changes")  # type: ignore
        @linuxOnly
        @patchClassMap(MockBuilder=MockBuilder)
        def test():
            # Make sure everything is up to date prior to running
            with patch.object(it.project, "configure") as configure:
                it.project._updateConfigIfNeeded()
                configure.assert_not_called()

            # Write the same thing into the file just to change the timestamp
            previous = p.getmtime(it.config_file)
            contents = open(it.config_file).read()
            open(it.config_file, "w").write(contents)
            it.assertNotEqual(
                previous,
                p.getmtime(it.config_file),
                "Modification times should have changed",
            )

            # Check that thing are updated
            with patch.object(it.project, "configure") as configure:
                it.project._updateConfigIfNeeded()
                configure.assert_called_once()

        @it.should("warn when failing to recover from cache")  # type: ignore
        @patch("hdl_checker.tests.DummyServer._handleUiWarning")
        def test(handle_ui_warning):
            it.project._saveCache()
            # Copy parameters of the object we're checking against
            root_dir = it.project.root_dir
            cache_filename = it.project._getCacheFilename()

            # Corrupt the cache file
            open(cache_filename.name, "w").write("corrupted cache contents")

            # Try to recreate
            project = DummyServer(root_dir)

            handle_ui_warning.assert_called_once_with(
                "Unable to recover cache from '{}': "
                "Expecting value: line 1 column 1 (char 0)".format(cache_filename)
            )

            it.assertIsInstance(project.builder, Fallback)

        @it.should("get builder messages by path")  # type: ignore
        # Avoid saving to cache because the patched method is not JSON
        # serializable
        @patch("hdl_checker.base_server.json.dump")
        def test(_):
            with PatchBuilder():
                it.project.setConfig(
                    Path(p.join(TEST_PROJECT, "vimhdl.prj")),
                    origin=ConfigFileOrigin.user,
                )
                it.project._updateConfigIfNeeded()

            entity_a = _SourceMock(
                filename=_path("entity_a.vhd"),
                library="some_lib",
                design_units=[{"name": "entity_a", "type": "entity"}],
                dependencies={("work", "foo")},
            )

            path_to_foo = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))

            diags = {
                # entity_a.vhd is the path we're compiling, inject a diagnostic
                # from the builder
                str(entity_a.filename): [
                    [
                        CheckerDiagnostic(
                            filename=entity_a.filename, checker=None, text="some text"
                        )
                    ]
                ],
                # foo.vhd is on the build sequence, check that diagnostics from
                # the build sequence are only included when their severity is
                # DiagType.ERROR
                str(path_to_foo): [
                    [
                        CheckerDiagnostic(
                            filename=path_to_foo,
                            checker=None,
                            text="should not be included",
                            severity=DiagType.WARNING,
                        ),
                        CheckerDiagnostic(
                            filename=path_to_foo,
                            checker=None,
                            text="style error should be included",
                            severity=DiagType.STYLE_ERROR,
                        ),
                        CheckerDiagnostic(
                            filename=path_to_foo,
                            checker=None,
                            text="should be included",
                            severity=DiagType.ERROR,
                        ),
                    ]
                ],
            }

            def build(  # pylint: disable=unused-argument
                path, library, scope, forced=False
            ):
                _logger.debug("Building library=%s, path=%s", library, path)
                path_diags = diags.get(str(path), [])
                if path_diags:
                    return path_diags.pop(), []
                return [], []

            with patch.object(it.project.builder, "build", build):
                _logger.info("Project paths: %s", it.project.database._paths)
                messages = list(it.project.getMessagesByPath(entity_a.filename))
                logIterable("Messages", messages, _logger.info)
                it.assertCountEqual(
                    messages,
                    [
                        LibraryShouldBeOmited(
                            library="work",
                            filename=entity_a.filename,
                            column_number=8,
                            line_number=0,
                        ),
                        PathNotInProjectFile(entity_a.filename),
                        CheckerDiagnostic(
                            filename=entity_a.filename, checker=None, text="some text"
                        ),
                        CheckerDiagnostic(
                            filename=path_to_foo,
                            checker=None,
                            text="style error should be included",
                            severity=DiagType.STYLE_ERROR,
                        ),
                        CheckerDiagnostic(
                            filename=path_to_foo,
                            checker=None,
                            text="should be included",
                            severity=DiagType.ERROR,
                        ),
                    ],
                )

        @it.should("Resolve dependency to path")  # type: ignore
        def test():
            path = _Path(TEST_PROJECT, "another_library", "foo.vhd")

            clock_divider = RequiredDesignUnit(
                name=Identifier("clock_divider"),
                library=Identifier("basic_library"),
                owner=path,
                locations=(),
            )

            it.assertEqual(
                it.project.resolveDependencyToPath(clock_divider),
                (
                    _Path(TEST_PROJECT, "basic_library", "clock_divider.vhd"),
                    Identifier("basic_library"),
                ),
            )

        @it.should(  # type: ignore
            "Resolve dependency to path when it's defined on the same file"
        )
        def test():
            path = _Path(TEST_PROJECT, "basic_library", "package_with_functions.vhd")

            clock_divider = RequiredDesignUnit(
                name=Identifier("package_with_functions"),
                library=Identifier("basic_library"),
                owner=path,
                locations=(),
            )

            it.assertEqual(
                it.project.resolveDependencyToPath(clock_divider),
                (path, Identifier("basic_library")),
            )

        @it.should("Not resolve dependencies whose library is built in")  # type: ignore
        def test():
            path = _Path(TEST_PROJECT, "another_library", "foo.vhd")

            numeric_std = RequiredDesignUnit(
                name=Identifier("numeric_std"),
                library=Identifier("ieee"),
                owner=path,
                locations=(),
            )

            it.assertIs(it.project.resolveDependencyToPath(numeric_std), None)

        @it.should(  # type: ignore
            "warn when unable to recreate a builder described in cache"
        )
        @linuxOnly
        @patch(
            "hdl_checker.base_server.getBuilderByName", new=lambda name: FailingBuilder
        )
        def test():
            cache_content = {"builder": FailingBuilder.builder_name}

            cache_path = it.project._getCacheFilename()
            if p.exists(p.dirname(cache_path.name)):
                shutil.rmtree(p.dirname(cache_path.name))

            os.makedirs(p.dirname(cache_path.name))

            with open(cache_path.name, "w") as fd:
                fd.write(repr(cache_content))

            found = True
            while not it.project._msg_queue.empty():
                severity, message = it.project._msg_queue.get()
                _logger.info("Message found: [%s] %s", severity, message)
                if (
                    message
                    == "Failed to create builder '%s'" % FailingBuilder.builder_name
                ):
                    found = True
                    break

            it.assertTrue(found, "Failed to warn that cache recovering has failed")
            it.assertTrue(it.project.builder.builder_name, "Fallback")

    with it.having("test_project as reference and a valid project file"):

        @it.has_setup
        @patch("hdl_checker.tests.DummyServer._handleUiInfo")
        def setup(handle_ui_info):
            setupTestSuport(TEST_TEMP_PATH)

            removeIfExists(p.join(TEST_TEMP_PATH, WORK_PATH, CACHE_NAME))

            with PatchBuilder():
                it.project = DummyServer(_Path(TEST_TEMP_PATH))
                it.project.setConfig(
                    Path(p.join(TEST_PROJECT, "vimhdl.prj")),
                    origin=ConfigFileOrigin.user,
                )
                it.project._updateConfigIfNeeded()
                handle_ui_info.assert_called_once_with("Added 10 sources")

            _logger.info(
                "Database state:\n%s", pformat(it.project.database.__jsonEncode__())
            )

            it.assertTrue(it.project.database.paths)
            it.assertIsInstance(it.project.builder, MockBuilder)

        @it.should("use mock builder")  # type: ignore
        def test():
            it.assertIsInstance(it.project.builder, MockBuilder)

        @it.should("get messages for an absolute path")  # type: ignore
        def test():
            filename = p.join(TEST_PROJECT, "another_library", "foo.vhd")

            diagnostics = it.project.getMessagesByPath(Path(filename))

            it.assertIn(
                ObjectIsNeverUsed(
                    filename=Path(filename),
                    line_number=28,
                    column_number=11,
                    object_type="signal",
                    object_name="neat_signal",
                ),
                diagnostics,
            )

            it.assertTrue(it.project.database.paths)

        @it.should("get messages for relative path")  # type: ignore
        def test():
            filename = p.relpath(
                p.join(TEST_PROJECT, "another_library", "foo.vhd"),
                str(it.project.root_dir),
            )

            it.assertFalse(p.isabs(filename))

            diagnostics = it.project.getMessagesByPath(Path(filename))

            it.assertIn(
                ObjectIsNeverUsed(
                    filename=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
                    line_number=28,
                    column_number=11,
                    object_type="signal",
                    object_name="neat_signal",
                ),
                diagnostics,
            )

        @it.should("get messages with text")  # type: ignore
        def test():
            it.assertTrue(it.project.database.paths)

            filename = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))
            original_content = open(filename.name, "r").read().split("\n")

            content = "\n".join(
                original_content[:28]
                + ["signal another_signal : std_logic;"]
                + original_content[28:]
            )

            _logger.debug("File content")
            for lnum, line in enumerate(content.split("\n")):
                _logger.debug("%2d| %s", (lnum + 1), line)

            diagnostics = set(it.project.getMessagesWithText(filename, content))

            logIterable("Diagnostics", diagnostics, _logger.info)

            it.assertTrue(it.project.config_file)

            expected = [
                ObjectIsNeverUsed(
                    filename=filename,
                    line_number=29,
                    column_number=11,
                    object_type="signal",
                    object_name="neat_signal",
                ),
                ObjectIsNeverUsed(
                    filename=filename,
                    line_number=28,
                    column_number=7,
                    object_type="signal",
                    object_name="another_signal",
                ),
            ]

            it.assertCountEqual(diagnostics, expected)

        @it.should(  # type: ignore
            "get messages with text for file outside the project file"
        )
        def test():
            filename = Path(p.join(TEST_TEMP_PATH, "some_file.vhd"))
            writeListToFile(str(filename), ["entity some_entity is end;"])

            content = "\n".join(
                ["library work;", "use work.all;", "entity some_entity is end;"]
            )

            diagnostics = it.project.getMessagesWithText(filename, content)

            _logger.debug("Records received:")
            for diagnostic in diagnostics:
                _logger.debug("- %s", diagnostic)

            it.assertIn(
                LibraryShouldBeOmited(
                    library="work", filename=filename, column_number=8, line_number=0
                ),
                diagnostics,
            )

            it.assertIn(PathNotInProjectFile(filename), diagnostics)

        @it.should("get updated messages")  # type: ignore
        def test():
            filename = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))

            code = open(str(filename), "r").read().split("\n")

            code[28] = "-- " + code[28]

            writeListToFile(str(filename), code)

            diagnostics = it.project.getMessagesByPath(filename)

            try:
                it.assertNotIn(
                    ObjectIsNeverUsed(
                        object_type="constant",
                        object_name="ADDR_WIDTH",
                        line_number=28,
                        column_number=13,
                    ),
                    diagnostics,
                )
            finally:
                # Remove the comment we added
                code[28] = code[28][3:]
                writeListToFile(str(filename), code)

        @it.should("get messages by path of a different source")  # type: ignore
        def test():
            filename = Path(p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd"))

            it.assertCountEqual(
                it.project.getMessagesByPath(filename),
                [
                    ObjectIsNeverUsed(
                        filename=filename,
                        line_number=26,
                        column_number=11,
                        object_type="signal",
                        object_name="clk_enable_unused",
                    )
                ],
            )

        @it.should(  # type: ignore
            "get messages from a source outside the project file"
        )
        def test():
            filename = Path(p.join(TEST_TEMP_PATH, "some_file.vhd"))
            writeListToFile(str(filename), ["library some_lib;"])

            diagnostics = it.project.getMessagesByPath(filename)

            _logger.info("Records found:")
            for diagnostic in diagnostics:
                _logger.info(diagnostic)

            it.assertIn(PathNotInProjectFile(filename), diagnostics)

            # The builder should find other issues as well...
            it.assertTrue(
                len(diagnostics) > 1,
                "It was expected that the builder added some "
                "message here indicating an error",
            )

        def basicRebuildTest(test_filename, rebuilds):
            calls = []
            ret_list = list(reversed(rebuilds))

            # Rebuild formats are:
            # - {unit_type: '', 'unit_name': }
            # - {library_name: '', 'unit_name': }
            # - {rebuild_path: ''}
            def _buildAndGetDiagnostics(_, path, library, forced=False):
                _logger.warning("%s, %s, %s", path, library, forced)
                calls.append(str(path))
                if ret_list:
                    return [], ret_list.pop()
                return [], []

            with patch.object(
                MockBuilder, "_buildAndGetDiagnostics", _buildAndGetDiagnostics
            ):
                it.assertFalse(
                    list(it.project._getBuilderMessages(Path(test_filename)))
                )

            it.assertFalse(ret_list, "Some rebuilds were not used: {}".format(ret_list))

            return calls

        def _RebuildLibraryUnit(name, library):
            return RebuildLibraryUnit(
                name=Identifier(name), library=Identifier(library)
            )

        @it.should(  # type: ignore
            "rebuild sources when needed within the same library"
        )
        def test():
            it.project.database._clearLruCaches()
            filename = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
            rebuilds = [
                [_RebuildLibraryUnit(name="clock_divider", library="basic_library")]
            ]

            logIterable("Design units", it.project.database.design_units, _logger.info)
            calls = basicRebuildTest(filename, rebuilds)

            # Calls should be
            # - first to build the source we wanted
            # - second to build the file we said needed to be rebuilt
            # - third should build the original source after handling a rebuild
            it.assertEqual(
                calls,
                [
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                ],
            )

        @it.should(  # type: ignore
            "rebuild sources when changing a package on different libraries"
        )
        def test():
            filename = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")
            rebuilds = [[_RebuildLibraryUnit(library="another_library", name="foo")]]

            calls = basicRebuildTest(filename, rebuilds)

            # Calls should be
            # - first to build the source we wanted
            # - second to build the file we said needed to be rebuilt
            # - third should build the original source after handling a rebuild
            it.assertEqual(
                calls,
                [
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                    p.join(TEST_PROJECT, "another_library", "foo.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                ],
            )

        def _RebuildPath(path):
            return RebuildPath(Path(path))

        @it.should("rebuild sources with path as a hint")  # type: ignore
        def test():
            filename = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

            abs_path = p.join(
                TEST_PROJECT, "basic_library", "package_with_constants.vhd"
            )

            # Force relative path as well
            rel_path = p.relpath(abs_path, str(it.project.root_dir))

            it.assertFalse(p.isabs(rel_path))

            rebuilds = [[_RebuildPath(rel_path)]]

            calls = basicRebuildTest(filename, rebuilds)

            #  Calls should be
            #  - first to build the source we wanted
            #  - second to build the file we said needed to be rebuilt
            #  - third should build the original source after handling a rebuild
            it.assertEqual(
                calls,
                [
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                    abs_path,
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                ],
            )

        def _RebuildUnit(name, type_):
            return RebuildUnit(name=Identifier(name), type_=Identifier(type_))

        @it.should("rebuild package if needed")  # type: ignore
        def test():
            filename = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

            # - {unit_type: '', 'unit_name': }
            rebuilds = [[_RebuildUnit(name="very_common_pkg", type_="package")]]

            calls = basicRebuildTest(filename, rebuilds)

            # Calls should be
            # - first to build the source we wanted
            # - second to build the file we said needed to be rebuilt
            # - third should build the original source after handling a rebuild
            it.assertEqual(
                calls,
                [
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "very_common_pkg.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                ],
            )

        @it.should("rebuild a combination of all")  # type: ignore
        def test():
            filename = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

            # - {unit_type: '', 'unit_name': }
            rebuilds = [
                [
                    _RebuildUnit(name="very_common_pkg", type_="package"),
                    _RebuildPath(
                        p.join(
                            TEST_PROJECT, "basic_library", "package_with_constants.vhd"
                        )
                    ),
                    _RebuildLibraryUnit(name="foo", library="another_library"),
                ]
            ]

            calls = basicRebuildTest(filename, rebuilds)

            # Calls should be
            # - first to build the source we wanted
            # - second to build the file we said needed to be rebuilt
            # - third should build the original source after handling a rebuild
            it.assertEqual(
                calls,
                [
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "very_common_pkg.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "package_with_constants.vhd"),
                    p.join(TEST_PROJECT, "another_library", "foo.vhd"),
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                ],
            )

        @it.should("give up trying to rebuild after 20 attempts")  # type: ignore
        @patch("hdl_checker.tests.DummyServer._handleUiError")
        def test(handle_ui_error):
            filename = p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd")

            # - {unit_type: '', 'unit_name': }
            rebuilds = 20 * [
                [_RebuildLibraryUnit(name="foo", library="another_library")],
                [],
            ]

            calls = basicRebuildTest(filename, rebuilds)

            # Calls should be
            # - first to build the source we wanted
            # - second to build the file we said needed to be rebuilt
            # - third should build the original source after handling a rebuild
            it.assertEqual(
                calls,
                20
                * [
                    p.join(TEST_PROJECT, "basic_library", "clk_en_generator.vhd"),
                    p.join(TEST_PROJECT, "another_library", "foo.vhd"),
                ],
            )

            handle_ui_error.assert_called_once_with(
                "Unable to build '{}' after 20 attempts".format(filename)
            )


it.createTests(globals())
