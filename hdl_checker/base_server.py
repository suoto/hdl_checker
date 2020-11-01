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
"HDL Checker project builder class"

import abc
import json
import logging
import os
import os.path as p
import tempfile
import traceback
from multiprocessing.pool import ThreadPool
from pprint import pformat
from threading import RLock, Timer
from typing import Any, AnyStr, Dict, Iterable, NamedTuple, Optional, Set, Tuple, Union

from hdl_checker import CACHE_NAME, DEFAULT_LIBRARY, WORK_PATH, __version__
from hdl_checker.builder_utils import (
    getBuilderByName,
    getVunitSources,
    getPreferredBuilder,
)
from hdl_checker.builders.fallback import Fallback
from hdl_checker.database import Database
from hdl_checker.diagnostics import (
    CheckerDiagnostic,
    DiagType,
    PathNotInProjectFile,
    UnresolvedDependency,
)
from hdl_checker.parsers.config_parser import ConfigParser
from hdl_checker.parsers.elements.dependency_spec import (
    IncludedPath,
    RequiredDesignUnit,
)
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path, TemporaryPath
from hdl_checker.serialization import StateEncoder, jsonObjectHook
from hdl_checker.static_check import getStaticMessages
from hdl_checker.types import (
    BuildFlagScope,
    ConfigFileOrigin,
    RebuildInfo,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)
from hdl_checker.utils import removeDirIfExists, removeIfExists, toBytes

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache  # type: ignore

_logger = logging.getLogger(__name__)

_HOW_LONG_IS_TOO_LONG = 30

_SETTING_UP_A_PROJECT_URL = (
    "https://github.com/suoto/hdl_checker/wiki/Setting-up-a-project"
)

_HOW_LONG_IS_TOO_LONG_MSG = (
    "Configuring the project seems to be taking too long. Consider using a "
    "smaller workspace or a configuration file. More info: "
    "[{0}]({0})".format(_SETTING_UP_A_PROJECT_URL)
)

WatchedFile = NamedTuple(
    "WatchedFile", (("path", Path), ("last_read", float), ("origin", ConfigFileOrigin))
)


