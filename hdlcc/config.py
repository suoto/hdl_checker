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

import logging

class Config(object):
    "Store HDL Code Checker configuration"
    is_toolchain = None
    thread_limit = 20

    # Only for running in standlone mode
    log_level = logging.DEBUG
    log_format = "%(levelname)-8s || %(name)s || %(message)s"

    show_only_current_file = False

    # When building a specific source, we can build its first level
    # dependencies and display their errors and/or warnings. Notice
    # that no dependency tracking will be done when none of them
    # are enabled!
    show_reverse_dependencies_errors = True
    show_reverse_dependencies_warnings = False
    max_reverse_dependency_sources = 20

    # When we find errors, we can cache them to avoid recompiling a
    # specific source file or consider the file as changed. Notice this
    # is changed from True to False, the errors reported for a given
    # source will be the cached ontes until we force rebuilding it
    cache_error_messages = True

