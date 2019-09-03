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
"HDL Code Checker project builder class"

import abc
import json
import logging
import os
import os.path as p
import traceback
from multiprocessing.pool import ThreadPool
from threading import RLock
from typing import Any, AnyStr, Dict, Generator, List, Optional, Set, Tuple

from hdlcc import builders, exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import Fallback
from hdlcc.database import Database
from hdlcc.diagnostics import (
    CheckerDiagnostic,
    DependencyNotUnique,
    DiagType,
    PathNotInProjectFile,
)
from hdlcc.parsers import (
    ConfigParser,
    DependencySpec,
    VerilogParser,
    VhdlParser,
    tSourceFile,
)
from hdlcc.serialization import StateEncoder, jsonObjectHook
from hdlcc.static_check import getStaticMessages
from hdlcc.utils import (
    getCachePath,
    getFileType,
    removeDirIfExists,
    removeDuplicates,
    removeIfExists,
    samefile,
)

CACHE_NAME = "cache.json"

_logger = logging.getLogger("build messages")


class HdlCodeCheckerBase(object):  # pylint: disable=useless-object-inheritance
    """
    HDL Code Checker project builder class
    """

    _USE_THREADS = True
    _MAX_REBUILD_ATTEMPTS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self):  # type: () -> None
        self._start_dir = p.abspath(os.curdir)
        self._logger = logging.getLogger(__name__)
        self._build_sequence_cache = {}  # type: Dict[str, Any]
        self._outstanding_diags = set()  # type: Set[CheckerDiagnostic]
        self._setup_lock = RLock()

        self.config_file = None  # type: Optional[t.Path]

        self.database = Database()
        self.builder = Fallback(self._getWorkingPath())

        self._recoverCacheIfPossible()
        self._setupEnvIfNeeded()
        self._saveCache()

    def setConfigFile(self, path):  # type: (t.Path) -> None
        """
        Setting the configuration file will trigger parsing if the path is
        different than the one already set.
        """
        if self.config_file is not None and samefile(self.config_file, path):
            self._logger.info("Seeting the same file, won't do anything")
            return

        self.config_file = path
        self.database.accept(ConfigParser(path))

    def _getWorkingPath(self):  # type: () -> t.Path
        """
        The working path will depend on the configuration file but it's
        guaranteed not to be None
        """
        cache = p.abspath(self.config_file or ".")
        return t.Path(p.join(getCachePath(), cache.replace(p.sep, "_")))

    def _getCacheFilename(self):
        """
        The cache file name will always be inside the path returned by self._getWorkingPath
        and defaults to cache.json
        """
        cache_dir = self._getWorkingPath()
        return p.join(cache_dir, CACHE_NAME)

    def _saveCache(self):
        """
        Dumps project object to a file to recover its state later
        """
        cache_fname = self._getCacheFilename()

        state = {
            "_logger": {"name": self._logger.name, "level": self._logger.level},
            "builder": self.builder,
        }

        self._logger.debug("Saving state to '%s'", cache_fname)
        if not p.exists(p.dirname(cache_fname)):
            os.makedirs(p.dirname(cache_fname))
        json.dump(state, open(cache_fname, "w"), indent=True, cls=StateEncoder)

    def _recoverCacheIfPossible(self):
        """
        Tries to recover cached info for the given config_file. If
        something goes wrong, assume the cache is invalid and return
        nothing. Otherwise, return the cached object
        """
        cache_fname = self._getCacheFilename()

        try:
            cache = json.load(open(cache_fname, "r"), object_hook=jsonObjectHook)
            self._handleUiInfo("Recovered cache from '{}'".format(cache_fname))
        except IOError:
            self._logger.debug(
                "Couldn't read cache file %s, skipping recovery", cache_fname
            )
            return
        except ValueError as exception:
            self._handleUiWarning(
                "Unable to recover cache from '{}': {}".format(
                    cache_fname, str(exception)
                )
            )

            self._logger.warning(
                "Unable to recover cache from '%s': %s",
                cache_fname,
                traceback.format_exc(),
            )
            return

        self._setState(cache)
        self.builder.checkEnvironment()

    def isSetupRunning(self):
        locked = not self._setup_lock.acquire(False)
        if not locked:
            self._setup_lock.release()
        return locked

    def _setupEnvIfNeeded(self):
        """
        Updates or creates the environment, which includes checking
        if the configuration file should be parsed and creating the
        appropriate builder objects
        """
        try:
            builder_name = self.database.builder_name
        except AssertionError:
            return

        try:
            with self._setup_lock:
                # If still using Fallback builder, check if the config has a
                # different one
                if isinstance(self.builder, Fallback):
                    builder_name = self.database.builder_name
                    builder_class = builders.getBuilderByName(builder_name)
                    if builder_class is Fallback:
                        return

                    cache_dir = self._getWorkingPath()
                    try:
                        os.makedirs(cache_dir)
                    except OSError:
                        pass

                    self.builder = builder_class(cache_dir)

                    self._logger.info(
                        "Selected builder is '%s'", self.builder.builder_name
                    )
        except exceptions.SanityCheckError as exc:
            self._handleUiError("Failed to create builder '%s'" % exc.builder)
            self.builder = Fallback(self._getWorkingPath())

        assert self.builder is not None

    def clean(self):
        """
        Clean up generated files
        """
        self._logger.debug("Cleaning up project")
        removeIfExists(self._getCacheFilename())
        removeDirIfExists(self._getWorkingPath())

        del self.builder
        self.database = Database()
        self.builder = Fallback(self._getWorkingPath())

    def _setState(self, state):
        """
        Serializer load implementation
        """
        self._logger = logging.getLogger(state["_logger"]["name"])
        self._logger.setLevel(state["_logger"]["level"])
        del state["_logger"]

        self.database = state["database"]

        builder_name = self.database.builder_name
        self._logger.debug("Recovered builder is '%s'", builder_name)
        #  builder_class = hdlcc.builders.getBuilderByName(builder_name)
        #  self.builder = builder_class.recoverFromState(state['builder'])
        self.builder = state["builder"]

    @abc.abstractmethod
    def _handleUiInfo(self, message):  # type: (AnyStr) -> None
        """
        Method that should be overriden to handle info messages from
        HDL Code Checker to the user
        """

    @abc.abstractmethod
    def _handleUiWarning(self, message):  # type: (AnyStr) -> None
        """
        Method that should be overriden to handle warning messages
        from HDL Code Checker to the user
        """

    @abc.abstractmethod
    def _handleUiError(self, message):  # type: (AnyStr) -> None
        """
        Method that should be overriden to handle errors messages
        from HDL Code Checker to the user
        """

    #  def getSourceByPath(self, path):
    #      # type: (t.Path) -> Tuple[tSourceFile, List[CheckerDiagnostic]]
    #      """
    #      Get the source object, flags and any additional info to be displayed
    #      """
    #      try:
    #          return self.database.getSourceByPath(path), []
    #      except KeyError:
    #          pass

    #      remarks = [] # type: List[CheckerDiagnostic]

    #      # If the source file was not found on the configuration file, add this
    #      # as a remark.
    #      # Also, create a source parser object with some library so the user can
    #      # at least have some info on the source
    #      if not isinstance(self.builder, Fallback):
    #          remarks = [PathNotInProjectFile(p.abspath(path)), ]

    #      self._logger.info("Path %s not found in the project file",
    #                        p.abspath(path))

    #      if getFileType(path) == 'vhdl':
    #          source = VhdlParser(path, library='undefined') # type: tSourceFile
    #      else:
    #          source = VerilogParser(path, library='undefined')

    #      return source, remarks

    def _resolveRelativeNames(self, source):
        # type: (tSourceFile) -> Generator[DependencySpec, None, None]
        """
        Translate raw dependency list parsed from a given source to the
        project name space
        """
        for dependency in source.getDependencies():
            if dependency.library in self.builder.getBuiltinLibraries():
                continue
            if dependency.name == "all":
                continue
            if dependency.library == source.library and dependency.name in [
                x["name"] for x in source.getDesignUnits()
            ]:
                continue
            yield dependency

    @staticmethod
    def _sortBuildMessages(diagnostics):
        """
        Sorts a given set of build records
        """
        return sorted(
            diagnostics,
            key=lambda x: (x.severity, x.line_number or 0, x.error_code or ""),
        )

    def updateBuildSequenceCache(self, source):
        # type: (tSourceFile) -> List[Tuple[tSourceFile, t.LibraryName]]
        """
        Wrapper to _resolveBuildSequence passing the initial build sequence
        list empty and caching the result
        """
        # Despite we renew the cache when on buffer enter, we must also
        # check if any file has been changed by some background process
        # that the editor is unaware of (Vivado maybe?) To cope with
        # this, we'll check if the newest modification time of the build
        # sequence hasn't changed since we cached the build sequence
        key = str(source.filename)
        if key not in self._build_sequence_cache:
            build_sequence = self.getBuildSequence(source)
            if build_sequence:
                timestamp = max([x[0].getmtime() for x in build_sequence])
            else:
                timestamp = 0
            self._build_sequence_cache[key] = {
                "sequence": build_sequence,
                "timestamp": timestamp,
            }
        else:
            cached_sequence = self._build_sequence_cache[key]["sequence"]
            cached_timestamp = self._build_sequence_cache[key]["timestamp"]
            if cached_sequence:
                current_timestamp = max(
                    max({x.getmtime() for x in cached_sequence if x}),
                    source.getmtime() or 0,
                )
            else:
                current_timestamp = 0

            if current_timestamp > cached_timestamp:
                self._logger.debug("Timestamp change, rescanning build " "sequence")
                self._build_sequence_cache[key] = {
                    "sequence": self.getBuildSequence(source),
                    "timestamp": current_timestamp,
                }

        return self._build_sequence_cache[key]["sequence"]

    def _reportDependencyNotUnique(self, non_resolved_dependency, actual, choices):
        """
        Reports a dependency failed to be resolved due to multiple files
        defining the required design unit
        """
        locations = non_resolved_dependency.locations or (
            non_resolved_dependency.filename,
            1,
            None,
        )

        for filename, line_number, column_number in locations:
            self._outstanding_diags.add(
                DependencyNotUnique(
                    filename=filename,
                    line_number=line_number,
                    column_number=column_number,
                    design_unit="{}.{}".format(
                        non_resolved_dependency.library, non_resolved_dependency.name
                    ),
                    actual=actual.filename,
                    choices=list(choices),
                )
            )

    def getBuildSequence(self, source):
        # type: (tSourceFile) -> List[Tuple[tSourceFile, t.LibraryName]]
        build_sequence = []  # type: List[Tuple[tSourceFile, t.LibraryName]]
        self._resolveBuildSequence(source, build_sequence)
        return build_sequence

    def _resolveBuildSequence(self, source, build_sequence, reference=None):
        # type: (tSourceFile, List[Tuple[tSourceFile, t.LibraryName]], Optional[tSourceFile]) -> None
        """
        Recursively finds out the dependencies of the given source file
        """
        self._logger.debug("Checking build sequence for %s", source)
        for dependency in self._resolveRelativeNames(source):
            # Get a list of source files that contains this design unit. At
            # this point, all the info we have pretty much depends on parsed
            # text. Since Verilog is case sensitive and VHDL is not, we need to
            # make sure we've got it right when mapping dependencies on mixed
            # language projects
            dependencies_list = self.database.discoverSourceDependencies(
                unit=dependency.name,
                library=dependency.library,
                case_sensitive=source.filetype != "vhdl",
            )

            if not dependencies_list:
                continue
            selected_dependency = dependencies_list.pop()

            # If we found more than a single file, then multiple files have the
            # same entity or package name and we failed to identify the real
            # file
            if dependencies_list:
                _logger.warning("Dependency %s (%s)", dependency, type(dependency))
                self._reportDependencyNotUnique(
                    non_resolved_dependency=dependency,
                    actual=selected_dependency[0],
                    choices=[x[0] for x in dependencies_list],
                )

            # Check if we found out that a dependency is the same we
            # found in the previous call to break the circular loop
            if selected_dependency == reference:
                build_sequence = removeDuplicates(build_sequence)
                return

            if selected_dependency not in build_sequence:
                self._resolveBuildSequence(
                    selected_dependency[0],
                    reference=source,
                    build_sequence=build_sequence,
                )

            if selected_dependency not in build_sequence:
                build_sequence.append(selected_dependency)

        build_sequence = removeDuplicates(build_sequence)

    def _getBuilderMessages(self, source):
        # type: (tSourceFile) -> List[Dict[str, str]]
        """
        Builds the given source taking care of recursively building its
        dependencies first
        """
        try:
            flags = self.database.getBuildFlags(source.filename)
        except KeyError:
            flags = []

        self._logger.info("Building '%s'", str(source.filename))

        build_sequence = self.updateBuildSequenceCache(source)

        self._logger.debug("Compilation build_sequence is:")
        for src, library in build_sequence:
            self._logger.debug("library=%s, source: %s", library, src)

        records = set()
        for src, library in build_sequence:
            _flags = self.database.getBuildFlags(src.filename)

            old = str(src.library)
            src.library = library
            dep_records = self._buildAndHandleRebuilds(src, forced=False, flags=_flags)
            src.library = old

            for record in dep_records:
                if record.filename is None:
                    continue
                if record.severity in (DiagType.ERROR,):
                    records.add(record)

        records.update(self._buildAndHandleRebuilds(source, forced=True, flags=flags))

        return self._sortBuildMessages(records)

    def _buildAndHandleRebuilds(self, source, *args, **kwargs):
        """
        Builds the given source and handle any files that might require
        rebuilding until there is nothing to rebuild. The number of iteractions
        is fixed in 10.
        """
        # Limit the amount of calls to rebuild the same file to avoid
        # hanging the server
        for _ in range(self._MAX_REBUILD_ATTEMPTS):
            records, rebuilds = self.builder.build(source, *args, **kwargs)
            if rebuilds:
                self._handleRebuilds(rebuilds, source)
            else:
                return records

        self._handleUiError(
            "Unable to build '%s' after %d attempts"
            % (source.filename, self._MAX_REBUILD_ATTEMPTS)
        )

        return {}

    def _handleRebuilds(self, rebuilds, source):
        """
        Resolves hints found in the rebuild list into source objects
        and rebuild them
        """
        self._logger.info(
            "Building '%s' triggers rebuilding: %s",
            source,
            ", ".join([str(x) for x in rebuilds]),
        )
        for rebuild in rebuilds:
            self._logger.debug("Rebuild hint: '%s'", rebuild)
            if "rebuild_path" in rebuild:
                rebuild_sources = [self.getSourceByPath(rebuild["rebuild_path"])[0]]
            else:
                unit_name = rebuild.get("unit_name", None)
                library_name = rebuild.get("library_name", None)
                unit_type = rebuild.get("unit_type", None)

                if library_name is not None:
                    rebuild_sources = self.database.findSourcesByDesignUnit(
                        unit_name, library_name
                    )
                elif unit_type is not None:
                    library = source.getMatchingLibrary(unit_type, unit_name)
                    rebuild_sources = self.database.findSourcesByDesignUnit(
                        unit_name, library
                    )
                else:  # pragma: no cover
                    assert False, "Don't know how to handle %s" % rebuild

            for rebuild_source in rebuild_sources:
                self._getBuilderMessages(rebuild_source)

    def _isBuilderCallable(self):
        """
        Checks if all preconditions for calling the builder have been
        met
        """
        if self.config_file is None:
            return False
        return True

    def getMessagesByPath(self, path):
        """
        Returns the messages for the given path, including messages
        from the configured builder (if available) and static checks
        """
        self._setupEnvIfNeeded()

        # These paths define the dependencies that the original path has. In
        # the ideal case, each dependency is defined once and the config file
        # specifies the correct library, in which case we don't add any extra
        # warning.
        #
        # If a dependency is defined multiple times, issue a warning indicating
        # which one is going to actually be used and which are the other
        # options, just like what has been already implemented.
        #
        # If the library is not set for the a given path, try to guess it by
        # (1) given every design unit defined in this file, (2) search for
        # every file that also depends on it and (3) identify which library is
        # used. If all of them converge on the same library name, just use
        # that. If there's no agreement, use the library that satisfies the
        # path in question but warn the user that something is not right
        paths = self.database.discoverSourceDependencies(path)

        self._outstanding_diags = set()

        records = []

        if self._USE_THREADS:
            pool = ThreadPool()

            static_check = pool.apply_async(
                getStaticMessages, args=(source.getRawSourceContent().split("\n"),)
            )

            if self._isBuilderCallable():
                builder_check = pool.apply_async(
                    self._getBuilderMessages, args=[source]
                )
                records += builder_check.get()

            pool.close()
            pool.join()

            # Static messages don't take the path, only the text, so we need to
            # set add that to the diagnostic
            for record in static_check.get():
                record.filename = source.filename
                records += [record]

        else:  # pragma: no cover
            for record in getStaticMessages(source.getRawSourceContent().split("\n")):
                record.filename = source.filename
                records += [record]

            if self._isBuilderCallable():
                records += self._getBuilderMessages(source)

        self._saveCache()
        return records + list(self._outstanding_diags)

    def getMessagesWithText(self, path, content):
        """
        Gets messages from a given path with a different content, for
        the cases when the buffer content has been modified
        """
        self._logger.debug("Getting messages for '%s' with content", path)

        self._setupEnvIfNeeded()

        source, remarks = self.getSourceByPath(path)
        with source.havingBufferContent(content):
            messages = self.getMessagesBySource(source)

        # Some messages may not include the filename field when checking a
        # file by content. In this case, we'll assume the empty filenames
        # refer to the same filename we got in the first place
        for message in messages:
            message.filename = p.abspath(path)

        return messages + remarks

    def getSources(self):
        """
        Returns a list of VhdlSourceFile objects parsed
        """
        self._setupEnvIfNeeded()
        return self.getSources()

    def onBufferVisit(self, path):
        """
        Runs tasks whenever a buffer is being visited. Currently this
        means caching the build sequence before the file is actually
        checked, so the overall wait time is reduced
        """
        self._setupEnvIfNeeded()
        source, _ = self.getSourceByPath(path)
        self.updateBuildSequenceCache(source)
