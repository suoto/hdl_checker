# This file is part of vim-hdl.
#
# Copyright (c) 2015-2019 Andre Souto
#
# vim-hdl is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# vim-hdl is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with vim-hdl.  If not, see <http://www.gnu.org/licenses/>.
"Base class for creating a project file"

import abc
import logging
import os
import os.path as p
import time

import vim  # pylint: disable=import-error
import vimhdl
from hdlcc.utils import UnknownTypeExtension, getFileType, isFileReadable

_SOURCE_EXTENSIONS = 'vhdl', 'sv', 'v'
_HEADER_EXTENSIONS = 'vh', 'svh'

_DEFAULT_LIBRARY_NAME = {
        'vhdl': 'lib',
        'verilog': 'lib',
        'systemverilog': 'lib'}

class ProjectFileCreator:
    """
    Base class implementing creation of config file semi automatically
    """

    __metaclass__ = abc.ABCMeta
    # If the user hasn't already set vimhdl_conf_file in g: or b:, we'll use
    # this instead
    _default_conf_filename = 'vimhdl.prj'

    _preface = """\
# This is the resulting project file, please review and save when done. The
# g:vimhdl_conf_file variable has been temporarily changed to point to this
# file should you wish to open HDL files and test the results. When finished,
# close this buffer; you''ll be prompted to either use this file or revert to
# the original one.
#
# ---- Everything up to this line will be automatically removed ----
""".splitlines()

    def __init__(self, builders, cwd):
        """
        Arguments:
            - builders: list of builder names that the server has reported as
                        working
            - cwd: current working directory. This will influence where the
                   resulting file is saved
        """
        self._builders = builders
        self._cwd = cwd
        self._logger = logging.getLogger(self.__class__.__name__)
        self._sources = set()
        self._include_paths = {'verilog': set(),
                               'systemverilog': set()}

        self._project_file = vimhdl.vim_helpers.getProjectFile() or \
                ProjectFileCreator._default_conf_filename

        self._backup_file = p.join(
            p.dirname(self._project_file),
            '.' + p.basename(self._project_file) + '.backup')

    open_after_running = property(lambda self: True, doc="""
        open_after_running enables or disables opening the resulting project
        file after the creator has run.""")

    def _addSource(self, path, flags, library=None):
        """
        Add a source to project. 'flags' and 'library' are only used for
        regular sources and not for header files (files ending in .vh or .svh)
        """
        self._logger.debug("Adding path %s (flgas=%s, library=%s)", path,
                           flags, library)

        if p.basename(path).split('.')[-1].lower() in ('vh', 'svh'):
            file_type = getFileType(path)
            if file_type in ('verilog', 'systemverilog'):
                self._include_paths[file_type].add(p.dirname(path))
        else:
            self._sources.add((path, ' '.join([str(x) for x in flags]),
                               library))

    @abc.abstractmethod
    def _populate(self):
        """
        Method that will be called for generating the project file contets and
        should be implemented by child classes
        """

    @abc.abstractmethod
    def _getPreferredBuilder(self):
        """
        Method should be overridden by child classes to express the preferred
        builder
        """

    def _formatIncludePaths(self, paths):
        """
        Format a list of paths to be used as flags by the builder. (Still needs
        a bit of thought, ideally only the builder know how to do this)
        """
        builder = self._getPreferredBuilder()

        if builder == 'msim':
            return ' '.join(['+incdir+%s' % path for path in paths])

        return ''

    def run(self):
        """
        Generates the project file by running the child class' algorithm and
        opens up
        """
        # Disable auto commands if any to avoid cleaning up a file we're not
        # supposed to
        vim.command('autocmd! vimhdl BufUnload')

        # In case no project file was set and we used the default one
        if 'vimhdl_conf_file' not in vim.vars:
            vim.vars['vimhdl_conf_file'] = self._project_file

        # Backup
        if p.exists(self._project_file):
            self._logger.info("Backing up %s to %s", self._project_file,
                              self._backup_file)
            os.rename(self._project_file, self._backup_file)

        try:
            self._writeGeneratedFile()
        except:
            self._logger.exception("Error running auto project creation, "
                                   "restoring backup")
            os.rename(self._backup_file, self._project_file)
            raise

        if self.open_after_running:
            # Need to open the resulting file and then setup auto commands to
            # avoid triggering them when loading / unloading the new buffer
            self._openResultingFileForEdit()
            self._setupAutocmds()

    def _writeGeneratedFile(self):
        """
        Runs the child class algorithm to populate the parent object with the
        project info and writes the result to the project file
        """
        self._logger.info("Running creation helpers")

        self._populate()
        contents = []

        # Don't include preface if not opening for edits later on
        if self.open_after_running:
            contents += ProjectFileCreator._preface

        contents += ['# Generated on %s' % time.ctime(),
                     '# Files found: %s' % len(self._sources),
                     '# Available builders: %s' % ', '.join(self._builders)]

        builder = self._getPreferredBuilder()
        if builder in self._builders:
            contents += ['builder = %s' % builder]

        # Add include paths if they exists. Need to iterate sorted keys to
        # generate results always in the same order
        for lang in sorted(self._include_paths.keys()):
            paths = sorted(self._include_paths[lang])
            include_paths = self._formatIncludePaths(paths)
            if include_paths:
                contents += ['global_build_flags[%s] = %s' % (lang, include_paths)]

        if self._include_paths:
            contents += ['']

        # Add sources
        sources = []

        for path, flags, library in self._sources:
            file_type = getFileType(path)
            sources.append((file_type, library, path, flags))

        sources.sort(key=lambda x: x[2])

        for file_type, library, path, flags in sources:
            contents += ['{0} {1} {2} {3}'.format(file_type, library, path,
                                                  flags)]

        contents += ['', '# vim: filetype=vimhdl']

        self._logger.info("Resulting file has %d lines", len(contents))

        open(self._project_file, 'w').write('\n'.join(contents))

    def _setupAutocmds(self):
        """
        Creates an autocmd for the specified file only
        """
        self._logger.debug("Setting up auto cmds for %s", self._project_file)
        # Create hook to remove preface text when closing the file
        vim.command('augroup vimhdl')
        vim.command('autocmd BufUnload %s :call s:onVimhdlTempQuit()' %
                    self._project_file)
        vim.command('augroup END')

    def _openResultingFileForEdit(self):
        """
        Opens the resulting conf file for editing so the user can tweak and
        test
        """
        self._logger.debug("Opening resulting file for edition")
        # If the current buffer is already pointing to the project file, reuse
        # it
        if not p.exists(vim.current.buffer.name) or \
                p.samefile(vim.current.buffer.name, self._project_file):
            vim.command('edit! %s' % self._project_file)
        else:
            vim.command('vsplit %s' % self._project_file)

        vim.current.buffer.vars['is_vimhdl_generated'] = True
        vim.command('set filetype=vimhdl')

    def onVimhdlTempQuit(self):
        """
        Callback for closing the generated project file to remove the preface
        from the buffer contents
        """
        # Don't touch files created by the user of files where the preface has
        # already been (presumably) taken out
        if not vim.current.buffer.vars.get('is_vimhdl_generated', False):
            return

        # No pop on Vim's RemoteMap dictionary
        del vim.current.buffer.vars['is_vimhdl_generated']
        # No need to call this again
        vim.command('autocmd! vimhdl BufUnload')

        # Search for the last line we said we'd remove
        lnum = 0
        for lnum, line in enumerate(vim.current.buffer):
            if 'Everything up to this line will be automatically removed' in line:
                self._logger.debug("Breaing at line %d", lnum)
                break

        # Remove line not found
        if not lnum:
            return

        # Update and save
        vim.current.buffer[ : ] = list(vim.current.buffer)[lnum + 1 : ]
        vim.command('write!')

