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

import hdlcc.builders
import hdlcc.exceptions
from hdlcc.builders import Fallback
from hdlcc.config_parser import ConfigParser
from hdlcc.diagnostics import (DependencyNotUnique, DiagType,
                               PathNotInProjectFile)
from hdlcc.parsers import VerilogParser, VhdlParser
from hdlcc.serialization import StateEncoder, jsonObjectHook
from hdlcc.static_check import getStaticMessages
from hdlcc.utils import (getCachePath, getFileType, removeDirIfExists,
                         removeDuplicates, removeIfExists)

CACHE_NAME = 'cache.json'

_logger = logging.getLogger('build messages')


class HdlCodeCheckerBase(object):  # pylint: disable=useless-object-inheritance
    """
    HDL Code Checker project builder class
    """

    _USE_THREADS = True
    _MAX_REBUILD_ATTEMPTS = 20

    __metaclass__ = abc.ABCMeta

    def __init__(self, project_file=None):
        self._start_dir = p.abspath(os.curdir)
        self._logger = logging.getLogger(__name__)
        self._build_sequence_cache = {}
        self._outstanding_diags = set()

        self.project_file = project_file

        self.config_parser = ConfigParser(self.project_file)
        self.builder = Fallback(self._getCacheDirectory())

        self._recoverCacheIfPossible()
        self._setupEnvIfNeeded()
        self._saveCache()

    def _getCacheDirectory(self):
        cache = p.abspath('.' if self.project_file is None else self.project_file)
        return p.join(getCachePath(), cache.replace(p.sep, '_'))

    def _getCacheFilename(self):
        """
        Returns the cache file name for a given project file
        """
        cache_dir = self._getCacheDirectory()
        return p.join(cache_dir, CACHE_NAME)

    def _saveCache(self):
        """
        Dumps project object to a file to recover its state later
        """
        cache_fname = self._getCacheFilename()

        state = {'_logger': {'name': self._logger.name,
                             'level': self._logger.level},
                 'builder': self.builder,
                 'config_parser': self.config_parser}

        self._logger.debug("Saving state to '%s'", cache_fname)
        if not p.exists(p.dirname(cache_fname)):
            os.makedirs(p.dirname(cache_fname))
        json.dump(state, open(cache_fname, 'w'), indent=True, cls=StateEncoder)

    def _recoverCacheIfPossible(self):
        """
        Tries to recover cached info for the given project_file. If
        something goes wrong, assume the cache is invalid and return
        nothing. Otherwise, return the cached object
        """
        cache_fname = self._getCacheFilename()

        try:
            cache = json.load(open(cache_fname, 'r'), object_hook=jsonObjectHook)
            self._handleUiInfo("Recovered cache from '{}'".format(cache_fname))
        except IOError:
            self._logger.debug("Couldn't read cache file %s, skipping recovery",
                               cache_fname)
            return
        except ValueError as exception:
            self._handleUiWarning(
                "Unable to recover cache from '{}': {}".format(cache_fname,
                                                               str(exception)))

            self._logger.warning("Unable to recover cache from '%s': %s",
                                 cache_fname, traceback.format_exc())
            return

        self._setState(cache)
        self.builder.checkEnvironment()

    def _setupEnvIfNeeded(self):
        """
        Updates or creates the environment, which includes checking
        if the configuration file should be parsed and creating the
        appropriate builder objects
        """
        try:
            # If still using Fallback builder, check if the config has a
            # different one
            if isinstance(self.builder, Fallback):
                builder_name = self.config_parser.getBuilder()
                builder_class = hdlcc.builders.getBuilderByName(builder_name)
                if builder_class is Fallback:
                    return

                cache_dir = self._getCacheDirectory()
                try:
                    os.makedirs(cache_dir)
                except OSError:
                    pass

                self.builder = builder_class(cache_dir)

                self._logger.info("Selected builder is '%s'",
                                  self.builder.builder_name)
        except hdlcc.exceptions.SanityCheckError as exc:
            self._handleUiError("Failed to create builder '%s'" % exc.builder)
            self.builder = Fallback(self._getCacheDirectory())

        assert self.builder is not None

    def clean(self):
        """
        Clean up generated files
        """
        self._logger.debug("Cleaning up project")
        removeIfExists(self._getCacheFilename())
        removeDirIfExists(self._getCacheDirectory())

        del self.config_parser
        del self.builder
        self.config_parser = ConfigParser(self.project_file)
        self.builder = Fallback(self._getCacheDirectory())

    def _setState(self, state):
        """
        Serializer load implementation
        """
        self._logger = logging.getLogger(state['_logger']['name'])
        self._logger.setLevel(state['_logger']['level'])
        del state['_logger']

        self.config_parser = state['config_parser']

        builder_name = self.config_parser.getBuilder()
        self._logger.debug("Recovered builder is '%s'", builder_name)
        #  builder_class = hdlcc.builders.getBuilderByName(builder_name)
        #  self.builder = builder_class.recoverFromState(state['builder'])
        self.builder = state['builder']

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

    def getSourceByPath(self, path):
        """
        Get the source object, flags and any additional info to be displayed
        """
        source = None
        remarks = []

        try:
            source = self.config_parser.getSourceByPath(path)
        except KeyError:
            pass

        # If the source file was not found on the configuration file, add this
        # as a remark.
        # Also, create a source parser object with some library so the user can
        # at least have some info on the source
        if source is None:
            if not isinstance(self.builder, Fallback):
                remarks += [PathNotInProjectFile(p.abspath(path)), ]

            self._logger.info("Path %s not found in the project file",
                              p.abspath(path))
            cls = VhdlParser if getFileType(path) == 'vhdl' else VerilogParser
            source = cls(path, library='undefined')

        return source, remarks

    def _resolveRelativeNames(self, source):
        """
        Translate raw dependency list parsed from a given source to the
        project name space
        """
        for dependency in source.getDependencies():
            if dependency.library in self.builder.getBuiltinLibraries():
                continue
            if dependency.name == 'all':
                continue
            if (dependency.library == source.library and \
                    dependency.name in [x['name'] for x in source.getDesignUnits()]):
                continue
            yield dependency

    @staticmethod
    def _sortBuildMessages(diagnostics):
        """
        Sorts a given set of build records
        """
        return sorted(diagnostics, key=lambda x: \
                (x.severity, x.line_number or 0, x.error_code or ''))

    def updateBuildSequenceCache(self, source):
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
                timestamp = max([x.getmtime() for x in build_sequence])
            else:
                timestamp = 0
            self._build_sequence_cache[key] = {
                'sequence': build_sequence,
                'timestamp': timestamp}
        else:
            cached_sequence = self._build_sequence_cache[key]['sequence']
            cached_timestamp = self._build_sequence_cache[key]['timestamp']
            if cached_sequence:
                current_timestamp = max(
                    max({x.getmtime() for x in cached_sequence if x}),
                    source.getmtime() or 0)
            else:
                current_timestamp = 0

            if current_timestamp > cached_timestamp:
                self._logger.debug("Timestamp change, rescanning build "
                                   "sequence")
                self._build_sequence_cache[key] = {
                    'sequence': self.getBuildSequence(source),
                    'timestamp': current_timestamp}

        return self._build_sequence_cache[key]['sequence']

    def _reportDependencyNotUnique(self, non_resolved_dependency, actual, choices):
        """
        Reports a dependency failed to be resolved due to multiple files
        defining the required design unit
        """
        locations = non_resolved_dependency.locations or \
                    (non_resolved_dependency.filename, 1, None)

        for filename, line_number, column_number in locations:
            self._outstanding_diags.add(
                DependencyNotUnique(
                    filename=filename,
                    line_number=line_number,
                    column_number=column_number,
                    design_unit='{}.{}'.format(non_resolved_dependency.library,
                                               non_resolved_dependency.name),
                    actual=actual.filename,
                    choices=list(choices)))


    def getBuildSequence(self, source):
        build_sequence = []
        self._resolveBuildSequence(source, build_sequence)
        return build_sequence

    def _resolveBuildSequence(self, source, build_sequence, reference=None):
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
            dependencies_list = self.config_parser.discoverSourceDependencies(
                dependency.name, dependency.library, case_sensitive=source.filetype != 'vhdl')

            if not dependencies_list:
                continue
            selected_dependency = dependencies_list[0]
            dependencies_list = dependencies_list[1:]

            # If we found more than a single file, then multiple files have the
            # same entity or package name and we failed to identify the real
            # file
            if dependencies_list:
                _logger.warning("Dependency %s (%s)", dependency, type(dependency))
                self._reportDependencyNotUnique(
                    non_resolved_dependency=dependency,
                    actual=selected_dependency,
                    choices=dependencies_list)

            # Check if we found out that a dependency is the same we
            # found in the previous call to break the circular loop
            if selected_dependency == reference:
                build_sequence = removeDuplicates(build_sequence)
                return

            if selected_dependency not in build_sequence:
                self._resolveBuildSequence(selected_dependency, reference=source,
                                           build_sequence=build_sequence)

            if selected_dependency not in build_sequence:
                build_sequence.append(selected_dependency)

        build_sequence = removeDuplicates(build_sequence)

    def _getBuilderMessages(self, source, batch_mode=False):
        """
        Builds the given source taking care of recursively building its
        dependencies first
        """
        try:
            flags = self.config_parser.getBuildFlags(source.filename, batch_mode)
        except KeyError:
            flags = []

        self._logger.info("Building '%s', batch_mode = %s",
                          str(source.filename), batch_mode)

        build_sequence = self.updateBuildSequenceCache(source)

        self._logger.debug("Compilation build_sequence is:\n%s",
                           "\n".join([x.filename for x in build_sequence]))

        records = set()
        for _source in build_sequence:
            _flags = self.config_parser.getBuildFlags(_source.filename,
                                                      batch_mode=False)

            dep_records = self._buildAndHandleRebuilds(_source, forced=False,
                                                       flags=_flags)

            for record in dep_records:
                if record.filename is None:
                    continue
                if record.severity in (DiagType.ERROR, ):
                    records.add(record)

        records.update(self._buildAndHandleRebuilds(source, forced=True,
                                                    flags=flags))

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

        self._handleUiError("Unable to build '%s' after %d attempts" %
                            (source.filename, self._MAX_REBUILD_ATTEMPTS))

        return {}

    def _handleRebuilds(self, rebuilds, source):
        """
        Resolves hints found in the rebuild list into source objects
        and rebuild them
        """
        self._logger.info("Building '%s' triggers rebuilding: %s",
                          source, ", ".join([str(x) for x in rebuilds]))
        for rebuild in rebuilds:
            self._logger.debug("Rebuild hint: '%s'", rebuild)
            if 'rebuild_path' in rebuild:
                rebuild_sources = [self.getSourceByPath(rebuild['rebuild_path'])[0]]
            else:
                unit_name = rebuild.get('unit_name', None)
                library_name = rebuild.get('library_name', None)
                unit_type = rebuild.get('unit_type', None)

                if library_name is not None:
                    rebuild_sources = self.config_parser.findSourcesByDesignUnit(
                        unit_name, library_name)
                elif unit_type is not None:
                    library = source.getMatchingLibrary(
                        unit_type, unit_name)
                    rebuild_sources = self.config_parser.findSourcesByDesignUnit(
                        unit_name, library)
                else:  # pragma: no cover
                    assert False, "Don't know how to handle %s" % rebuild

            for rebuild_source in rebuild_sources:
                self._getBuilderMessages(rebuild_source,
                                         batch_mode=True)

    def _isBuilderCallable(self):
        """
        Checks if all preconditions for calling the builder have been
        met
        """
        if self.config_parser.filename is None:
            return False
        return True

    def getMessagesByPath(self, path, *args, **kwargs):
        """
        Returns the messages for the given path, including messages
        from the configured builder (if available) and static checks
        """
        self._setupEnvIfNeeded()

        source, remarks = self.getSourceByPath(path)
        return self._sortBuildMessages(
            self.getMessagesBySource(source, *args, **kwargs) + remarks)

    def getMessagesBySource(self, source, batch_mode=False):
        """
        Returns the messages for the given source, including messages
        from the configured builder (if available) and static checks
        Extra arguments are
        """
        self._setupEnvIfNeeded()
        self._outstanding_diags = set()

        records = []

        if self._USE_THREADS:
            pool = ThreadPool()

            static_check = pool.apply_async(
                getStaticMessages, args=(source.getRawSourceContent().split('\n'), ))

            if self._isBuilderCallable():
                builder_check = pool.apply_async(self._getBuilderMessages,
                                                 args=[source, batch_mode])
                records += builder_check.get()

            pool.close()
            pool.join()

            # Static messages don't take the path, only the text, so we need to
            # set add that to the diagnostic
            for record in static_check.get():
                record.filename = source.filename
                records += [record]

        else:  # pragma: no cover
            for record in getStaticMessages(source.getRawSourceContent().split('\n')):
                record.filename = source.filename
                records += [record]

            if self._isBuilderCallable():
                records += self._getBuilderMessages(source, batch_mode)

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
        return self.config_parser.getSources()

    def onBufferVisit(self, path):
        """
        Runs tasks whenever a buffer is being visited. Currently this
        means caching the build sequence before the file is actually
        checked, so the overall wait time is reduced
        """
        self._setupEnvIfNeeded()
        source, _ = self.getSourceByPath(path)
        self.updateBuildSequenceCache(source)
