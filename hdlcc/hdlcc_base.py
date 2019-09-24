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
import tempfile
import traceback
from multiprocessing.pool import ThreadPool
from typing import Any, AnyStr, Dict, Iterable, Set

import six

from hdlcc.builder_utils import getBuilderByName, getVunitSources, getWorkingBuilders
from hdlcc.builders.fallback import Fallback
from hdlcc.database import Database
from hdlcc.diagnostics import CheckerDiagnostic, DiagType
from hdlcc.exceptions import UnknownParameterError
from hdlcc.parsers.config_parser import ConfigParser
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.path import Path
from hdlcc.serialization import StateEncoder, jsonObjectHook
from hdlcc.static_check import getStaticMessages
from hdlcc.types import (
    BuildFlagScope,
    RebuildInfo,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)
from hdlcc.utils import removeDirIfExists, removeIfExists, toBytes

CACHE_NAME = "cache.json"

_logger = logging.getLogger(__name__)

if six.PY2:
    JSONDecodeError = ValueError
    FileNotFoundError = IOError  # pylint: disable=redefined-builtin
else:
    JSONDecodeError = json.decoder.JSONDecodeError

WORK_PATH = ".hdlcc"


class HdlCodeCheckerBase(object):  # pylint: disable=useless-object-inheritance
    """
    HDL Code Checker project builder class
    """

    _USE_THREADS = True
    _MAX_REBUILD_ATTEMPTS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, root_dir):  # type: (Path) -> None
        self.root_dir = root_dir
        self.work_dir = Path(p.join(str(self.root_dir), WORK_PATH))

        self.database = Database()
        self.builder = Fallback(self.work_dir, self.database)

        if not p.exists(str(self.work_dir)):
            os.makedirs(str(self.work_dir))

        self._recoverCacheIfPossible()
        self._saveCache()

    def readConfig(self, filename):
        # type: (str) -> None
        """
        Updates the database from a configuration file. Extracting form JSON
        has priority, then ConfigParser is attempted.
        """
        try:
            config = json.load(open(filename))
        except FileNotFoundError as exc:
            self._handleUiError(
                "Failed to parse '{}': No such file".format(exc.filename)
            )
            raise
        except JSONDecodeError:
            try:
                config = ConfigParser(Path(filename)).parse()
            except UnknownParameterError as exc:
                self._handleUiError(
                    "Failed to parse '{}': {}".format(filename, str(exc))
                )
                raise

        self.configure(config)

    def configure(self, config):
        # type: (Dict[Any, Any]) -> None
        "Updates configuration from a dictionary"

        from pprint import pformat

        _logger.info("Updating with base config:\n%s", pformat(config))

        builder_name = config.pop("builder_name", None)
        if builder_name is not None:
            builder_cls = getBuilderByName(builder_name)
        else:
            try:
                builder_cls = list(getWorkingBuilders()).pop()
            except IndexError:
                builder_cls = Fallback

        self.builder = builder_cls(self.work_dir, self.database)

        self.database.configure(config, str(self.root_dir))
        # Add VUnit
        if not isinstance(self.builder, Fallback):
            for path, library, flags in getVunitSources(self.builder):
                self.database.addSource(path, library, flags, flags)

        # Add the flags from the root config file last, it should overwrite
        # values set by the included files
        #  self.database.addSources(config.pop("sources", ()), config_root_path)
        #  if config
        if config:
            _logger.warning(
                "Some configuration elements weren't used:\n%s", pformat(config)
            )
            assert False

    def _getCacheFilename(self):
        # type: () -> Path
        """
        The cache file name will always be inside the path returned by self._getWorkingPath
        and defaults to cache.json
        """
        return Path(p.join(self.work_dir.name, CACHE_NAME))

    def _saveCache(self):
        # type: (...) -> Any
        """
        Dumps project object to a file to recover its state later
        """
        cache_fname = self._getCacheFilename()

        state = {"builder": self.builder, "database": self.database}

        _logger.debug("Saving state to '%s'", cache_fname)
        if not p.exists(p.dirname(cache_fname.name)):
            os.makedirs(p.dirname(cache_fname.name))
        json.dump(state, open(cache_fname.name, "w"), indent=True, cls=StateEncoder)

    def _setState(self, state):
        # type: (...) -> Any
        """
        Serializer load implementation
        """
        self.database = state.pop("database")
        self.builder = state.pop("builder", Fallback)

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
            self._handleUiInfo("Recovered cache from '{}'".format(cache_fname))
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

        self._setState(cache)
        self.builder.setup()

    def _cleanIfNeeded(self):
        # type: (...) -> Any
        """
        Sanity checks to make sure the environment is sane
        """
        if not p.exists(self.builder.work_folder):
            _logger.info("Builder work folder not found, cleaning up")
            self.clean()
            self.builder.setup()

    def clean(self):
        # type: (...) -> Any
        """
        Clean up generated files
        """
        _logger.debug("Cleaning up project")
        removeDirIfExists(str(self.work_dir))

        del self.builder
        del self.database

        self.database = Database()
        self.builder = Fallback(self.work_dir, self.database)

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

    def _getBuilderMessages(self, path):
        # type: (Path) -> Iterable[CheckerDiagnostic]
        """
        Builds the given path taking care of recursively building its
        dependencies first
        """
        _logger.debug("Building '%s'", str(path))

        path = Path(str(path), str(self.root_dir))

        for dep_library, dep_path in self.database.getBuildSequence(
            path, self.builder.builtin_libraries
        ):
            for record in self._buildAndHandleRebuilds(
                dep_path, dep_library, scope=BuildFlagScope.dependencies
            ):
                if record.severity in (DiagType.ERROR, DiagType.STYLE_ERROR):
                    yield record

        _logger.info("Built dependencies, now actually building '%s'", str(path))
        library = self.database.getLibrary(path)
        for record in self._buildAndHandleRebuilds(
            path,
            library if library is not None else Identifier("work"),
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
        _logger.info("Building %s / %s", path, library)
        self._cleanIfNeeded()
        # Limit the amount of calls to rebuild the same file to avoid
        # hanging the server
        for _ in range(self._MAX_REBUILD_ATTEMPTS):
            records, rebuilds = self.builder.build(
                path=path, library=library, scope=scope, forced=forced
            )

            if rebuilds:
                _logger.info(
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
        path = Path(str(path), str(self.root_dir))

        builder_diags = set()  # type: Set[CheckerDiagnostic]

        if self._USE_THREADS:
            pool = ThreadPool()

            static_check = pool.apply_async(
                getStaticMessages, args=(tuple(open(path.name).read().split("\n")),)
            )

            builder_check = pool.apply_async(self._getBuilderMessages, args=[path])
            builder_diags |= {x for x in builder_check.get()}

            pool.close()
            pool.join()

            static_diags = {x for x in static_check.get()}

        else:  # pragma: no cover
            builder_diags |= set(self._getBuilderMessages(path))
            static_diags = set(
                getStaticMessages(tuple(open(path.name).read().split("\n")))
            )

        # Static messages don't take the path, only the text, so we need to
        # set add that to the diagnostic
        for diag in static_diags:
            diag.filename = path
            builder_diags.add(diag)

        self._saveCache()
        return builder_diags | set(self.database.getDiagnosticsForPath(path))

    def getMessagesWithText(self, path, content):
        # type: (Path, AnyStr) -> Iterable[CheckerDiagnostic]
        """
        Dumps content to a temprary file and replaces the temporary file name
        for path on the diagnostics received
        """
        _logger.debug("Getting messages for '%s' with content", path)

        ext = path.name.split(".")[-1]
        temporary_file = tempfile.NamedTemporaryFile(suffix="." + ext, delete=False)

        temp_path = Path(temporary_file.name)

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

        temporary_file.file.write(toBytes(content))  # type: ignore
        temporary_file.close()
        messages = self.getMessagesByPath(temp_path)

        # Some messages may not include the filename field when checking a
        # file by content. In this case, we'll assume the empty filenames
        # refer to the same filename we got in the first place
        for message in messages:
            message.filename = path
            message.text = message.text.replace(temporary_file.name, path.name)

        self.database.removeSource(temp_path)
        removeIfExists(temporary_file.name)

        return set(messages) | set(self.database.getDiagnosticsForPath(path))
