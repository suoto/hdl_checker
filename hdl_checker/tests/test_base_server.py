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
# pylint: disable=useless-object-inheritance

import json
import logging
import os
import os.path as p
import shutil
import tempfile
import time

import six
from mock import patch

from nose2.tools import such  # type: ignore

from hdl_checker.tests import (
    FailingBuilder,
    MockBuilder,
    PatchBuilder,
    SourceMock,
    StandaloneProjectBuilder,
    assertCountEqual,
    assertSameFile,
    getTestTempPath,
    logIterable,
    setupTestSuport,
    writeListToFile,
)

from hdl_checker import CACHE_NAME, WORK_PATH
from hdl_checker.builders.fallback import Fallback
from hdl_checker.diagnostics import (
    CheckerDiagnostic,
    DiagType,
    LibraryShouldBeOmited,
    ObjectIsNeverUsed,
    PathNotInProjectFile,
)
from hdl_checker.parsers.elements.dependency_spec import DependencySpec
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import (
    BuildFlagScope,
    FileType,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)
from hdl_checker.utils import ON_WINDOWS, removeIfExists

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

if six.PY2:
    FileNotFoundError = (  # pylint: disable=redefined-builtin,invalid-name
        IOError,
        OSError,
    )


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
    import hdl_checker

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
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    it.assertSameFile = assertSameFile(it)

    def _assertMsgQueueIsEmpty(project):
        msg = []
        while not project._msg_queue.empty():
            msg += [str(project._msg_queue.get())]

        if msg:
            msg.insert(
                0, "Message queue should be empty but has %d messages" % len(msg)
            )
            it.fail("\n".join(msg))

    it.assertMsgQueueIsEmpty = _assertMsgQueueIsEmpty

    import hdl_checker

    @it.should("warn when setup is taking too long")
    @patch("hdl_checker.base_server._SETUP_IS_TOO_LONG_TIMEOUT", 0.1)
    @patch.object(
        hdl_checker.base_server.HdlCodeCheckerBase,
        "configure",
        lambda *_: time.sleep(0.5),
    )
    def test():

        path = tempfile.mkdtemp()

        config = p.join(path, "config.json")
        source = p.join(path, "source.vhd")

        # Make sure the files exists
        open(config, "w").write("")
        open(source, "w").write("")

        project = StandaloneProjectBuilder(_Path(path))
        project.setConfig(Path(config))
        # Get messages of anything to trigger reading the config
        project.getMessagesByPath(Path(source))

        it.assertCountEqual(
            [("info", hdl_checker.base_server._SETUP_IS_TOO_LONG_MSG)],
            list(project.getUiMessages()),
        )

        removeIfExists(path)

    with it.having("non existing root dir"):

        @it.has_setup
        def setup():
            it.project_file = Path("non_existing_file")
            it.assertFalse(p.exists(it.project_file.name))

        @it.should("raise exception when trying to instantiate")
        def test():
            project = StandaloneProjectBuilder(_Path("nonexisting"))
            with it.assertRaises(FileNotFoundError):
                project.setConfig(str(it.project_file))

    with it.having("no project file at all"):

        @it.has_setup
        def setup():
            it.project = StandaloneProjectBuilder(Path(TEST_PROJECT))

        @it.should("use fallback to Fallback builder")  # type: ignore
        def test():
            it.assertIsInstance(it.project.builder, Fallback)

        @it.should("still report static messages")  # type: ignore
        def test():

            _logger.info("Files: %s", it.project.database._paths)

            source = _SourceMock(
                filename=_path("some_lib_target.vhd"),
                library="some_lib",
                design_units=[{"name": "target", "type": "entity"}],
                dependencies={("work", "foo")},
            )

            it.assertCountEqual(
                it.project.getMessagesByPath(source.filename),
                {
                    LibraryShouldBeOmited(
                        library="work",
                        filename=_Path("some_lib_target.vhd"),
                        line_number=0,
                        column_number=8,
                    )
                },
            )

    with it.having("an existing and valid project file"):

        @it.has_setup
        def setup():
            setupTestSuport(TEST_TEMP_PATH)

            it.project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))

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

            it.project.setConfig(it.config_file)

        @it.should("use MockBuilder builder")  # type: ignore
        def test():
            with PatchBuilder():
                it.assertIsInstance(it.project.builder, MockBuilder)

        @it.should("save cache after checking a source")  # type: ignore
        def test():
            source = _SourceMock(
                library="some_lib", design_units=[{"name": "target", "type": "entity"}]
            )

            with patch("hdl_checker.base_server.json.dump", spec=json.dump) as func:
                it.project.getMessagesByPath(source.filename)
                func.assert_called_once()

        @it.should("recover from cache")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        @patch("hdl_checker.base_server.HdlCodeCheckerBase._setState")
        def test(set_state):
            source = _SourceMock(
                library="some_lib", design_units=[{"name": "target", "type": "entity"}]
            )

            it.project.getMessagesByPath(source.filename)

            _ = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))

            set_state.assert_called_once()

            # Setting the config file should not trigger reparsing
            with patch.object(it.project, "_readConfig") as read_config:
                with patch(
                    "hdl_checker.base_server.WatchedFile.__init__", side_effect=[None]
                ) as watched_file:
                    old = it.project.config_file
                    it.project.setConfig(it.config_file)
                    it.project._updateConfigIfNeeded()
                    it.assertEqual(it.project.config_file, old)
                    read_config.assert_not_called()
                    watched_file.assert_not_called()

        @it.should("clean up root dir")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        def test():
            if not ON_WINDOWS:
                it.assertCountEqual(
                    [("info", "Added 0 sources")],
                    list(it.project.getUiMessages()),
                )

            it.project.clean()

            project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(project)

            # Reset the project to the previous state
            setup()

        @it.should("warn when failing to recover from cache")  # type: ignore
        def test():
            it.project._saveCache()
            # Copy parameters of the object we're checking against
            root_dir = it.project.root_dir
            cache_filename = it.project._getCacheFilename()

            #  it.assertIsInstance(it.project.builder, Fallback)

            # Corrupt the cache file
            open(cache_filename.name, "w").write("corrupted cache contents")

            # Try to recreate
            project = StandaloneProjectBuilder(root_dir)

            if six.PY2:
                it.assertIn(
                    (
                        "warning",
                        "Unable to recover cache from '{}': "
                        "No JSON object could be decoded".format(cache_filename),
                    ),
                    list(project.getUiMessages()),
                )
            else:
                it.assertIn(
                    (
                        "warning",
                        "Unable to recover cache from '{}': "
                        "Expecting value: line 1 column 1 (char 0)".format(
                            cache_filename
                        ),
                    ),
                    list(project.getUiMessages()),
                )

            it.assertIsInstance(project.builder, Fallback)

        @it.should("get builder messages by path")  # type: ignore
        # Avoid saving to cache because the patched method is not JSON
        # serializable
        @patch("hdl_checker.base_server.json.dump")
        def test(_):
            with PatchBuilder():
                it.project.setConfig(Path(p.join(TEST_PROJECT, "vimhdl.prj")))
                it.project._readConfig()

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

            clock_divider = DependencySpec(
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

        @it.should("Not resolve dependencies whose library is built in")  # type: ignore
        def test():
            path = _Path(TEST_PROJECT, "another_library", "foo.vhd")

            numeric_std = DependencySpec(
                name=Identifier("numeric_std"),
                library=Identifier("ieee"),
                owner=path,
                locations=(),
            )

            it.assertIs(it.project.resolveDependencyToPath(numeric_std), None)

        @it.should(  # type: ignore
            "warn when unable to recreate a builder described in cache"
        )
        @patch(
            "hdl_checker.base_server.getBuilderByName", new=lambda name: FailingBuilder
        )
        def test():
            if ON_WINDOWS:
                raise it.skipTest("Test doesn't run on Windows")

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
        def setup():
            setupTestSuport(TEST_TEMP_PATH)

            removeIfExists(p.join(TEST_TEMP_PATH, WORK_PATH, CACHE_NAME))

            with PatchBuilder():
                it.project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))
                it.project.setConfig(Path(p.join(TEST_PROJECT, "vimhdl.prj")))
                it.project._updateConfigIfNeeded()

            from pprint import pformat

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

            if not ON_WINDOWS:
                it.assertCountEqual(
                    [("info", "Added 10 sources")],
                    list(it.project.getUiMessages()),
                )

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

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

            it.assertTrue(it.project.database.paths)

        @it.should("get messages for relative path")  # type: ignore
        def test():
            filename = p.relpath(
                p.join(TEST_PROJECT, "another_library", "foo.vhd"),
                str(it.project.root_dir),
            )

            it.assertFalse(p.isabs(filename))

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

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

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

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

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

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
            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

        @it.should(  # type: ignore
            "get messages with text for file outside the project file"
        )
        def test():
            filename = Path(p.join(TEST_TEMP_PATH, "some_file.vhd"))
            writeListToFile(str(filename), ["entity some_entity is end;"])

            content = "\n".join(
                ["library work;", "use work.all;", "entity some_entity is end;"]
            )

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesWithText(filename, content)

            _logger.debug("Records received:")
            for diagnostic in diagnostics:
                _logger.debug("- %s", diagnostic)

            expected = [
                LibraryShouldBeOmited(
                    library="work", filename=filename, column_number=8, line_number=0
                ),
                PathNotInProjectFile(filename),
            ]

            try:
                it.assertCountEqual(expected, diagnostics)
            except:
                _logger.warning("Expected:")
                for exp in expected:
                    _logger.warning(exp)

                raise

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

        @it.should("get updated messages")  # type: ignore
        def test():
            filename = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

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

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages by path of a different source")  # type: ignore
        def test():
            filename = Path(p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd"))

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

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

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

        @it.should(  # type: ignore
            "get messages from a source outside the project file"
        )
        def test():
            filename = Path(p.join(TEST_TEMP_PATH, "some_file.vhd"))
            writeListToFile(str(filename), ["library some_lib;"])

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

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

            if not ON_WINDOWS:
                it.assertMsgQueueIsEmpty(it.project)

        def basicRebuildTest(test_filename, rebuilds):
            calls = []
            ret_list = list(reversed(rebuilds))

            # Rebuild formats are:
            # - {unit_type: '', 'unit_name': }
            # - {library_name: '', 'unit_name': }
            # - {rebuild_path: ''}
            def _buildAndParse(_, path, library, forced=False):
                _logger.warning("%s, %s, %s", path, library, forced)
                calls.append(str(path))
                if ret_list:
                    return [], ret_list.pop()
                return [], []

            with patch.object(MockBuilder, "_buildAndParse", _buildAndParse):
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

        @it.should("rebuild sources with path as a hint")
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
        def test():
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

            # Not sure why this is needed, might be hiding something weird
            time.sleep(0.1)

            ui_msgs = list(it.project.getUiMessages())
            logIterable("UI messages", ui_msgs, _logger.info)

            it.assertIn(
                ("error", "Unable to build '{}' after 20 attempts".format(filename)),
                ui_msgs,
            )


it.createTests(globals())
