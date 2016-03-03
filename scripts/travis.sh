#!/usr/bin/env bash

set -x
set +e

./run_tests.py $*

export BUILDER_NAME=msim
export BUILDER_PATH=${HOME}/builders/msim/modelsim_ase/linux/
export MODEL_TECH=${BUILDER_PATH}

./run_tests.py $*

export BUILDER_NAME=ghdl
export BUILDER_PATH=${HOME}/builders/ghdl/bin/
# export BUILDER_PATH=${HOME}/.local/bin/ghdl
./run_tests.py $*

coverage combine
coverage html

