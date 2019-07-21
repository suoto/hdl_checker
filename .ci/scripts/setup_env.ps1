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

write-host "Configured builder is $env:BUILDER"

if ($env:ARCH -eq 32) {
    $env:python_path = "C:\Python$env:PYTHON_VERSION"
} else {
    $env:python_path = "C:\Python$env:PYTHON_VERSION-x64"
}

$env:PATH="$env:python_path;$env:python_path\Scripts;$env:PATH"

Start-Process "git" -RedirectStandardError git.log -Wait -NoNewWindow -ArgumentList `
    "submodule update --init --recursive"
get-content git.log

if ($env:APPVEYOR -eq "True") {
    appveyor DownloadFile https://bootstrap.pypa.io/get-pip.py
    if (!$?) {write-error "Error while downloading get-pip.py, exiting"; exit -1}
    "$env:PYTHON\\python.exe get-pip.py"
}


if ("$env:BUILDER" -eq "msim") {
    echo "Installing MSIM"
    . "$env:APPVEYOR_BUILD_FOLDER\\.ci\\scripts\\setup_msim.ps1"
    if (!$?) {write-error "Error while installing ModelSim"; exit -1}
} elseif ("$env:BUILDER" -eq "ghdl") {
    echo "Installing GHDL"
    . "$env:APPVEYOR_BUILD_FOLDER\\.ci\\scripts\\setup_ghdl.ps1"
    if (!$?) {write-error "Error while installing GHDL"; exit -1}
} else {
    echo "No builder selected"
}

write-host "Arch is $env:ARCH, Python selected is $env:python_path"

