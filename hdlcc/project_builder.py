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
import threading
import logging

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
    MAX_BUILD_STEPS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, project_file=None):
        self.builder = None
        self._logger = logging.getLogger(__name__)

        self.halt = False
        self._units_built = []

        self._config = ConfigParser(project_file)
        parsed_builder = self._config.getBuilder()

        # Check if the builder selected is implemented and create the
        # builder attribute
        self.builder = None
        try:
            if parsed_builder == 'msim':
                self.builder = hdlcc.builders.MSim(self._config.getTargetDir())
            elif parsed_builder == 'xvhdl':
                self.builder = hdlcc.builders.XVHDL(self._config.getTargetDir())
            elif parsed_builder == 'ghdl':
                self.builder = hdlcc.builders.GHDL(self._config.getTargetDir())
        except hdlcc.exceptions.SanityCheckError:
            self._logger.warning("Builder '%s' sanity check failed", parsed_builder)

        if self.builder is None:
            self._logger.info("Using Fallback builder")
            self.builder = hdlcc.builders.Fallback(self._config.getTargetDir())

    @staticmethod
    def _getCacheFilename(project_file):
        "Returns the cache file name for a given project file"
        return p.join(p.dirname(project_file), \
            '.' + p.basename(project_file))

    @staticmethod
    def clean(project_file):
        "Clean up generated files for a clean build"
        cache_fname = ProjectBuilder._getCacheFilename(project_file)

        if p.exists(cache_fname):
            os.remove(cache_fname)

    def __getstate__(self):
        "Pickle dump implementation"
        # Remove the _logger attribute because we can't pickle file or
        # stream objects. In its place, save the logger name
        state = self.__dict__.copy()
        state['_logger'] = self._logger.name
        return state

    def __setstate__(self, state):
        "Pickle load implementation"
        # Get a logger with the name given in state['_logger'] (see
        # __getstate__) and update our dictionary with the pickled info
        self._logger = logging.getLogger(state['_logger'])
        self._logger.setLevel(logging.INFO)
        del state['_logger']
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
        return sources

    def _translateSourceDependencies(self, source):
        """Translate raw dependency list parsed from a given source to the
        project name space"""
        for dependency in source.getDependencies():
            if dependency['library'] in self.builder.builtin_libraries or \
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
            if self.halt:
                self._logger.info("Halt requested, stopping")
                raise StopIteration()
            empty_step = True
            for source in self._config.getSources():
                dependencies = self._getSourceDependenciesSet(source)

                missing_dependencies = dependencies - set(self._units_built)

                # If there are missing dependencies skip this file for now
                if missing_dependencies or source.abspath in sources_built:
                    self._logger.debug("Skipping %s for now because it has "
                                       "missing dependencies: %s", source,
                                       list(missing_dependencies))
                    continue

                self._logger.debug("All dependencies for %s are met", str(source))

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

        try:
            source = self._config.getSourceByPath(path)
        except KeyError:
            msg = {
                'checker'        : '',
                'line_number'    : '',
                'column'         : '',
                'filename'       : '',
                'error_number'   : '',
                'error_type'     : 'W',
                'error_message'  : 'Path "%s" not found in project file' %
                                   p.abspath(path)}
            #  if self._setup_thread.isAlive():
            #      msg['error_message'] += ' (setup it still active, try again ' \
            #              'after it finishes)'
            return [msg]

        dependencies = self._getSourceDependenciesSet(source)

        self._logger.debug("Source '%s' depends on %s", str(source), \
                ", ".join(["'%s'" % str(x) for x in dependencies]))

        if dependencies.issubset(set(self._units_built)):
            self._logger.debug("Dependencies for source '%s' are met", \
                    str(source))
            records = self._getBuilderMessages(path, *args, **kwargs)
            self.saveCache()
            return records

        #  elif self._setup_thread.isAlive():
        #      self._handleUiWarning("Project setup is still running...")
        #      return []

        else:
            return self._getBuilderMessages(path, *args, **kwargs)

    def _getBuilderMessages(self, path, batch_mode=False):
        '''Builds a given source file handling rebuild of units reported
        by the compiler'''
        #  if not self._project_file['valid']:
        #      self._logger.warning("Project file is invalid, not building")
        #      return []

        if not self._config.hasSource(path):
            return [{
                'checker'        : 'hdl-code-checker',
                'line_number'    : None,
                'column'         : None,
                'filename'       : path,
                'error_number'   : None,
                'error_type'     : 'W',
                'error_message'  : "Source '%s' not found on the configuration"
                                   " file" % path,
            }]

        #  flags = self._build_flags['batch'] if batch_mode else \
        #          self._build_flags['single']

        flags = self._config.getBatchBuildFlagsByPath(path) if batch_mode else \
                self._config.getSingleBuildFlagsByPath(path)

        records, rebuilds = self.builder.build(self._config.getSourceByPath(path),
                                               forced=True, flags=flags)

        if rebuilds:
            source = self._config.getSourceByPath(path)
            rebuild_units = ["%s.%s" % (x[0], x[1]) for x in rebuilds]

            self._logger.info("Building '%s' triggers rebuild of units: %s",
                              source, ", ".join(rebuild_units))
            for rebuild_unit in rebuild_units:
                for rebuild_source in self._findSourceByDesignUnit(rebuild_unit):
                    self._getBuilderMessages(rebuild_source.abspath,
                                             batch_mode=True)
            return self._getBuilderMessages(path)

        return self._sortBuildMessages(records)

    def saveCache(self):
        "Dumps project object to a file to recover its state later"
        cache_fname = self._getCacheFilename(self._config.filename)
        pickle.dump(self, open(cache_fname, 'w'))

    def getCompilationOrder(self):
        "Returns the build order needed by the buildByDependency method"
        self._units_built = []
        return self._getBuildSteps()

    def buildByDependency(self):
        "Build the project by checking source file dependencies"
        built = 0
        errors = 0
        warnings = 0
        self._units_built = []
        for source in self._getBuildSteps():
            records, _ = self.builder.build(source, \
                    self._config.getBatchBuildFlagsByPath(source.filename))
            self._units_built += list(source.getDesignUnitsDotted())
            for record in self._sortBuildMessages(records):
                if record['error_type'] == 'E':
                    _logger.debug(str(record))
                    errors += 1
                elif record['error_type'] == 'W':
                    _logger.debug(str(record))
                    warnings += 1
                else: # pragma: no cover
                    _logger.fatal(str(record))
                    assert 0, 'Invalid record: %s' % str(record)
            built += 1
        self._logger.info("Done. Built %d sources, %d errors and %d warnings", \
                built, errors, warnings)


    def getMessagesByPath(self, path, *args, **kwargs):
        records = []

        pool = ThreadPool()
        static_check = pool.apply_async(getStaticMessages, \
                args=(open(path, 'r').read().split('\n'), ))
        builder_check = pool.apply_async(self._getMessagesAvailable, \
                args=[path, ] + list(args))

        records += static_check.get()
        records += builder_check.get()

        pool.terminate()
        pool.join()

        #  records = getStaticMessages(open(path, 'r').read().split('\n')) + \
        #            self._getMessagesAvailable(path, *args)
        return self._sortBuildMessages(records)