class FindProjectFiles(ProjectFileCreator):
    """
    Implementation of ProjectFileCreator that searches for paths on a given
    set of paths recursively
    """
    def __init__(self, builders, cwd, paths):
        super(FindProjectFiles, self).__init__(builders, cwd)
        self._logger.debug("Search paths: %s", paths)
        self._paths = paths
        self._valid_extensions = tuple(list(_SOURCE_EXTENSIONS) +
                                       list(_HEADER_EXTENSIONS))

    def _getPreferredBuilder(self):
        if 'msim' in self._builders:
            return 'msim'
        if 'ghdl' in self._builders:
            return 'ghdl'
        return 'xvhdl'

    def _getCompilerFlags(self, path):
        """
        Returns file specific compiler flags
        """
        if self._getPreferredBuilder() != 'msim':
            return []

        flags = []
        # Testbenches are usually more relaxed, so set VHDL 2008
        if (p.basename(path).split('.')[0].endswith('_tb') or
                p.basename(path).startswith('tb_')):
            flags += ['-2008']

        return flags

    def _getLibrary(self, path):  # pylint: disable=no-self-use
        """
        Returns the library name given the path. On this implementation this
        returns a default name; child classes can override this to provide
        specific names (say the library name is embedded on the path itself or
        on the file's contents)
        """
        extension = getFileType(path)
        return _DEFAULT_LIBRARY_NAME[extension]

    def _findSources(self):
        """
        Iterates over the paths and searches for relevant files by extension.
        """
        for path in self._paths:
            for dirpath, _, filenames in os.walk(path):
                for filename in filenames:
                    path = p.join(dirpath, filename)

                    if not p.isfile(path):
                        continue

                    try:
                        # getFileType will fail if the file's extension is not
                        # valid (one of '.vhd', '.vhdl', '.v', '.vh', '.sv',
                        # '.svh')
                        getFileType(filename)
                    except UnknownTypeExtension:
                        continue

                    if isFileReadable(path):
                        yield path

    def _populate(self):
        for path in self._findSources():
            self._addSource(path, flags=self._getCompilerFlags(path),
                            library=self._getLibrary(path))
