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
        "Wrapper for json.dump"
        return serializer.dump(indent=True, *args, **kwargs)
except ImportError:
    try:
        import cPickle as serializer
    except ImportError:
        import pickle as serializer

    _dump = serializer.dump # pylint: disable=invalid-name

import hdlcc.exceptions
import hdlcc.builders
from hdlcc.config_parser import ConfigParser
from hdlcc.static_check import getStaticMessages

_logger = logging.getLogger('build messages')

# pylint: disable=too-many-instance-attributes,abstract-class-not-used
class HdlCodeCheckerBase(object):
    "HDL Code Checker project builder class"

    _USE_THREADS = True
    MAX_BUILD_STEPS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, project_file=None):
        self._start_dir = p.abspath(os.curdir)
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._background_thread = threading.Thread(
            target=self._buildByDependency, name='_buildByDependency')

        self._units_built = []

        self.project_file = project_file

        self._config = None
        self.builder = None

        self.setupEnvIfNeeded()
        #  self.buildByDependency()

    def _getCacheFilename(self, target_dir=None):
        "Returns the cache file name for a given project file"
        if target_dir is None:
            if self._config is None:
                return None
            else:
                target_dir = self._config.getTargetDir()
        return p.join(target_dir, '.hdlcc.cache')

    def clean(self):
        "Clean up generated files"
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
        "serializer load implementation"
        self._logger = logging.getLogger(state['_logger']['name'])
        self._logger.setLevel(state['_logger']['level'])
        del state['_logger']
        self._lock = threading.Lock()
        self._background_thread = threading.Thread(target=self._buildByDependency)

        self._config = ConfigParser.recoverFromState(state['_config'])

        builder_name = self._config.getBuilder()
        self._logger.debug("Recovered builder is '%s'", builder_name)
        builder_class = hdlcc.builders.getBuilderByName(builder_name)
        self.builder = builder_class.recoverFromState(state['builder'])

    @abc.abstractmethod
    def _handleUiInfo(self, message):
        """Method that should be overriden to handle info messages from
        HDL Code Checker to the user"""

    @abc.abstractmethod
    def _handleUiWarning(self, message):
        """Method that should be overriden to handle warning messages
        from HDL Code Checker to the user"""

    @abc.abstractmethod
    def _handleUiError(self, message):
        """Method that should be overriden to handle errors messages
        from HDL Code Checker to the user"""

    def _findSourceByDesignUnit(self, design_unit):
        "Finds the source files that have 'design_unit' defined"
        sources = []
        for source in self._config.getSources():
            if design_unit in source.getDesignUnitsDotted():
                sources += [source]
        if not sources:
            raise hdlcc.exceptions.DesignUnitNotFoundError(design_unit)
        return sources

    def _translateSourceDependencies(self, source):
        """Translate raw dependency list parsed from a given source to the
        project name space"""
        for dependency in source.getDependencies():
            if dependency['library'] in self.builder.getBuiltinLibraries() or \
               dependency['unit'] == 'all' or \
               (dependency['library'] == source.library and \
                dependency['unit'] in [x['name'] for x in source.getDesignUnits()]):
                continue
            yield dependency

    def _getSourceDependenciesSet(self, source):
        "Returns a set containing the dependencies of a given source"
        return set(["%s.%s" % (x['library'], x['unit']) \
                for x in self._translateSourceDependencies(source)])

    def _getBuildSteps(self):
        "Yields source objects that can be built given the units already built"
        sources_built = []
        for step in range(self.MAX_BUILD_STEPS):
            empty_step = True
            for source in self._config.getSources():
                dependencies = self._getSourceDependenciesSet(source)

                missing_dependencies = dependencies - set(self._units_built)

                # Skip current file if it has missing dependencies or if it was
                # already built
                if missing_dependencies:
                    self._logger.debug("Skipping %s for now because it has "
                                       "missing dependencies: %s", source,
                                       list(missing_dependencies))
                    continue

                if source.abspath in sources_built:
                    continue

                self._units_built += list(source.getDesignUnitsDotted())
                sources_built += [source.abspath]
                empty_step = False
                yield source

            if empty_step:
                missing_paths = list(set(
                    self._config.getSourcesPaths()) - set(sources_built))
                for missing_path in missing_paths: # pragma: no cover
                    source = self._config.getSourceByPath(missing_path)
                    dependencies = self._getSourceDependenciesSet(source)
                    missing_dependencies = dependencies - set(self._units_built)
                    if missing_dependencies:
                        self._logger.warning(
                            "Couldn't build source '%s'. Missing dependencies: %s",
                            str(source),
                            ", ".join([str(x) for x in missing_dependencies]))
                    #  else:
                    #      self._logger.warning(
                    #          "Source %s wasn't built but has no missing "
                    #          "dependencies", str(source))
                    #      yield source

                self._logger.debug("Breaking at step %d. Units built: %s",
                                   step, ", ".join(sorted(self._units_built)))

                raise StopIteration()

    def _sortBuildMessages(self, records): # pylint: disable=no-self-use
        "Sorts a given set of build records"
        return sorted(records, key=lambda x: \
                (x['error_type'], x['line_number'], x['error_number']))

    def _getMessagesAvailable(self, path, *args, **kwargs):
        """
        Checks if the builder can be called via self._getBuilderMessages
        or return info/messages identifying why it couldn"t be done
        """

        if not self.finishedBuilding():
            self._handleUiWarning("Project hasn't finished building, try again "
                                  "after it finishes.")
            return []

        if self._config.filename is None:
            return []

        source = None
        if self._config is not None:
            try:
                source = self._config.getSourceByPath(path)
            except KeyError:
                pass

        if source is None:
            return [{
                'checker'        : 'hdlcc',
                'line_number'    : '',
                'column'         : '',
                'filename'       : '',
                'error_number'   : '',
                'error_type'     : 'W',
                'error_message'  : 'Path "%s" not found in project file' %
                                   p.abspath(path)}]


        with self._lock:
            dependencies = self._getSourceDependenciesSet(source)

            self._logger.debug("Source '%s' depends on %s", str(source), \
                    ", ".join(["'%s'" % str(x) for x in dependencies]))

            if dependencies.issubset(set(self._units_built)):
                self._logger.debug("Dependencies for source '%s' are met", \
                        str(source))
                records = self._getBuilderMessages(path, *args, **kwargs)
                self.saveCache()
                return records

            else:
                return self._getBuilderMessages(path, *args, **kwargs)

    def _getBuilderMessages(self, path, batch_mode=False):
        '''Builds a given source file handling rebuild of units reported
        by the compiler'''

        self._logger.debug("Building '%s', batch_mode = %s",
                           str(path), batch_mode)

        flags = self._config.getBatchBuildFlagsByPath(path) if batch_mode else \
                self._config.getSingleBuildFlagsByPath(path)

        records, rebuilds = self.builder.build(self._config.getSourceByPath(path),
                                               forced=True, flags=flags)

        if rebuilds:
            source = self._config.getSourceByPath(path)
            self._logger.info("Building '%s' triggers rebuilding: %s",
                              source, ", ".join([str(x) for x in rebuilds]))

            for rebuild in rebuilds:
                self._logger.debug("Rebuild hint: '%s'", rebuild)
                if 'rebuild_path' in rebuild:
                    self._getBuilderMessages(rebuild['rebuild_path'],
                                             batch_mode=True)
                else:
                    design_unit = '%s.%s' % (rebuild['library_name'],
                                             rebuild['unit_name'])
                    for rebuild_source in \
                            self._findSourceByDesignUnit(design_unit):
                        self._getBuilderMessages(rebuild_source.abspath,
                                                 batch_mode=True)
            return self._getBuilderMessages(path)

        return self._sortBuildMessages(records)

    def saveCache(self):
        "Dumps project object to a file to recover its state later"
        cache_fname = self._getCacheFilename()

        state = {'serializer' : serializer.__name__,
                 '_logger': {'name' : self._logger.name,
                             'level' : self._logger.level},
                 'builder' : self.builder.getState(),
                 '_config' : self._config.getState(),
                }

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

    def getCompilationOrder(self):
        "Returns the build order needed by the _buildByDependency method"
        self._units_built = []
        return self._getBuildSteps()

    def buildByDependency(self):
        "Build the project by checking source file dependencies"
        if self._USE_THREADS: # pragma: no cover
            if not self._background_thread.isAlive():
                self._background_thread = \
                        threading.Thread(target=self._buildByDependency,
                                         name='_buildByDependency')
                self._background_thread.start()
            else:
                self._handleUiInfo("Build thread is already running")
        else: # pragma: no cover
            self._buildByDependency()

    def finishedBuilding(self):
        "Returns whether a background build has finished running"
        return not self._background_thread.isAlive()

    def waitForBuild(self):
        "Waits until the background build finishes"
        try:
            self._background_thread.join()
            self._logger.debug("Background thread joined")
        except RuntimeError:
            self._logger.debug("Background thread was not active")

        with self._lock:
            self._logger.info("Build has finished")

    def setupEnvIfNeeded(self):
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
                if target_dir:
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

    def _buildByDependency(self):
        "Build the project by checking source file dependencies"
        with self._lock:
            self.setupEnvIfNeeded()
            built = 0
            errors = 0
            warnings = 0
            self._units_built = []
            for source in self._getBuildSteps():
                records, _ = self.builder.build(source, \
                        flags=self._config.getBatchBuildFlagsByPath(source.filename))
                self._units_built += list(source.getDesignUnitsDotted())
                for record in self._sortBuildMessages(records):
                    if record['error_type'] == 'E':
                        _logger.debug(str(record))
                        errors += 1
                    elif record['error_type'] == 'W':
                        _logger.debug(str(record))
                        warnings += 1
                    elif self.builder.builder_name != 'xvhdl': # pragma: no cover
                        _logger.error("Invalid record: %s", str(record))
                        raise ValueError("Record '%s' is invalid" % record)
                built += 1
            self._logger.info("Done. Built %d sources, %d errors and %d warnings", \
                    built, errors, warnings)

    def getMessagesByPath(self, path, *args, **kwargs):
        """
        Returns the messages for the given path, including messages
        from the import configured builder (if available) and static
        checks
        """
        self.setupEnvIfNeeded()
        if not p.isabs(path): # pragma: no cover
            abspath = p.join(self._start_dir, path)
        else:
            abspath = path

        # _USE_THREADS is for debug only, no need to cover
        # this
        if self._USE_THREADS: # pragma: no cover
            records = []
            pool = ThreadPool()
            static_check = pool.apply_async(getStaticMessages, \
                    args=(open(abspath, 'r').read().split('\n'), ))
            builder_check = pool.apply_async(self._getMessagesAvailable, \
                    args=[abspath, ] + list(args), kwds=kwargs)

            records += static_check.get()
            records += builder_check.get()

            pool.terminate()
            pool.join()
        else:
            records = getStaticMessages(open(abspath, 'r').read().split('\n'))
            records += self._getMessagesAvailable(abspath, list(args), **kwargs)

        return self._sortBuildMessages(records)

    def getSources(self):
        "Returns a list of VhdlSourceFile objects parsed"
        return self._config.getSources()

