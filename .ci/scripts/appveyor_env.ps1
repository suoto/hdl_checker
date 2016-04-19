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

write-host "Creating AppVeyor-like environment variables"
$env:APPVEYOR_BUILD_FOLDER=$(get-location)
$env:CI_WORK_PATH="$env:USERPROFILE\\ci"

$env:CACHE_PATH="$env:CI_WORK_PATH\\cache"
$env:HDLCC_CI="$env:CI_WORK_PATH\\hdlcc_ci"
$env:ARCH="32"
$env:PATH="C:\Program Files\7-zip;$env:PATH"

if (!(Test-Path "$env:CI_WORK_PATH")) {
    cmd /c "mkdir `"$env:CI_WORK_PATH`""
}

