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
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=useless-object-inheritance

import json
import logging
import os
import os.path as p
import shutil
import time

import mock
import six

#  import unittest2
#  from mock import patch
from nose2.tools import such  # type: ignore

from hdlcc.builders.fallback import Fallback
from hdlcc.diagnostics import (
    CheckerDiagnostic,
    DiagType,
    LibraryShouldBeOmited,
    ObjectIsNeverUsed,
    PathNotInProjectFile,
)
from hdlcc.hdlcc_base import CACHE_NAME
from hdlcc.parsers.config_parser import ConfigParser
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.path import Path
from hdlcc.tests.utils import (
    FailingBuilder,
    MockBuilder,
    SourceMock,
    StandaloneProjectBuilder,
    assertCountEqual,
    assertSameFile,
    disableVunit,
    getTestTempPath,
    logIterable,
    setupTestSuport,
    writeListToFile,
)
from hdlcc.types import (
    BuildFlagScope,
    FileType,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)
from hdlcc.utils import removeIfExists

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
    import hdlcc

    class_map = hdlcc.serialization.CLASS_MAP.copy()
    for name, value in kwargs.items():
        class_map.update({name: value})

    return mock.patch("hdlcc.serialization.CLASS_MAP", class_map)


def _configWithDict(dict_):
    # type: (...) -> str
    filename = p.join(TEST_TEMP_PATH, "mock.prj")
    json.dump(dict_, open(filename, "w"))
    return filename

such.unittest.TestCase.maxDiff = None

