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


# Create variables defined on Appveyor YAML file

# $TESTS=

# $TESTS=hdlcc.tests.test_builders
# $TESTS=hdlcc.tests.test_config_parser
# $TESTS=hdlcc.tests.test_persistency
# $TESTS=hdlcc.tests.test_project_builder
# $TESTS=hdlcc.tests.test_source_file
# $TESTS=hdlcc.tests.test_standalone
# $TESTS="hdlcc.tests.test_server_handlers"

# write-host "TESTS: $TESTS"

python "$env:APPVEYOR_BUILD_FOLDER\\.ci\\scripts\\run_tests.py" -vv `
    --log-capture -F