class BaseServer(object):  # pylint: disable=useless-object-inheritance
    """
    HDL Checker project builder class
    """

    _USE_THREADS = True
    _MAX_REBUILD_ATTEMPTS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, root_dir):  # type: (Path) -> None
        # Root dir is the absolute path to use when any path passed on is
        # relative
        self.root_dir = root_dir
        # Work dir is the the directory that HDL Checker uses as a scratch
        # pad, everything within it may be deleted or changed
        self.work_dir = Path(p.join(str(self.root_dir), WORK_PATH))

        self._lock = RLock()
        self.config_file = None  # type: Optional[WatchedFile]

        self._database = Database()
        self._builder = Fallback(self.work_dir, self._database)

        self._setupIfNeeded()
        self._recoverCacheIfPossible()

        # Use this to know which methods should be cache
        self._cached_methods = {
            getattr(self, x)
            for x in dir(self)
            if hasattr(getattr(self, x), "cache_clear")
        }

    @property
    def builder(self):
        """
        Parses the config file if it has been set and returns the builder in
        use
        """
        self._updateConfigIfNeeded()
        return self._builder

    @property
    def database(self):
        """
        Parses the config file if it has been set and returns the builder in
        use
        """
        self._updateConfigIfNeeded()
        return self._database

    def __hash__(self):
        # Just to allow lru_cache to work
        return hash(0)

    def _clearLruCaches(self):
        "Clear caches from lru_caches"
        with self._lock:
            for meth in self._cached_methods:
                meth.cache_clear()

    def setConfig(self, filename, origin):
        # type: (Union[Path, str], ConfigFileOrigin) -> None
        """
        Sets the configuration file. Calling this method will only trigger a
        configuration update if the given file name is different what was
        configured previously (that includes no value previously set)
        """
        path = Path(filename, self.root_dir)
        mtime = path.mtime

        # If the config file has been set previously, avoid refreshing if
        # possible
        if self.config_file is None or self.config_file.path != path:
            _logger.debug("Replacing %s with %s", self.config_file, path)
            mtime = 0.0
        else:
            return

        self.config_file = WatchedFile(path, mtime, origin)
        _logger.debug("Set config to %s", self.config_file)
        self._updateConfigIfNeeded()

    def _updateConfigIfNeeded(self):
        # type: (...) -> Any
        """
        Checks if self.config_file has changed; if it has, cleans up working
        dir and re reads it. The config file will be read as JSON first and, if
        that fails, ConfigParser is attempted
        """
        with self._lock:
            self._setupIfNeeded()

            # No config file set
            if self.config_file is None:
                return

            file_mtime = self.config_file.path.mtime
            # Check if values we have are up to date
            if self.config_file.last_read >= file_mtime:
                return

            # Don't let the user hanging if adding sources is taking too long
            # when there's no config file. Also need to notify when adding is
            # done.
            timer = Timer(
                _HOW_LONG_IS_TOO_LONG,
                self._handleUiInfo,
                args=(_HOW_LONG_IS_TOO_LONG_MSG,),
            )

            if self.config_file.origin is ConfigFileOrigin.generated:
                timer.start()

            try:
                config = json.load(open(str(self.config_file.path)))
            except json.decoder.JSONDecodeError:
                config = ConfigParser(self.config_file.path).parse()

            self.configure(config)

            self.config_file = WatchedFile(
                self.config_file.path, file_mtime, self.config_file.origin
            )
            _logger.debug("Updated config file to %s", self.config_file)
            timer.cancel()

    def configure(self, config):
        # type: (Dict[Any, Any]) -> None
        "Updates configuration from a dictionary"

        _logger.debug("Updating with base config:\n%s", pformat(config))

        builder_name = config.pop("builder", None)
        if builder_name is not None:
            builder_cls = getBuilderByName(builder_name)
        else:
            builder_cls = getPreferredBuilder()

        _logger.debug("Builder class: %s", builder_cls)

        self._builder = builder_cls(self.work_dir, self._database)

        sources_added = self._database.configure(config, str(self.root_dir))
        # Add VUnit
        if not isinstance(self._builder, Fallback):
            for path, library, flags in getVunitSources(self._builder):
                self._database.addSource(path, library, flags, flags)

        # Add the flags from the root config file last, it should overwrite
        # values set by the included files
        if config:
            _logger.warning(
                "Some configuration elements weren't used:\n%s", pformat(config)
            )

        if sources_added:
            self._handleUiInfo("Added {} sources".format(sources_added))
        else:
            self._handleUiInfo("No sources were added")

    def _getCacheFilename(self):
        # type: () -> Path
        """
        The cache file name will always be inside the path returned by self._getWorkingPath
        and defaults to cache.json
        """
        return Path(CACHE_NAME, self.work_dir)

    def _saveCache(self):
        # type: (...) -> Any
        """
        Dumps project object to a file to recover its state later
        """
        cache_fname = self._getCacheFilename()

        state = {
            "builder": self.builder,
            "config_file": self.config_file,
            "database": self.database,
            "__version__": __version__,
        }

        _logger.debug("Saving state to '%s'", cache_fname)
        if not p.exists(p.dirname(cache_fname.name)):
            os.makedirs(p.dirname(cache_fname.name))
        json.dump(state, open(cache_fname.name, "w"), indent=True, cls=StateEncoder)

    def _setState(self, state):
        # type: (...) -> Any
        """
        Serializer load implementation
        """
        self._database = state.pop("database")
        self._builder = state.pop("builder", Fallback)
        self._builder._database = self._database
        config_file = state.pop("config_file", None)
        if config_file is None:
            self.config_file = None
        else:
            self.config_file = WatchedFile._make(config_file)

    def _recoverCacheIfPossible(self):
        # type: (...) -> Any
        """
        Tries to recover cached info for the given config_file. If
        something goes wrong, assume the cache is invalid and return
        nothing. Otherwise, return the cached object
        """
        cache_fname = self._getCacheFilename()

        try:
            cache = json.load(open(cache_fname.name, "r"), object_hook=jsonObjectHook)
        except IOError:
            _logger.debug("Couldn't read cache file %s, skipping recovery", cache_fname)
            return
        except ValueError as exception:
            self._handleUiWarning(
                "Unable to recover cache from '{}': {}".format(
                    cache_fname, str(exception)
                )
            )

            _logger.warning(
                "Unable to recover cache from '%s': %s",
                cache_fname,
                traceback.format_exc(),
            )
            return

        # Check the cache info and the current version match
        cached_version = cache.get("__version__", None)
        if __version__ != cached_version:
            _logger.info(
                "Cache versions mismatch: %s and %s", __version__, cached_version
            )
            return

        _logger.debug("Recovered cache from '%s'", cache_fname)
        self._setState(cache)
        self._builder.setup()

    def _setupIfNeeded(self):
        # type: (...) -> Any
        """
        Sanity checks to make sure the environment is sane
        """
        if p.exists(str(self.work_dir)) and p.exists(self._builder.work_folder):
            return

        _logger.info("Not all directories exist, forcing setup")
        self.clean()

        os.makedirs(str(self.work_dir))

        del self._builder
        del self._database

        database = Database()
        self._database = database
        self._builder = Fallback(self.work_dir, database)

        self._builder.setup()

        if self.config_file is None:
            return

        # Force config file out of to date to trigger reparsing
        self.config_file = WatchedFile(
            self.config_file.path, 0, self.config_file.origin
        )

    def clean(self):
        # type: (...) -> Any
        """
        Clean up generated files
        """
        _logger.debug("Cleaning up project")
        removeDirIfExists(str(self.work_dir))

    @abc.abstractmethod
    def _handleUiInfo(self, message):  # type: (AnyStr) -> None
        """
        Method that should be overriden to handle info messages from
        HDL Checker to the user
        """

    @abc.abstractmethod
    def _handleUiWarning(self, message):  # type: (AnyStr) -> None
        """
        Method that should be overriden to handle warning messages
        from HDL Checker to the user
        """

    @abc.abstractmethod
    def _handleUiError(self, message):  # type: (AnyStr) -> None
        """
        Method that should be overriden to handle errors messages
        from HDL Checker to the user
        """

    def _getBuilderMessages(self, path):
        # type: (Path) -> Iterable[CheckerDiagnostic]
        """
        Builds the given path taking care of recursively building its
        dependencies first
        """
        _logger.debug("Building '%s'", str(path))

        path = Path(path, self.root_dir)

        for dep_library, dep_path in self.database.getBuildSequence(
            path, self.builder.builtin_libraries
        ):
            for record in self._buildAndHandleRebuilds(
                dep_path, dep_library, scope=BuildFlagScope.dependencies
            ):
                if record.severity in (DiagType.ERROR, DiagType.STYLE_ERROR):
                    yield record

        _logger.debug("Built dependencies, now actually building '%s'", str(path))
        library = self.database.getLibrary(path)
        for record in self._buildAndHandleRebuilds(
            path,
            library if library is not None else DEFAULT_LIBRARY,
            scope=BuildFlagScope.single,
            forced=True,
        ):
            yield record

    def _buildAndHandleRebuilds(self, path, library, scope, forced=False):
        # type: (Path, Identifier, BuildFlagScope, bool) -> Iterable[CheckerDiagnostic]
        """
        Builds the given path and handle any files that might require
        rebuilding until there is nothing to rebuild. The number of iteractions
        is fixed in 10.
        """
        # Limit the amount of calls to rebuild the same file to avoid
        # hanging the server
        for _ in range(self._MAX_REBUILD_ATTEMPTS):
            records, rebuilds = self.builder.build(
                path=path, library=library, scope=scope, forced=forced
            )

            if rebuilds:
                _logger.debug(
                    "Building '%s' triggers rebuilding: %s",
                    path,
                    ", ".join([str(x) for x in rebuilds]),
                )
                self._handleRebuilds(rebuilds)
            else:
                _logger.debug("Had no rebuilds for %s", path)
                return records

        self._handleUiError(
            "Unable to build '%s' after %d attempts"
            % (path, self._MAX_REBUILD_ATTEMPTS)
        )

        return {}

    def _handleRebuilds(self, rebuilds):
        # type: (Iterable[RebuildInfo]) -> None
        """
        Resolves hints found in the rebuild list into path objects
        and rebuild them
        """
        for rebuild in rebuilds:
            _logger.debug("Rebuild hint: '%s'", rebuild)
            if isinstance(rebuild, RebuildUnit):
                for path in self.database.getPathsDefining(name=rebuild.name):
                    list(self._getBuilderMessages(path))

            elif isinstance(rebuild, RebuildLibraryUnit):
                for path in self.database.getPathsDefining(
                    name=rebuild.name, library=rebuild.library
                ):
                    list(self._getBuilderMessages(path))
            elif isinstance(rebuild, RebuildPath):
                list(self._getBuilderMessages(rebuild.path))

            else:  # pragma: no cover
                _logger.warning("Did nothing with %s", rebuild)

    def getMessagesByPath(self, path):
        # type: (Path) -> Iterable[CheckerDiagnostic]
        """
        Returns the messages for the given path, including messages
        from the configured builder (if available) and static checks
        """
        self._clearLruCaches()

        path = Path(path, self.root_dir)

        builder_diags = set()  # type: Set[CheckerDiagnostic]

        if self._USE_THREADS:
            pool = ThreadPool()

            static_check = pool.apply_async(
                getStaticMessages, args=(tuple(open(path.name).read().split("\n")),)
            )

            builder_check = pool.apply_async(self._getBuilderMessages, args=[path])
            builder_diags |= set(builder_check.get())

            pool.close()
            pool.join()

            static_diags = set(static_check.get())

        else:  # pragma: no cover
            builder_diags |= set(self._getBuilderMessages(path))
            static_diags = set(
                getStaticMessages(tuple(open(path.name).read().split("\n")))
            )

        # Static messages don't take the path, only the text, so we need to set
        # that. Also, any diagnostic without filename will be made to point to
        # the current path
        for diag in static_diags:
            if diag.filename is None:
                diag = diag.copy(filename=path)
            builder_diags.add(diag)

        self._saveCache()

        # Add diagnostics the database might have
        diags = builder_diags | set(self.database.getDiagnosticsForPath(path))

        # Report dependencies that could not be resolved to paths
        for dependency in self.database.getDependenciesByPath(path):
            if dependency.library in self.builder.builtin_libraries:
                continue
            # Required design units will be translated directly into a path
            resolved = (
                isinstance(dependency, RequiredDesignUnit)
                and self.resolveDependencyToPath(dependency)
            ) or (
                isinstance(dependency, IncludedPath)
                and self.database.resolveIncludedPath(dependency)
            )
            if not resolved:
                for location in dependency.locations:
                    diags.add(UnresolvedDependency(dependency, location))

        # If we're working off of a project file, no need to filter out diags
        # about path not being found
        if self.config_file is not None:
            return diags

        return {diag for diag in diags if not isinstance(diag, PathNotInProjectFile)}

    def getMessagesWithText(self, path, content):
        # type: (Path, AnyStr) -> Iterable[CheckerDiagnostic]
        """
        Dumps content to a temprary file and replaces the temporary file name
        for path on the diagnostics received
        """
        with self._lock:
            _logger.info("Getting messages for '%s' with content", path)

            ext = path.name.split(".")[-1]
            temporary_file = tempfile.NamedTemporaryFile(suffix="." + ext, delete=False)

            temp_path = TemporaryPath(temporary_file.name)

            temporary_file.file.write(toBytes(content))  # type: ignore
            temporary_file.close()

            # If the reference path was added to the database, add the
            # temporary file with the same attributes
            if path in self.database.paths:
                library = self.database.getLibrary(path)
                self.database.addSource(
                    temp_path,
                    getattr(library, "display_name", None),
                    self.database.getFlags(path, BuildFlagScope.single),
                    self.database.getFlags(path, BuildFlagScope.dependencies),
                )

            diags = set()  # type: Set[CheckerDiagnostic]

            # Some messages may not include the filename field when checking a
            # file by content. In this case, we'll assume the empty filenames
            # refer to the same filename we got in the first place
            for diag in self.getMessagesByPath(temp_path):
                if diag.filename in (temp_path, None):
                    diag = diag.copy(
                        text=diag.text.replace(temporary_file.name, path.name),
                        filename=path,
                    )

                diags.add(diag)

            diags |= set(self.database.getDiagnosticsForPath(temporary_file))

            self.database.removeSource(temp_path)
            removeIfExists(temporary_file.name)

            if self.config_file and path not in self.database.paths:
                diags.add(PathNotInProjectFile(path))

        return diags

    @lru_cache()
    def resolveDependencyToPath(self, dependency):
        # type: (RequiredDesignUnit) -> Optional[Tuple[Path, Identifier]]
        """
        Retrieves the build sequence for the dependency's owner and extracts
        the path that implements a design unit whose names match that of the
        dependency.
        """

        # Check if the dependency is defined in the same same file
        if dependency.name in (
            x.name for x in self.database.getDesignUnitsByPath(dependency.owner)
        ):
            return dependency.owner, self.database.getLibrary(dependency.owner)

        # Search through the build sequence
        for library, path in self.database.getBuildSequence(
            dependency.owner, self.builder.builtin_libraries
        ):
            if dependency.name in (
                x.name for x in self.database.getDesignUnitsByPath(path)
            ):
                return path, library

        return None
