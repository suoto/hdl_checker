#!/usr/bin/env bash

set -x

git clean -fd
# git submodule update
git submodule foreach git clean -fd
coverage run -m nose2 "$@"
coverage combine
coverage html
# coverage report


