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

VIRTUAL_ENV_DEST=~/dev/hdlcc_venv

ARGS=()

CLEAN=0

while [ -n "$1" ]; do
  if [ "$1" == "ghdl" ]; then
    GHDL=1
  elif [ "$1" == "msim" ]; then
    MSIM=1
  elif [ "$1" == "xvhdl" ]; then
    XVHDL=1
  elif [ "$1" == "fallback" ]; then
    FALLBACK=1
  elif [ "$1" == "pip" ]; then
    PIP=1
  elif [ "$1" == "clean" ]; then
    CLEAN=1
  elif [ "$1" == "standalone" ]; then
    STANDALONE=1
  else
    if [ "$1" == "-F" ]; then
      FAILFAST=1
    fi
    ARGS+=($1)
  fi

  shift
done


if [ -z "${GHDL}${MSIM}${FALLBACK}${STANDALONE}${XVHDL}" ]; then
  GHDL=1
  MSIM=1
  FALLBACK=1
  XVHDL=1
  STANDALONE=1
  PIP=1
fi

if [ "${CLEAN}" == "1" ]; then
  git clean -fdx && git submodule foreach --recursive git clean -fdx
  cd ${HDLCC_CI} && git reset HEAD --hard \
    && git clean -fdx && git submodule foreach --recursive git clean -fdx
  cd - || exit
fi

set -x
set +e

RESULT=0

if [ -z "${CI}" ]; then
  if [ -d "${VIRTUAL_ENV_DEST}" ]; then
    rm -rf ${VIRTUAL_ENV_DEST}
  fi

  virtualenv ${VIRTUAL_ENV_DEST}
  . ${VIRTUAL_ENV_DEST}/bin/activate

  pip install -r requirements.txt
fi

if [ -n "${PIP}" ]; then
  pip uninstall hdlcc -y
  if [ -n "${VIRTUAL_ENV}" ]; then
    pip install -e .
  else
    pip install -e . --user
  fi
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}

  hdlcc -h
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi


if [ "${RESULT}" != "0" ]; then
  exit ${RESULT}
fi

TEST_RUNNER="./.ci/scripts/run_tests.py"

if [ -n "${STANDALONE}" ]; then
  ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_config_parser hdlcc.tests.test_source_file
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${FALLBACK}" ]; then
  ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_code_checker_base hdlcc.tests.test_standalone
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${MSIM}" ]; then
  export BUILDER_NAME=msim
  export BUILDER_PATH=${HOME}/builders/msim/modelsim_ase/linux/

  ${TEST_RUNNER} "${ARGS[@]}"
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${XVHDL}" ]; then
  export BUILDER_NAME=xvhdl
  export BUILDER_PATH=${HOME}/builders/xvhdl/bin
  if [ ! -d "${BUILDER_PATH}" ]; then
    export BUILDER_PATH=${HOME}/dev/xvhdl/bin
  fi

  ${TEST_RUNNER} "${ARGS[@]}"
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${GHDL}" ]; then
  export BUILDER_NAME=ghdl
  if [ "${CI}" == "true" ]; then
    export BUILDER_PATH=${HOME}/builders/ghdl/bin/
  else
    if [ -f "${HOME}/.local/bin/ghdl" ]; then
      export BUILDER_PATH=${HOME}/.local/bin/ghdl
    else
      export BUILDER_PATH=${HOME}/builders/ghdl/bin/
    fi
  fi

  echo "BUILDER_PATH=$BUILDER_PATH"

  ${TEST_RUNNER} "${ARGS[@]}"
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

coverage combine
coverage html
# coverage report

[ -z "${CI}" ] && [ -n "${VIRTUAL_ENV}" ] && deactivate

exit "${RESULT}"

