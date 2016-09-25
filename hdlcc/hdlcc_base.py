# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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
import os
import os.path as p
import shutil
import logging
import traceback
import threading
from multiprocessing.pool import ThreadPool

# Make the serializer transparent
try:
    import json as serializer
    def _dump(*args, **kwargs):
        """
        Wrapper for json.dump
        """
        return serializer.dump(indent=True, *args, **kwargs)
except ImportError:
    try:
        import cPickle as serializer
    except ImportError:
        import pickle as serializer

    _dump = serializer.dump  # pylint: disable=invalid-name

import hdlcc.exceptions
import hdlcc.builders
from hdlcc.utils import getFileType, removeDuplicates
from hdlcc.parsers import VerilogParser, VhdlParser
from hdlcc.config_parser import ConfigParser
from hdlcc.static_check import getStaticMessages

_logger = logging.getLogger('build messages')

# pylint: disable=too-many-instance-attributes
# pylint: disable=abstract-class-not-used
class HdlCodeCheckerBase(object):
    """
    HDL Code Checker project builder class
    """

    _USE_THREADS = True
    MAX_BUILD_STEPS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, project_file=None):
        self._start_dir = p.abspath(os.curdir)
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._background_thread = None

        self.project_file = project_file

        self._config = None
        self.builder = None

        self._setupEnvIfNeeded()

    def _getCacheFilename(self, target_dir=None):
        """
        Returns the cache file name for a given project file
        """
        if target_dir is None:
            if self._config is None or self._config.getBuilder() == 'fallback':
                return None
            else:
                target_dir = self._config.getTargetDir()
        return p.join(target_dir, '.hdlcc.cache')

    def _saveCache(self):
        """
        Dumps project object to a file to recover its state later
        """
        cache_fname = self._getCacheFilename()
        if self.builder.builder_name == 'fallback' or cache_fname is None:
            self._logger.debug("Skipping cache save")
            return

        state = {'serializer' : serializer.__name__,
                 '_logger': {'name' : self._logger.name,
                             'level' : self._logger.level},
                 'builder' : self.builder.getState(),
                 '_config' : self._config.getState()}

        self._logger.debug("Saving state to '%s'", cache_fname)
        _dump(state, open(cache_fname, 'w'))

    def _recoverCache(self, target_dir):
        """
        Tries to recover cached info for the given project_file. If
        something goes wrong, assume the cache is invalid and return
        nothing. Otherwise, return the cached object
        """
        cache_fname = self._getCacheFilename(target_dir)
        #  if self.project_file is None or cache_fname is None:
        if cache_fname is None:
            self._logger.warning("Can't recover cache from None")
            return

        _logger.debug("Trying to recover from '%s'", cache_fname)
        cache = None
        if p.exists(cache_fname):
            try:
                cache = serializer.load(open(cache_fname, 'r'))
                self._handleUiInfo("Recovered cache from '%s' (used '%s')" %
                                   (cache_fname, serializer.__package__))
                self._setState(cache)
                self.builder.checkEnvironment()
            except ValueError:
                self._handleUiError(
                    "Unable to recover cache from '%s' using '%s'\n"
                    "Traceback:\n%s" % \
                        (cache_fname, serializer.__package__,
                         traceback.format_exc()))
        else:
            _logger.debug("File not found")

    def _setupEnvIfNeeded(self):
        """
        Updates or creates the environment, which includes checking
        if the configuration file should be parsed and creating the
        appropriate builder objects
        """
        try:
            # If the configuration is undefined, try to extract the
            # target dir from the project file so we can have a hint of
            # where the cache file should be
            if self._config is None and self.project_file is not None:
                target_dir, _ = ConfigParser.simpleParse(self.project_file)
                self._recoverCache(target_dir)

            # No configuration defined means we failed to recover it
            # from the cache
            if self._config is None:
                self._config = ConfigParser(self.project_file)

            # If the builder is still undefined we failed to recover
            # from cache
            if self.builder is None:
                builder_name = self._config.getBuilder()
                builder_class = hdlcc.builders.getBuilderByName(builder_name)
                self.builder = builder_class(self._config.getTargetDir())

                self._logger.info("Selected builder is '%s'",
                                  self.builder.builder_name)
            assert self.builder is not None

        except hdlcc.exceptions.SanityCheckError as exc:
            _msg = "Failed to create builder '%s'" % exc.builder
            self._logger.warning(_msg)
            self._handleUiError(_msg)
            self.builder = hdlcc.builders.Fallback(self._config.getTargetDir())

    def clean(self):
        """
        Clean up generated files
        """
        cache_fname = self._getCacheFilename()
        if cache_fname is not None and p.exists(cache_fname):
            _logger.debug("Removing cached info in '%s'", cache_fname)
            os.remove(cache_fname)

        target_dir = self._config.getTargetDir()
        if p.exists(target_dir):
            _logger.debug("Removing target dir '%s'", target_dir)
            shutil.rmtree(target_dir)

        del self._config
        del self.builder
        self._config = None
        self.builder = None

    def _setState(self, state):
        """
        Serializer load implementation
        """
        self._logger = logging.getLogger(state['_logger']['name'])
        self._logger.setLevel(state['_logger']['level'])
        del state['_logger']
        self._lock = threading.Lock()
        self._background_thread = None

        self._config = ConfigParser.recoverFromState(state['_config'])

        builder_name = self._config.getBuilder()
        self._logger.debug("Recovered builder is '%s'", builder_name)
        builder_class = hdlcc.builders.getBuilderByName(builder_name)
        self.builder = builder_class.recoverFromState(state['builder'])

    @abc.abstractmethod
    def _handleUiInfo(self, message):
        """
        Method that should be overriden to handle info messages from
        HDL Code Checker to the user
        """

    @abc.abstractmethod
    def _handleUiWarning(self, message):
        """
        Method that should be overriden to handle warning messages
        from HDL Code Checker to the user
        """

    @abc.abstractmethod
    def _handleUiError(self, message):
        """
        Method that should be overriden to handle errors messages
        from HDL Code Checker to the user
        """

    def _getSourceByPath(self, path):
        """
        Get the source object, flags and any additional info to be displayed
        """
        source = None
        remarks = []

        if self._config is not None:
            try:
                source = self._config.getSourceByPath(path)
            except KeyError:
                pass

        # If the source file was not found on the configuration file, add this
        # as a remark.
        # Also, create a source parser object with some library so the user can
        # at least have some info on the source
        if source is None:
            remarks += [{
                'checker'        : 'hdlcc',
                'line_number'    : '',
                'column'         : '',
                'filename'       : '',
                'error_number'   : '',
                'error_type'     : 'W',
                'error_message'  : 'Path "%s" not found in project file' %
                                   p.abspath(path)}]
            self._logger.info("Path %s not found in the project file", path)
            cls = VhdlParser if getFileType(path) == 'vhdl' else VerilogParser
            source = cls(path, library='undefined')

        return source, remarks

    def _resolveRelativeNames(self, source):
        """
        Translate raw dependency list parsed from a given source to the
        project name space
        """
        for dependency in source.getDependencies():
            if dependency['library'] in self.builder.getBuiltinLibraries() or \
               dependency['unit'] == 'all' or \
               (dependency['library'] == source.library and \
                dependency['unit'] in [x['name'] for x in source.getDesignUnits()]):
                continue
            yield dependency['library'], dependency['unit']

    @staticmethod
    def _sortBuildMessages(records):
        """
        Sorts a given set of build records
        """
        return sorted(records, key=lambda x: \
                (x['error_type'], x['line_number'], x['error_number']))

    def _getBuildSequence(self, source, reference=None):
        """
        Recursively finds out the dependencies of the given source file
        """
        self._logger.info("Checking build sequence for %s", source)
        build_sequence = []
        for library, unit in self._resolveRelativeNames(source):
            # Get a list of source files that contains this design unit
            dependencies_list = self._config.discoverSourceDependencies(
                unit, library)

            dependency = dependencies_list[0]

            # If we found more than a single file, then multiple files
            # have the same entity or package name and we failed to
            # identify the real file
            if len(dependencies_list) != 1:
                self._handleUiWarning(
                    "Returning dependency '%s' for %s.%s in file '%s', but "
                    "there were %d other matches: %s. The selected option may "
                    "be sub-optimal" % (
                        dependency.filename, library, unit, source.filename,
                        len(dependencies_list),
                        ', '.join([x.filename for x in dependencies_list])))

            # Check if we found out that a dependency is the same we
            # found in the previous call to break the circular loop
            if dependency == reference:
                raise hdlcc.exceptions.CircularDependencyFound(
                    source, dependency)

            dependency_build_sequence = self._getBuildSequence(
                dependency, reference=source)

            build_sequence += dependency_build_sequence + [dependency]

        return removeDuplicates(build_sequence)

    def _getBuilderMessages(self, path, batch_mode=False):
        """
        Builds a given source file handling rebuild of units reported
        by the compiler
        Builds the given source taking care of recursively building its
        dependencies first
        """
        source, remarks = self._getSourceByPath(path)
        try:
            flags = self._config.getBuildFlags(path, batch_mode)
        except KeyError:
            flags = []

        self._logger.debug("Building '%s', batch_mode = %s",
                           str(path), batch_mode)

        build_sequence = self._getBuildSequence(source)

        self._logger.debug("Compilation build_sequence is\n: %s",
                           "\n".join([x.filename for x in build_sequence]))

        records = []
        for _source in build_sequence:
            _flags = self._config.getBuildFlags(_source.filename,
                                                batch_mode=False)
            _records, rebuilds = self.builder.build(_source, forced=False,
                                                    flags=_flags)
            records += _records
            self._handleRebuilds(rebuilds, _source)

        source_records, rebuilds = self.builder.build(source, forced=True,
                                                      flags=flags)

        self._handleRebuilds(rebuilds, source)

        return self._sortBuildMessages(records + source_records + remarks)

    def _handleRebuilds(self, rebuilds, source=None):
        if source is not None and rebuilds:
            self._logger.info("Building '%s' triggers rebuilding: %s",
                              source, ", ".join([str(x) for x in rebuilds]))
        for rebuild in rebuilds:
            self._logger.debug("Rebuild hint: '%s'", rebuild)
            if 'rebuild_path' in rebuild:
                self._getBuilderMessages(rebuild['rebuild_path'],
                                         batch_mode=True)
            else:
                rebuild_sources = self._config.findSourcesByDesignUnit(
                    rebuild['unit_name'], rebuild['library_name'])
                for rebuild_source in rebuild_sources:
                    self._getBuilderMessages(rebuild_source.abspath,
                                             batch_mode=True)

    def hasFinishedBuilding(self):
        """
        Returns whether a background build has finished running
        """
        if self._background_thread is None:
            return True
        return not self._background_thread.isAlive()

    def waitForBuild(self):
        """
        Waits until the background build finishes
        """
        if self._background_thread is None:
            return
        try:
            self._background_thread.join()
            self._logger.debug("Background thread joined")
        except RuntimeError:
            self._logger.debug("Background thread was not active")

        with self._lock:
            self._logger.info("Build has finished")

    def _isBuilderCallable(self):
        """
        Checks if all preconditions for calling the builder have been
        met
        """
        if self._config.filename is None or not self.hasFinishedBuilding():
            return False
        return True

    def getMessagesByPath(self, path, *args, **kwargs):
        """
        Returns the messages for the given path, including messages
        from the import configured builder (if available) and static
        checks
        """
        self._setupEnvIfNeeded()
        if not p.isabs(path): # pragma: no cover
            abspath = p.join(self._start_dir, path)
        else:
            abspath = path

        if not self.hasFinishedBuilding():
            self._handleUiWarning("Project hasn't finished building, try again "
                                  "after it finishes.")

        # _USE_THREADS is for debug only, no need to cover
        # this
        if self._USE_THREADS: # pragma: no cover
            records = []
            pool = ThreadPool()
            static_check = pool.apply_async(getStaticMessages, \
                    args=(open(abspath, 'r').read().split('\n'), ))
            if self._isBuilderCallable():
                builder_check = pool.apply_async(
                    self._getBuilderMessages,
                    args=[abspath, ] + list(args),
                    kwds=kwargs)
                records += builder_check.get()

            records += static_check.get()

            pool.terminate()
            pool.join()
        else:
            records = getStaticMessages(open(abspath, 'r').read().split('\n'))
            if self._isBuilderCallable():
                records += self._getBuilderMessages(
                    abspath, list(args), **kwargs)

        self._saveCache()
        return self._sortBuildMessages(records)

    def getSources(self):
        """
        Returns a list of VhdlSourceFile objects parsed
        """
        return self._config.getSources()

