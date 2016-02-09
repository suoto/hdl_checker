#!/usr/bin/env bash

set -x

git clean -fdx
# git submodule update
git submodule foreach git clean -fdx
coverage run -m nose2 "$@"
coverage combine
coverage html
# coverage report


