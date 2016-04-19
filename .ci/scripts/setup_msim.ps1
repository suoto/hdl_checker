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

if (!(Test-Path "$env:CACHE_PATH\\modelsim.exe")) {
    write-host "Downloading $env:BUILDER_NAME from $env:URL"
    cmd /c "curl -fsS -o `"$env:CACHE_PATH\\modelsim.exe`" `"$env:URL`""
    write-host "Download finished"
}

if (!(Test-Path "$env:BUILDER_PATH")) {
    write-host "Installing $env:BUILDER_NAME to $env:LOCALAPPDATA"
    "$env:CACHE_PATH\\modelsim.exe --mode unattended --modelsim_edition modelsim_ase --installdir $env:LOCALAPPDATA"
    write-host "Testing installation"
    cmd /c "$env:BUILDER_PATH\\vcom -version"
    write-host "Done here"
}

