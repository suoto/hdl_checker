#!/usr/bin/env python

import os
import os.path as p

_CLONE_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')

def main():
    grlib_path = p.join(_CLONE_PATH, 'grlib')
    if not p.isdir(grlib_path):
        os.system('git clone https://github.com/suoto/grlib {} --depth 1'.format(grlib_path))

main()
