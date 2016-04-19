# This file is part of HDL Code Checker.

# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.


# Create variables defined on Appveyor YAML file
.ci\\scripts\\appveyor_env.ps1

if (!$?) {write-error "Something went wrong, exiting"; exit -1}

$env:BUILDER_NAME="ghdl"
$env:ARCH="32"
$env:URL="http://pilotfiber.dl.sourceforge.net/project/ghdl-updates/Builds/ghdl-0.31/Windows/ghdl-0.31-mcode-win32.zip"
$env:INSTALL_DIR="$env:CI_WORK_PATH\\ghdl-0.31-mcode-win32"
$env:BUILDER_PATH="$env:INSTALL_DIR\\bin"

if ($env:APPVEYOR -ne "True") {
    write-host "Setting up virtualenv"
    $VENV_PATH="$env:CI_WORK_PATH\\venv_$env:BUILDER_NAME\\"
    if (!(Test-Path $VENV_PATH)) {
      virtualenv $VENV_PATH
      . "$VENV_PATH\\Scripts\\activate.ps1"
    }
}

if (!$?) {write-error "Something went wrong, exiting"; exit -1}

write-host "Setting up environment"
. .ci\\scripts\\setup_env.ps1
if (!$?) {write-error "Something went wrong, exiting"; exit -1}

write-host "Running tests"
. .ci\\scripts\\run_tests.ps1
if (!$?) {write-error "Something went wrong, exiting"; exit -1}

deactivate

