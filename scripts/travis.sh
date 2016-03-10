#!/usr/bin/env bash
# This file is part of hdlcc.
#
# hdlcc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# hdlcc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with hdlcc.  If not, see <http://www.gnu.org/licenses/>.

ARGS=

while [ -n "$1" ]; do
  if [ "$1" == "ghdl" ]; then
    GHDL=1
  elif [ "$1" == "msim" ]; then
    MSIM=1
  elif [ "$1" == "fb" ]; then
    FALLBACK=1
  else
    ARGS+=" $1"
  fi

  shift
done

if [ -z "${GHDL}${MSIM}${FALLBACK}" ]; then
  GHDL=1
  MSIM=1
  FALLBACK=1
fi

git clean -fdx && git submodule foreach --recursive git clean -fdx

set -x
set +e

RESULT=0

if [ -n "${FALLBACK}" ]; then
  ./run_tests.py $ARGS
  RESULT=$(($? || ${RESULT}))
fi

if [ -n "${MSIM}" ]; then
  export BUILDER_NAME=msim
  export BUILDER_PATH=${HOME}/builders/msim/modelsim_ase/linux/

  ./run_tests.py $ARGS
  RESULT=$(($? || ${RESULT}))
fi

if [ -n "${GHDL}" ]; then
  export BUILDER_NAME=ghdl
  if [ "${TRAVIS}" == "true" ]; then
    export BUILDER_PATH=${HOME}/builders/ghdl/bin/
  else
    if [ -d "${HOME}/builders/ghdl/bin/" ]; then
      export BUILDER_PATH=${HOME}/builders/ghdl/bin/
    else
      export BUILDER_PATH=${HOME}/.local/bin/ghdl
    fi
  fi

  echo "BUILDER_PATH=$BUILDER_PATH"

  ./run_tests.py $ARGS
  RESULT=$(($? || ${RESULT}))
fi

coverage combine
coverage html

exit "${RESULT}"

