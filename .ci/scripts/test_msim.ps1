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

$env:BUILDER_NAME="msim"
$env:BUILDER_PATH="$env:LOCALAPPDATA\\modelsim_ase\\win32aloem"
$env:ARCH="32"
$env:URL="http://download.altera.com/akdlm/software/acdsinst/15.1/185/ib_installers/ModelSimSetup-15.1.0.185-windows.exe"

if ($env:APPVEYOR -ne "True") {
    $VENV_PATH="$env:LOCALAPPDATA\\venv_$env:BUILDER_NAME\\"
    if (Test-Path $VENV_PATH) {
        rmdir /s /q $VENV_PATH
    }
    virtualenv $VENV_PATH
    . "$VENV_PATH\\Scripts\\activate.ps1"
}

write-host "Setting up environment"
.ci\\scripts\\setup_env.ps1
write-host "Running tests"
.ci\\scripts\\run_tests.ps1

deactivate

