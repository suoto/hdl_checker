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

set -e

PATH_TO_THIS_SCRIPT=$(readlink -f "$(dirname "$0")")

TOX_ARGS="$*"

# Need to add some variables so that uploading coverage from witihin the
# container to codecov works
docker run                                                      \
  --rm                                                          \
  --mount type=bind,source="$PATH_TO_THIS_SCRIPT",target=/hdlcc \
  --env USER_ID="$(id -u)"                                      \
  --env GROUP_ID="$(id -g)"                                     \
  --env TOX_ARGS="$TOX_ARGS"                                    \
  --env TOX_ARGS="$TOX_ARGS"                                    \
  --env USERNAME="$USER"                                        \
  suoto/hdlcc:latest
