# This file is part of HDL Code Checker.
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
import logging

import threading
from multiprocessing.pool import ThreadPool

try:
    import cPickle as pickle # pragma: no cover
except ImportError:
    import pickle

import hdlcc.exceptions
import hdlcc.builders
from hdlcc.config_parser import ConfigParser
from hdlcc.static_check import getStaticMessages

_logger = logging.getLogger('build messages')

# pylint: disable=too-many-instance-attributes,abstract-class-not-used
class ProjectBuilder(object):
    "HDL Code Checker project builder class"

    GET_MESSAGES_WITH_THREADS = True
    MAX_BUILD_STEPS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, project_file=None):
        self._start_dir = p.abspath(os.curdir)
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._background_thread = threading.Thread(target=self._buildByDependency)

        self._units_built = []

        self.project_file = project_file

        self._config = None
        self.builder = None

        self.buildByDependency()

    @staticmethod
    def _getCacheFilename(project_file):
        "Returns the cache file name for a given project file"
        return p.join(p.dirname(project_file), \
            '.' + p.basename(project_file))

    @staticmethod
    def clean(project_file):
        "Clean up generated files for a clean build"
        if project_file is None:
            _logger.debug("Project file is None, can't clean")
            return
        cache_fname = ProjectBuilder._getCacheFilename(project_file)
        if p.exists(cache_fname):
            os.remove(cache_fname)

    def __getstate__(self):
        "Pickle dump implementation"
        # Remove the _logger attribute because we can't pickle file or
        # stream objects. In its place, save the logger name
        state = self.__dict__.copy()
        state['_logger'] = {'name' : self._logger.name,
                            'level' : self._logger.level}
        del state['_lock']
        del state['_background_thread']

        return state

    def __setstate__(self, state):
        "Pickle load implementation"
        # Get a logger with the name given in state['_logger'] (see
        # __getstate__) and update our dictionary with the pickled info
        self._logger = logging.getLogger(state['_logger']['name'])
        self._logger.setLevel(state['_logger']['level'])
        del state['_logger']
        self._lock = threading.Lock()
        self._background_thread = threading.Thread(target=self._buildByDependency)
        self.__dict__.update(state)

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

    def _postUnpicklingSanityCheck(self):
        "Sanity checks to ensure the state after unpickling is still valid"
        self.builder.checkEnvironment()

    def _findSourceByDesignUnit(self, design_unit):
        "Finds the source files that have 'design_unit' defined"
        sources = []
        #  for source in self.sources.values():
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
                sources_not_built = False

                for missing_path in \
                        list(set(self._config.getSourcesPaths()) - set(sources_built)):
                    source = self._config.getSourceByPath(missing_path)
                    dependencies = self._getSourceDependenciesSet(source)
                    missing_dependencies = dependencies - set(self._units_built)
                    if missing_dependencies:
                        sources_not_built = True
                        self._logger.info(
                            "Couldn't build source '%s'. Missing dependencies: %s",
                            str(source),
                            ", ".join([str(x) for x in missing_dependencies]))
                    else:
                        self._logger.warning(
                            "Source %s wasn't built but has no missing "
                            "dependencies", str(source))
                        yield source
                if sources_not_built:
                    self._logger.warning("Some sources were not built")

                self._logger.info("Breaking at step %d. Units built: %s",
                                  step, ", ".join(sorted(self._units_built)))

                raise StopIteration()

    def _sortBuildMessages(self, records): # pylint: disable=no-self-use
        "Sorts a given set of build records"
        return sorted(records, key=lambda x: \
                (x['error_type'], x['line_number'], x['error_number']))

    def _getMessagesAvailable(self, path, *args, **kwargs):
        '''Checks if the builder can be called via self._getBuilderMessages
        or return info/messages identifying why it couldn't be done'''

        if self._background_thread.isAlive():
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
        cache_fname = self._getCacheFilename(self._config.filename)
        pickle.dump(self, open(cache_fname, 'w'), 0)

    def _recoverCache(self):
        '''Tries to recover cached info for the given project_file.
        If something goes wrong, assume the cache is invalid and return
        nothing. Otherwise, return the cached object'''
        if self.project_file is None:
            self._logger.debug("Can't recover cache from None")
            return
        cache_fname = self._getCacheFilename(self.project_file)
        cache = None
        if p.exists(cache_fname):
            try:
                cache = pickle.load(open(cache_fname, 'r'))
                print "Recovered cache from '%s'" % cache_fname
            except (pickle.UnpicklingError, ImportError):
                print "Unable to recover from '%s'" % cache_fname

        return cache

    def getCompilationOrder(self):
        "Returns the build order needed by the _buildByDependency method"
        self._units_built = []
        return self._getBuildSteps()

    def buildByDependency(self):
        "Build the project by checking source file dependencies"
        if not self._background_thread.isAlive():
            self._background_thread = \
                    threading.Thread(target=self._buildByDependency,
                                     name='_buildByDependency')
            self._background_thread.start()
        else:
            self._handleUiInfo("Build thread is already running")

    def finishedBuilding(self):
        "Returns whether a background build has finished running"
        return not self._background_thread.isAlive()

    def waitForBuild(self):
        "Waits until the background build finishes"
        if self._background_thread.isAlive():
            self._background_thread.join()
        with self._lock:
            self._logger.info("Build has finished")
    def _updateEnvironmentIfNeeded(self):
        '''Updates or creates the environment, which includes checking
        if the configuration file should be parsed and creating the
        appropriate builder objects'''

        # If we have run before and we don't need to parse it, just
        # return early
        if not (self._config is None or self._config.shouldParse()):
            return

        cache = self._recoverCache()

        if cache is None:
            # No cache file or unable to recover from cache file
            self._config = ConfigParser(self.project_file)
            builder_name = self._config.getBuilder()
            builder_class = hdlcc.builders.getBuilderByName(builder_name)
            try:
                self.builder = builder_class(self._config.getTargetDir())
            except hdlcc.exceptions.SanityCheckError:
                self._handleUiError("Failed to create builder '%s'" % \
                    builder_class.__builder_name__)
                self.builder = hdlcc.builders.Fallback(self._config.getTargetDir())

        else:
            self.__dict__.update(cache.__dict__)

    def _buildByDependency(self):
        "Build the project by checking source file dependencies"
        with self._lock:
            self._updateEnvironmentIfNeeded()
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
                    else: # pragma: no cover
                        _logger.error("Invalid record: %s", str(record))
                built += 1
            self._logger.info("Done. Built %d sources, %d errors and %d warnings", \
                    built, errors, warnings)

    def getMessagesByPath(self, path, *args, **kwargs):
        '''Returns the messages for the given path, including messages
        from the import configured builder (if available) and static
        checks'''
        if not p.isabs(path):
            abspath = p.join(self._start_dir, path)
        else:
            abspath = path

        if self.GET_MESSAGES_WITH_THREADS:
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

