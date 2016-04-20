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

write-host "HDLCC_CI=$env:HDLCC_CI"
write-host "Configured builder is $env:BUILDER_NAME"

$env:python = if ($env:arch -eq 32) { 'C:\Python27' } else
                                    { 'C:\Python27-x64' }

write-host "Python selected is $env:python"
$env:PATH="$env:PYTHON;$env:PYTHON\Scripts;$env:PATH"

&"git" "submodule" "update" "--init" "--recursive" "-q" "*>&1"

if (!(Test-Path $env:HDLCC_CI)) {
    &"git" "clone" "https://github.com/suoto/hdlcc_ci" "$env:HDLCC_CI" "--recursive" `
        "-q" "*>&1"
}

IF ($env:APPVEYOR -eq "True") {
    appveyor DownloadFile https://bootstrap.pypa.io/get-pip.py
    if (!$?) {write-error "Something went wrong, exiting"; exit -1}
    python get-pip.py
}

pip install -r requirements.txt
pip install git+https://github.com/suoto/rainbow_logging_handler
if (!$?) {write-error "Something went wrong, exiting"; exit -1}

if (!(Test-Path $env:CACHE_PATH)) {
    mkdir "$env:CACHE_PATH"
}

if ("$env:BUILDER_NAME" -eq "msim") {
    echo "Installing MSIM"
    . "$env:APPVEYOR_BUILD_FOLDER\\.ci\\scripts\\setup_msim.ps1"
    if (!$?) {write-error "Something went wrong, exiting"; exit -1}
} elseif ("$env:BUILDER_NAME" -eq "ghdl") {
    echo "Installing GHDL"
    . "$env:APPVEYOR_BUILD_FOLDER\\.ci\\scripts\\setup_ghdl.ps1"
    if (!$?) {write-error "Something went wrong, exiting"; exit -1}
} else {
    echo "No builder selected"
    exit -1
}

pip install -U -e $env:APPVEYOR_BUILD_FOLDER
if (!$?) {write-error "Something went wrong, exiting"; exit -1}

