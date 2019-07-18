#!/usr/bin/env bash
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

set -x
set +e

URL=http://downloads.sourceforge.net/project/ghdl-updates/Builds/ghdl-0.33/ghdl-0.33-x86_64-linux.tgz
CACHE_DIR="${HOME}/cache/"
GHDL_TAR_GZ="${CACHE_DIR}/ghdl.tar.gz"
INSTALLATION_DIR="${HOME}/builders/ghdl/"

mkdir -p "${CACHE_DIR}"
mkdir -p "${INSTALLATION_DIR}"
# CWD=$(pwd)

if [ ! -f "${GHDL_TAR_GZ}" ]; then
  wget ${URL} -O "${GHDL_TAR_GZ}" --quiet
fi

if [ ! -d "${INSTALLATION_DIR}/bin" ]; then
  mkdir -p "${INSTALLATION_DIR}"
  tar zxvf "${GHDL_TAR_GZ}" --directory "${INSTALLATION_DIR}"
fi

"${INSTALLATION_DIR}"/bin/ghdl --version