with such.A("hdlcc project") as it:
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

    with it.having("non existing project file"):

        @it.has_setup
        def setup():
            it.project_file = Path("non_existing_file")
            it.assertFalse(p.exists(it.project_file.name))

        @it.should("raise exception when trying to instantiate")
        def test():
            project = StandaloneProjectBuilder(_Path("nonexisting"))
            with it.assertRaises((OSError, IOError)):
                project.readConfig(str(it.project_file))

    with it.having("no project file at all"):

        @it.has_setup
        def setup():
            it.project = StandaloneProjectBuilder(Path(TEST_PROJECT))

        @it.should("use fallback to Fallback builder")  # type: ignore
        def test():
            it.assertTrue(isinstance(it.project.builder, Fallback))

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
                        line_number=1,
                        column_number=9,
                    )
                },
            )

    with it.having("an existing and valid project file"):

        @it.has_setup
        def setup():
            setupTestSuport(TEST_TEMP_PATH)

            def getBuilderByName(*args):  # pylint: disable=unused-argument
                return MockBuilder

            it.parser = _configWithDict(
                {
                    "builder_name": MockBuilder.builder_name,
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

            with mock.patch("hdlcc.hdlcc_base.getBuilderByName", getBuilderByName):
                it.project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))
                it.project.readConfig(it.parser)

        @it.should("use fallback to Fallback builder")  # type: ignore
        def test():
            it.assertTrue(isinstance(it.project.builder, MockBuilder))

        @it.should("save cache after checking a source")  # type: ignore
        def test():
            source = _SourceMock(
                library="some_lib", design_units=[{"name": "target", "type": "entity"}]
            )

            with mock.patch("hdlcc.hdlcc_base.json.dump", spec=json.dump) as func:
                it.project.getMessagesByPath(source.filename)
                func.assert_called_once()

        @it.should("recover from cache")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        def test():
            source = _SourceMock(
                library="some_lib", design_units=[{"name": "target", "type": "entity"}]
            )

            it.project.getMessagesByPath(source.filename)

            project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))

            cache_filename = project._getCacheFilename()

            it.assertIn(
                ("info", "Recovered cache from '{}'".format(cache_filename)),
                list(it.project.getUiMessages()),
            )

        @it.should("clean up root dir")  # type: ignore
        @patchClassMap(MockBuilder=MockBuilder)
        def test():
            it.assertMsgQueueIsEmpty(it.project)
            it.project.clean()

            project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))

            it.assertMsgQueueIsEmpty(project)

            # Reset the project to the previous state
            setup()

        @it.should("warn when failing to recover from cache")  # type: ignore
        def test():
            # Save contents before destroying the object
            root_dir = it.project.root_dir
            cache_filename = it.project._getCacheFilename()

            it.assertFalse(isinstance(it.project.builder, Fallback))

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

            it.assertTrue(
                isinstance(project.builder, Fallback),
                "Builder should be MockBuilderbut it's {} instead".format(
                    type(project.builder)
                ),
            )

        @it.should("get builder messages by path")  # type: ignore
        def test():
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

            with mock.patch("hdlcc.hdlcc_base.json.dump"):
                with mock.patch.object(it.project.builder, "build", build):
                    _logger.info("Project paths: %s", it.project.database._paths)
                    messages = list(it.project.getMessagesByPath(entity_a.filename))
                    logIterable("Messages", messages, _logger.info)
                    it.assertCountEqual(
                        messages,
                        [
                            LibraryShouldBeOmited(
                                library="work",
                                filename=entity_a.filename,
                                column_number=9,
                                line_number=1,
                            ),
                            PathNotInProjectFile(entity_a.filename),
                            CheckerDiagnostic(
                                filename=entity_a.filename,
                                checker=None,
                                text="some text",
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

        @it.should(  # type: ignore
            "warn when unable to recreate a builder described in cache"
        )
        @mock.patch(
            "hdlcc.hdlcc_base.getBuilderByName", new=lambda name: FailingBuilder
        )
        def test():
            cache_content = {"builder": FailingBuilder}

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
            it.project_file = Path(p.join(TEST_PROJECT, "vimhdl.prj"))
            setupTestSuport(TEST_TEMP_PATH)

            it.parser = _configWithDict({"builder_name": MockBuilder.builder_name})
            removeIfExists(p.join(TEST_TEMP_PATH, CACHE_NAME))

            #  with disableVunit:
            with mock.patch("hdlcc.hdlcc_base.getBuilderByName", lambda _: MockBuilder):
                it.project = StandaloneProjectBuilder(_Path(TEST_TEMP_PATH))
                it.project.readConfig(str(it.project_file))

            from pprint import pformat

            _logger.info(
                "Database state:\n%s", pformat(it.project.database.__jsonEncode__())
            )

        @it.should("use mock builder")  # type: ignore
        def test():
            it.assertTrue(
                isinstance(it.project.builder, MockBuilder),
                "Builder should be {} but got {} instead".format(
                    MockBuilder, it.project.builder
                ),
            )

        @it.should("get messages for an absolute path")  # type: ignore
        def test():
            filename = p.join(TEST_PROJECT, "another_library", "foo.vhd")

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesByPath(Path(filename))

            it.assertIn(
                ObjectIsNeverUsed(
                    filename=Path(filename),
                    line_number=29,
                    column_number=12,
                    object_type="signal",
                    object_name="neat_signal",
                ),
                diagnostics,
            )

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages for relative path")  # type: ignore
        def test():
            filename = p.relpath(
                p.join(TEST_PROJECT, "another_library", "foo.vhd"),
                str(it.project.root_dir),
            )

            it.assertFalse(p.isabs(filename))

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesByPath(Path(filename))

            it.assertIn(
                ObjectIsNeverUsed(
                    filename=Path(p.join(TEST_PROJECT, "another_library", "foo.vhd")),
                    line_number=29,
                    column_number=12,
                    object_type="signal",
                    object_name="neat_signal",
                ),
                diagnostics,
            )

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages with text")  # type: ignore
        def test():
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

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesWithText(filename, content)

            if diagnostics:
                _logger.debug("Records received:")
                for diagnostic in diagnostics:
                    _logger.debug("- %s", diagnostic)
            else:
                _logger.warning("No diagnostics found")

            expected = [
                ObjectIsNeverUsed(
                    filename=filename,
                    line_number=30,
                    column_number=12,
                    object_type="signal",
                    object_name="neat_signal",
                ),
                ObjectIsNeverUsed(
                    filename=filename,
                    line_number=29,
                    column_number=8,
                    object_type="signal",
                    object_name="another_signal",
                ),
            ]

            it.assertCountEqual(expected, diagnostics)
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

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesWithText(filename, content)

            _logger.debug("Records received:")
            for diagnostic in diagnostics:
                _logger.debug("- %s", diagnostic)

            expected = [
                LibraryShouldBeOmited(
                    library="work", filename=filename, column_number=9, line_number=1
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

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get updated messages")  # type: ignore
        def test():
            filename = Path(p.join(TEST_PROJECT, "another_library", "foo.vhd"))

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
                        line_number=29,
                        column_number=14,
                    ),
                    diagnostics,
                )
            finally:
                # Remove the comment we added
                code[28] = code[28][3:]
                writeListToFile(str(filename), code)

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages by path of a different source")  # type: ignore
        def test():
            filename = Path(p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd"))

            it.assertMsgQueueIsEmpty(it.project)

            it.assertCountEqual(
                it.project.getMessagesByPath(filename),
                [
                    ObjectIsNeverUsed(
                        filename=filename,
                        line_number=27,
                        column_number=12,
                        object_type="signal",
                        object_name="clk_enable_unused",
                    )
                ],
            )

            it.assertMsgQueueIsEmpty(it.project)

        @it.should(  # type: ignore
            "get messages from a source outside the project file"
        )
        def test():
            filename = Path(p.join(TEST_TEMP_PATH, "some_file.vhd"))
            writeListToFile(str(filename), ["library some_lib;"])

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

            it.assertMsgQueueIsEmpty(it.project)

        def basicRebuildTest(test_filename, rebuilds):
            calls = []
            ret_list = list(reversed(rebuilds))

            # Rebuild formats are:
            # - {unit_type: '', 'unit_name': }
            # - {library_name: '', 'unit_name': }
            # - {rebuild_path: ''}
            def _buildAndParse(self, path, library, forced=False):
                _logger.warning("%s, %s, %s", path, library, forced)
                calls.append(str(path))
                if ret_list:
                    return [], ret_list.pop()
                return [], []

            with mock.patch.object(MockBuilder, "_buildAndParse", _buildAndParse):
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

            it.assertCountEqual(
                ui_msgs,
                [("error", "Unable to build '{}' after 20 attempts".format(filename))],
            )


it.createTests(globals())

#  class TestIncludesVunit(TestCase):
#      def setUp(self):
#          # type: (...) -> Any
#          _logger.info("Setting up %s", self)
#          self.database = Database()

#      def tearDown(self):
#          # type: (...) -> Any
#          _logger.info("Tearing down %s", self)
#          del self.database

#      def test_has_vunit_context(self):
#          # type: (...) -> Any
#          expected = p.join(
#              os.environ["TOX_ENV_DIR"],
#              "lib",
#              "python%d.%d" % (sys.version_info.major, sys.version_info.minor),
#              "site-packages",
#              "vunit",
#              "vhdl",
#              "vunit_context.vhd",
#          )

#          logIterable("Design units:", self.database.design_units, _logger.fatal)

#          self.assertCountEqual(
#              self.database.getPathsDefining(Identifier("vunit_context")),
#              {Path(expected)},
#          )
#          #  /home/souto/dev/hdlcc/.tox/py37-linux-ff-dbg
#          #  /home/souto/dev/hdlcc/.tox/py37-linux-ff-dbg/
#          #  _logger.fatal(
#          #      "context: %s", set(self.database.getPathsDefining(Identifier("vunit_context")))
#          #  )
#          #  self.fail("stop")
