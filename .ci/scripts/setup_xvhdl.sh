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

CACHE_DIR="${HOME}/cache/"

INSTALLATION_DIR="${HOME}/builders/"

mkdir -p "${CACHE_DIR}"
mkdir -p "${INSTALLATION_DIR}"

XVHDL_TGZ="${CACHE_DIR}/xvhdl.tar.bz2"

if [ ! -f "${XVHDL_TGZ}.gpg" -a -n "${XVHDL_URL}" ]; then
  trap "rm -f -- '$PASS_FILE'" EXIT
  wget --no-check-certificate --quiet "${XVHDL_URL}" -O "${XVHDL_TGZ}.gpg"
  trap - EXIT
fi

echo "==============================="

if [ ! -f "${XVHDL_TGZ}" ]; then
  # --------
  # Save the passphrase to a file so we don't echo it in the logs
  PASS_FILE=$(tempfile)
  trap "rm -f -- '$PASS_FILE'" EXIT
  set +x
  if [ ! -z "$PASS" ]; then
    echo "$PASS" >> "$PASS_FILE"
  else
    rm "$PASS_FILE"
    trap - EXIT
  fi
  set -x
  # --------

  gpg --batch --passphrase-fd 0 "${XVHDL_TGZ}.gpg" < "$PASS_FILE"

fi

ls -ltra "${CACHE_DIR}"

if [ ! -d "${INSTALLATION_DIR}/xvhdl/bin" ]; then
  tar xvf "${XVHDL_TGZ}" --directory "${INSTALLATION_DIR}"
fi

rm "${XVHDL_TGZ}"

"${INSTALLATION_DIR}/xvhdl/bin/xvhdl" --version

