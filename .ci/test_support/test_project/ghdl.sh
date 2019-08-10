#!/usr/bin/env bash
set -x
rm -rf .build/

mkdir -p .build/

mkdir -p .build/basic_library
mkdir -p .build/another_library

ghdl -i --work=basic_library --workdir=.build/basic_library basic_library/*.vhd
ghdl -i --work=another_library --workdir=.build/another_library another_library/*.vhd

# ghdl -e --workdir=.build/basic_library very_common_pkg
# ghdl -e --workdir=.build/basic_library package_with_constants
# ghdl -e --workdir=.build/basic_library package_with_functions
ghdl -a --ieee=synopsys --work=basic_library --workdir=.build/basic_library basic_library/clock_divider.vhd
ghdl -e --ieee=synopsys --work=basic_library --workdir=.build/basic_library clock_divider

# ghdl -m --workdir=.build/another_library foo

# vhdl basic_library basic_library/very_common_pkg
# vhdl basic_library basic_library/package_with_constants
# vhdl basic_library basic_library/clock_divider
# vhdl another_library another_library/foo.vhd  -2008
# vhdl basic_library basic_library/package_with_functions.vhd 
