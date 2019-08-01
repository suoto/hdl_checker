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

set -xe

echo "USER_ID=$USER_ID"
echo "GROUP_ID=$GROUP_ID"

addgroup "$USERNAME" --gid "$GROUP_ID"

adduser --disabled-password \
  --gid "$GROUP_ID"         \
  --uid "$USER_ID"          \
  --home "/home/$USERNAME" "$USERNAME"

exec su -l "$USERNAME" -c "ls -la $PWD && ls -la / && cd /hdlcc && tox -e local"

