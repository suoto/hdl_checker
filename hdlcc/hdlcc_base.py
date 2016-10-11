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
from multiprocessing.pool import ThreadPool

import hdlcc.exceptions
import hdlcc.builders
from hdlcc.utils import (getFileType, removeDuplicates, serializer, dump,
                         samefile)
from hdlcc.parsers import VerilogParser, VhdlParser
from hdlcc.config_parser import ConfigParser
from hdlcc.static_check import getStaticMessages

_logger = logging.getLogger('build messages')

class HdlCodeCheckerBase(object):
    """
    HDL Code Checker project builder class
    """

    _USE_THREADS = True
    _MAX_REBUILD_ATTEMPTS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, project_file=None):
        self._start_dir = p.abspath(os.curdir)
        self._logger = logging.getLogger(__name__)
        self._cache = {}

        self.project_file = project_file

        self._config = None
        self.builder = None

        self._setupEnvIfNeeded()
        self._saveCache()

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
        if not p.exists(p.dirname(cache_fname)):
            os.mkdir(p.dirname(cache_fname))
        dump(state, open(cache_fname, 'w'))

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
        if not p.exists(cache_fname):  # pragma: no cover
            _logger.debug("File not found")
            return

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
            self._handleUiError("Failed to create builder '%s'" % exc.builder)
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

    def getBuildSequence(self, source):
        """
        Wrapper to _getBuildSequence passing the initial build sequence
        list empty and caching the result
        """
        # Despite we renew the cache when on buffer enter, we must also
        # check if:
        #
        #   1) Any file has been changed by some background process that
        #      the editor is unaware of (Vivado maybe?)
        #      To cope with this, we'll check if the newest modification
        #      time of the build sequence hasn't changed since we cached
        #      the build sequence
        #
        #   2) The source being currently requested is the same that was
        #      cached previously
        #
        # In any case, the cached build sequence will always match the
        # source file that was visited (i.e., it won't be replaced if
        # the item (2) above is true)
        #
        key = 'getBuildSequence'
        if key in self._cache:
            # We can only use the cached build sequence if the source
            # is the same that was cached before
            path = self._cache[key]['path']
            if samefile(path, source.filename):
                sequence = self._cache[key]['sequence']
                cache_mtime = self._cache[key]['cache_mtime']
                last_mtime = max([x.getmtime() for x in sequence])

                if cache_mtime == last_mtime:
                    return self._cache[key]['sequence']

        build_sequence = []
        self._getBuildSequence(source, build_sequence)
        return build_sequence

    def _getBuildSequence(self, source, build_sequence, reference=None):
        """
        Recursively finds out the dependencies of the given source file
        """
        self._logger.debug("Checking build sequence for %s", source)
        for library, unit in self._resolveRelativeNames(source):
            # Get a list of source files that contains this design unit
            dependencies_list = self._config.discoverSourceDependencies(
                unit, library)

            if not dependencies_list:
                continue
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
                return removeDuplicates(build_sequence)

            if dependency not in build_sequence:
                self._getBuildSequence(dependency, reference=source,
                                       build_sequence=build_sequence)

            if dependency not in build_sequence:
                build_sequence.append(dependency)

        build_sequence = removeDuplicates(build_sequence)

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

        self._logger.info("Building '%s', batch_mode = %s",
                          str(path), batch_mode)

        build_sequence = self.getBuildSequence(source)

        self._logger.debug("Compilation build_sequence is:\n%s",
                           "\n".join([x.filename for x in build_sequence]))

        for _source in build_sequence:
            _flags = self._config.getBuildFlags(_source.filename,
                                                batch_mode=False)

            _ = self._buildAndHandleRebuilds(_source, forced=False,
                                             flags=_flags)

        source_records = self._buildAndHandleRebuilds(source, forced=True,
                                                      flags=flags)
        return self._sortBuildMessages(source_records + remarks)

    def _buildAndHandleRebuilds(self, source, *args, **kwargs):
        """
        Builds the given source and handle any files that might require
        rebuilding until there is nothing to rebuild.
        The number of iteractions is fixed in 10.
        """
        # Limit the amount of calls to rebuild the same file to avoid
        # hanging the server
        for _ in range(self._MAX_REBUILD_ATTEMPTS):
            records, rebuilds = self.builder.build(source, *args, **kwargs)
            if rebuilds:
                self._handleRebuilds(rebuilds, source)
            else:
                return records

        self._handleUiError("Unable to build '%s' after %d attempts" %
                            (source, self._MAX_REBUILD_ATTEMPTS))

    def _handleRebuilds(self, rebuilds, source=None):
        """
        Resolves hints found in the rebuild list into source objects
        and rebuild them
        """
        if source is not None:
            self._logger.info("Building '%s' triggers rebuilding: %s",
                              source, ", ".join([str(x) for x in rebuilds]))
        for rebuild in rebuilds:
            self._logger.debug("Rebuild hint: '%s'", rebuild)
            if 'rebuild_path' in rebuild:
                self._getBuilderMessages(rebuild['rebuild_path'],
                                         batch_mode=True)
            else:
                unit_name = rebuild.get('unit_name', None)
                library_name = rebuild.get('library_name', None)
                unit_type = rebuild.get('unit_type', None)


                if library_name is not None:
                    rebuild_sources = self._config.findSourcesByDesignUnit(
                        unit_name, library_name)
                elif unit_type is not None:
                    library = source.getMatchingLibrary(
                        unit_type, unit_name)
                    rebuild_sources = self._config.findSourcesByDesignUnit(
                        unit_name, library)
                else:  # pragma: no cover
                    assert False, ', '.join([x.filename for x in rebuild_sources])

                for rebuild_source in rebuild_sources:
                    self._getBuilderMessages(rebuild_source.abspath,
                                             batch_mode=True)

    def _isBuilderCallable(self):
        """
        Checks if all preconditions for calling the builder have been
        met
        """
        if self._config.filename is None:
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

        if self._USE_THREADS:
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

    def onBufferVisit(self, path):
        """
        Runs tasks whenever a buffer is being visited. Currently this
        means caching the build sequence before the file is actually
        checked, so the overall wait time is reduced
        """
        try:
            source = self._config.getSourceByPath(path)
        except KeyError:
            return
        key = 'getBuildSequence'
        sequence = self.getBuildSequence(source)
        try:
            cache_mtime = max([x.getmtime() for x in sequence])
        except ValueError:
            self._logger.exception("Failed to get cache mtime for '%s'", path)
        self._cache[key] = {
            'path': path,
            'sequence': sequence,
            'cache_mtime': cache_mtime}

    def onBufferLeave(self, _):
        """
        Runs actions when leaving a buffer.
        """
        pass

