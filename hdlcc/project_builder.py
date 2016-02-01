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

import logging
import os
import threading
from multiprocessing.pool import ThreadPool
try:
    import cPickle as pickle # pragma: no cover
except ImportError:
    import pickle

import hdlcc.exceptions
from hdlcc.compilers import * # pylint: disable=wildcard-import
from hdlcc.config_parser import readConfigFile
from hdlcc.source_file import VhdlSourceFile
from hdlcc.static_check import vhdStaticCheck

_logger = logging.getLogger('build messages')

# pylint: disable=too-many-instance-attributes,abstract-class-not-used
class ProjectBuilder(object):
    "HDL Code Checker project builder class"
    MAX_BUILD_STEPS = 20

    def __init__(self):
        self.builder = None
        self.sources = {}
        self._logger = logging.getLogger(__name__)

        self._project_file = {'filename'  : None,
                              'timestamp' : 0,
                              'valid'     : False,
                              'cache'     : None}

        self._build_flags = {'batch'  : set(),
                             'single' : set(),
                             'global' : set()}

        self.halt = False
        self._units_built = []

        self._lock = threading.Lock()

    @staticmethod
    def _getCacheFilename(project_file):
        return os.path.join(os.path.dirname(project_file), \
            '.' + os.path.basename(project_file))

    @staticmethod
    def clean(project_file):
        "Clean up generated files for a clean build"
        cache_fname = ProjectBuilder._getCacheFilename(project_file)

        if os.path.exists(cache_fname):
            try:
                os.remove(cache_fname)
            except OSError:
                pass

    def __getstate__(self):
        "Pickle dump implementation"
        # Remove the _logger attribute because we can't pickle file or
        # stream objects. In its place, save the logger name
        state = self.__dict__.copy()
        state['_logger'] = self._logger.name
        del state['_lock']
        return state

    def __setstate__(self, state):
        "Pickle load implementation"
        # Get a logger with the name given in state['_logger'] (see
        # __getstate__) and update our dictionary with the pickled info
        self._logger = logging.getLogger(state['_logger'])
        self._logger.setLevel(logging.INFO)
        del state['_logger']
        self._lock = threading.Lock()
        self.__dict__.update(state)

    def handleUiInfo(self, message):
        """Method that should be overriden to handle info messages from
        HDL Code Checker to the user"""
        print '[info]' + str(message)

    def handleUiWarning(self, message):
        """Method that should be overriden to handle warning messages
        from HDL Code Checker to the user"""
        print '[warning]' + str(message)

    def handleUiError(self, message):
        """Method that should be overriden to handle errors messages
        from HDL Code Checker to the user"""
        print '[error]' + str(message)

    def setup(self, blocking=True):
        if blocking:
            self._runSetup()
        else:
            threading.Thread(target=self._runSetup).start()

    def _runSetup(self):
        "Read configuration file and build project in background"
        with self._lock:
            try:
                self.readConfigFile()
            except hdlcc.exceptions.SanityCheckError as exception:
                msg = {
                    'type' : 'error',
                    'text' : "HDL Code Checker disabled due to exception from builder "
                             "sanity check: " + str(exception)}
                self._logger.exception(msg['text'])
                self.handleUiInfo(msg)

            self.buildByDependency()
            self.saveCache()

    def _postUnpicklingSanityCheck(self):
        "Sanity checks to ensure the state after unpickling is still valid"
        self.builder.checkEnvironment()

    def _findSourceByDesignUnit(self, design_unit):
        "Finds the source files that have 'design_unit' defined"
        sources = []
        for source in self.sources.values():
            if design_unit in source.getDesignUnitsDotted():
                sources += [source]
        assert sources, "Design unit %s not found" % design_unit
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
            for source in self.sources.values():
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
                        list(set(self.sources.keys()) - set(sources_built)):
                    source = self.sources[missing_path]
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

    def _sortBuildMessages(self, records):
        "Sorts a given set of build records"
        return sorted(records, key=lambda x: \
                (x['error_type'], x['line_number'], x['error_number']))

    def _getMessagesFromCompiler(self, path, *args, **kwargs):
        """Wrapper around _getMessagesFromCompilerInner to handle the
        project state properly"""

        try:
            source = self.sources[os.path.abspath(path)]
        except KeyError:
            msg = {
                'checker'        : '',
                'line_number'    : '',
                'column'         : '',
                'filename'       : '',
                'error_number'   : '',
                'error_type'     : 'W',
                'error_message'  : 'Path "%s" not found in project file' %
                                   os.path.abspath(path)}
            if self._lock.locked():
                msg['error_message'] += ' (setup it still active, try again ' \
                        'after it finishes)'
            return [msg]

        dependencies = self._getSourceDependenciesSet(source)

        self._logger.debug("Source '%s' depends on %s", str(source), \
                ", ".join(["'%s'" % str(x) for x in dependencies]))

        if dependencies.issubset(set(self._units_built)):
            self._logger.debug("Dependencies for source '%s' are met", \
                    str(source))
            records = self._getMessagesFromCompilerInner(path, *args, **kwargs)
            self.saveCache()
            return records

        elif self._lock.locked():
            self.handleUiWarning("Project setup is still running...")
            return []

        else:
            with self._lock:
                return self._getMessagesFromCompilerInner(path, *args, **kwargs)

    def _getMessagesFromCompilerInner(self, path, batch_mode=False):
        """Builds a given source file handling rebuild of units reported by the
        compiler"""
        if not self._project_file['valid']:
            self._logger.warning("Project file is invalid, not building")
            return []

        if os.path.abspath(path) not in self.sources.keys():
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

        flags = self._build_flags['batch'] if batch_mode else \
                self._build_flags['single']

        records, rebuilds = self.builder.build(
            self.sources[os.path.abspath(path)], forced=True,
            flags=flags)

        if rebuilds:
            source = self.sources[os.path.abspath(path)]
            rebuild_units = ["%s.%s" % (x[0], x[1]) for x in rebuilds]

            self._logger.info("Building '%s' triggers rebuild of units: %s",
                              source, ", ".join(rebuild_units))
            for rebuild_unit in rebuild_units:
                for rebuild_source in self._findSourceByDesignUnit(rebuild_unit):
                    self._getMessagesFromCompilerInner(rebuild_source.abspath,
                                                       batch_mode=True)
            return self._getMessagesFromCompilerInner(path)

        return self._sortBuildMessages(records)

    def readConfigFile(self):
        "Reads the configuration given by self._project_file['filename']"

        cache_fname = self._getCacheFilename(self._project_file['filename'])

        self._logger.info("Reading configuration file: '%s'", \
                str(self._project_file['filename']))

        if os.path.exists(cache_fname):
            try:
                obj = pickle.load(open(cache_fname, 'r'))
                self.__dict__.update(obj.__dict__)
                # Environment may have change since we last saved the file,
                # we must recheck
                try:
                    self._postUnpicklingSanityCheck()
                except hdlcc.exceptions.VimHdlBaseException:
                    self._logger.exception("Sanity check error")
                    self._project_file['valid'] = False
            except (EOFError, IOError):
                self._logger.warning("Unable to unpickle cached filename")

        if not os.path.exists(self._project_file['filename']):
            self._project_file['valid'] = False
            return
        #  If the library file hasn't changed, we're up to date an return
        if os.path.getmtime(self._project_file['filename']) <= \
                self._project_file['timestamp']:
            return

        self._logger.info("Updating config file")

        self._project_file['timestamp'] = os.path.getmtime(self._project_file['filename'])

        target_dir, builder_name, builder_flags, source_list = \
                readConfigFile(self._project_file['filename'])

        self._logger.info("Builder info:")
        self._logger.info(" - Target dir:    %s", target_dir)
        self._logger.info(" - Builder name:  %s", builder_name)
        self._logger.info(" - Builder flags (global): %s", \
                builder_flags['global'])
        self._logger.info(" - Builder flags (batch): %s", \
                builder_flags['batch'])
        self._logger.info(" - Builder flags (single): %s", \
                builder_flags['single'])

        self._build_flags = builder_flags.copy()

        # Check if the builder selected is implemented and create the
        # builder attribute
        if builder_name == 'msim':
            try:
                self.builder = MSim(target_dir)
            except hdlcc.exceptions.SanityCheckError:
                self._logger.warning("Builder '%s' sanity check failed", builder_name)
        elif builder_name == 'xvhdl':
            try:
                self.builder = XVHDL(target_dir)
            except hdlcc.exceptions.SanityCheckError:
                self._logger.warning("Builder '%s' sanity check failed", builder_name)
        elif builder_name == 'ghdl':
            try:
                self.builder = GHDL(target_dir)
            except hdlcc.exceptions.SanityCheckError:
                self._logger.warning("Builder '%s' sanity check failed", builder_name)

        if self.builder is None:
            self._logger.info("Using Fallback builder")
            self.builder = Fallback(target_dir)

        # Remove from our sources the files that are no longes listed
        # in the configuration file.
        # TODO: Check feasibility to tell the builder to remove compiled
        # files so the removed file is actually removed from the library
        for source in set(self.sources.keys()) - \
                set([os.path.abspath(x[0]) for x in source_list]):
            self._logger.debug("Removing %s from library", source)
            self.sources.pop(source)

        # Iterate over the sections to get sources and build flags.
        # Take care to don't recreate a library
        for source, library, flags in source_list:
            if os.path.abspath(source) in self.sources.keys():
                _source = self.sources[os.path.abspath(source)]
            else:
                _source = VhdlSourceFile(source, library)
            _source.flags = self._build_flags['global'].copy()
            if flags:
                _source.flags.update(flags)

            self.sources[_source.abspath] = _source

        self._project_file['valid'] = True

    def saveCache(self):
        "Dumps project object to a file to recover its state later"
        cache_fname = self._getCacheFilename(self._project_file['filename'])
        pickle.dump(self, open(cache_fname, 'w'))

    def cleanCache(self):
        "Remove the cached project data and clean all libraries as well"
        cache_fname = self._getCacheFilename(self._project_file['filename'])

        try:
            os.remove(cache_fname)
        except OSError:
            self._logger.debug("Cache filename '%s' not found", cache_fname)
        self._project_file['timestamp'] = 0

    def getCompilationOrder(self):
        "Returns the build order osed by the buildByDependency method"
        self._units_built = []
        return self._getBuildSteps()

    def buildByDependency(self):
        "Build the project by checking source file dependencies"
        if not self._project_file['valid']:
            self._logger.warning("Project file is invalid, not building")
        built = 0
        errors = 0
        warnings = 0
        self._units_built = []
        for source in self._getBuildSteps():
            records, _ = self.builder.build(source, \
                    flags=self._build_flags['batch'])
            self._units_built += list(source.getDesignUnitsDotted())
            for record in self._sortBuildMessages(records):
                if record['error_type'] == 'E':
                    _logger.debug(str(record))
                    errors += 1
                elif record['error_type'] == 'W':
                    _logger.debug(str(record))
                    warnings += 1
                else:
                    _logger.fatal(str(record))
                    assert 0, 'Invalid record: %s' % str(record)
            built += 1
        self._logger.info("Done. Built %d sources, %d errors and %d warnings", \
                built, errors, warnings)

    def getMessagesByPath(self, path, *args, **kwargs):
        records = []

        pool = ThreadPool()
        static_check = pool.apply_async(vhdStaticCheck, \
                args=(open(path, 'r').read().split('\n'), ))
        compiler_check = pool.apply_async(self._getMessagesFromCompiler,
            args=[path, ] + list(args))

        records += static_check.get()
        records += compiler_check.get()

        pool.terminate()
        pool.join()

        return self._sortBuildMessages(records)


    def setProjectFile(self, project_file):
        self._project_file = {'filename'  : os.path.abspath(project_file),
                              'timestamp' : 0,
                              'valid'     : True if os.path.exists(project_file)
                                            else False,
                              'cache'     : None}


