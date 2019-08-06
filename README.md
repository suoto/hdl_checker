# HDL Code Checker

[![PyPI version](https://badge.fury.io/py/hdlcc.svg)](https://badge.fury.io/py/hdlcc)
[![Build Status](https://travis-ci.org/suoto/hdlcc.svg?branch=master)](https://travis-ci.org/suoto/hdlcc)
[![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdlcc/branch/master)
[![codecov](https://codecov.io/gh/suoto/hdlcc/branch/master/graph/badge.svg)](https://codecov.io/gh/suoto/hdlcc)
[![Code Climate](https://codeclimate.com/github/suoto/hdlcc/badges/gpa.svg)](https://codeclimate.com/github/suoto/hdlcc)
[![Join the chat at https://gitter.im/suoto/hdlcc](https://badges.gitter.im/suoto/hdlcc.svg)](https://gitter.im/suoto/hdlcc?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Analytics](https://ga-beacon.appspot.com/UA-68153177-4/hdlcc/README.md?pixel)](https://github.com/suoto/hdlcc)

HDL Code Checker provides a Python API that uses HDL compilers to build a project
and return info that can be used to populate syntax checkers. It works out mixed
language dependencies and compile ordering, interprets some compilers messages
and provides some (limited) static checks.

---

* [Installation](#installation)
* [Usage](#usage)
  * [Configuration File](#configuration-file)
  * [LSP server](#lsp-server)
  * [HTTP server](#http-server)
* [Testing](#testing)
* [Supported environments](#supported-environments)
  * [Supported systems](#supported-systems)
  * [Editor support](#editor-support)
  * [Supported third-party compilers](#supported-third-party-compilers)
* [Style checking](#style-checking)
* [Issues](#issues)
* [License](#license)

## Installation

```sh
pip install hdlcc
```

## Usage

HDL Code Checker server can be started via `hdlcc` command. Use `hdlcc --help`
for more info on how to use it.

```bash
$ hdlcc -h
usage: hdlcc [-h] [--host HOST] [--port PORT] [--lsp]
             [--attach-to-pid ATTACH_TO_PID] [--log-level LOG_LEVEL]
             [--log-stream LOG_STREAM] [--nocolor] [--stdout STDOUT]
             [--stderr STDERR] [--version]

optional arguments:
  -h, --help            show this help message and exit
  --host HOST           [HTTP] Host to serve
  --port PORT           [HTTP] Port to serve
  --lsp                 Starts the server in LSP mode. Defaults to false
  --attach-to-pid ATTACH_TO_PID
                        [HTTP, LSP] Stops the server if given PID is not
                        active
  --log-level LOG_LEVEL
                        [HTTP, LSP] Logging level
  --log-stream LOG_STREAM
                        [HTTP, LSP] Log file, defaults to stdout when in HTTP
                        or a temporary file named hdlcc_log_pid<PID>.log when
                        in LSP mode
  --nocolor             [HTTP, LSP] Enables colored logging (defaults to
                        false)
  --stdout STDOUT       [HTTP] File to redirect stdout to. Defaults to a
                        temporary file named hdlcc_stdout_pid<PID>.log
  --stderr STDERR       [HTTP] File to redirect stdout to. Defaults to a
                        temporary file named hdlcc_stderr_pid<PID>.log
  --version, -V         Prints hdlcc version and exit
```

### Configuration file

`hdlcc` requires a configuration file listing libraries, source files, build flags,
etc.

Basic syntax is

```bash
# This is a comment

[ builder = (msim|ghdl|xvhdl) ] # This is being deprecated
[ target_dir = PATH_TO_HDLCC_TEMPORARY_WORKING_DIR ] # This is being deprecated

[ global_build_flags[ (vhdl|verilog|systemverilog) ] = <language specific flags> ]

# Specifying sources
(vhdl|verilog|systemverilog) <library name> <path/to/source> [file specific flags]
```

An example project file could be:

```bash
# Specifying builder and target path
builder = msim
target_dir = .msim

global_build_flags[vhdl] = -rangecheck
global_build_flags[verilog] = -lint
global_build_flags[systemverilog] = -lint

# Relative paths (relative to the project file if using HTTP mode or the project
# root if using LSP mode)
vhdl          my_library foo.vhd                               -check_synthesis
vhdl          my_library foo_tb.vhd                            -2008
verilog       my_library verilog/a_verilog_file.v              -pedanticerrors
# Absolute paths are handled as such
systemverilog my_library /home/user/some_systemverilog_file.sv -pedanticerrors
```

Setting specific flags can be done per language or per file:

```
global_build_flags[vhdl] = <flags passed to the compiler when building VHDL files>
global_build_flags[verilog] = <flags passed to the compiler when building Verilog files>
global_build_flags[systemverilog] = <flags passed to the compiler when building SystemVerilog files>
```

When unset, `hdlcc` sets the following default values depending on the compiler
being used:

* ModelSim

| Compiler      | ModelSim                                                       |
| :---:         | :---                                                           |
| VHDL          | `-lint -pedanticerrors -check_synthesis -rangecheck -explicit` |
| Verilog       | `-lint -pedanticerrors -hazards`                               |
| SystemVerilog | `-lint -pedanticerrors -hazards`                               |

* GHDL

| Language      | Flags                        |
| :---:         | :---                         |
| VHDL          | `-fexplicit -frelaxed-rules` |
| Verilog       | N/A                          |
| SystemVerilog | N/A                          |

### LSP server

HDL Code Checker has beta support for [Language Server Protocol][LSP]. To start
in LSP mode:

```bash
hdlcc --lsp
```

On a Linux system, log file will be at `/tmp/hdlcc_log_pid<PID_NUMBER>.log` and
`/tmp/hdlcc_stderr_pid<PID_NUMBER>.log`.


### HTTP server

HDL Code Checker can be used in HTTP server mode also:

```bash
$ hdlcc
```

*Please note that this mode **does not use LSP to communicate**. Request/response
API is not yet available, but a reference implementation can be found in
[vim-hdl][vim-hdl]*

## Supported systems

| System  | CI      | CI status                                                                                                                                                         |
| :--:    | :--:    | :--:                                                                                                                                                              |
| Linux   | Yes     | [![Build Status](https://travis-ci.org/suoto/hdlcc.svg?branch=master)](https://travis-ci.org/suoto/hdlcc)                                                         |
| Windows | Partial | [![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdlcc/branch/master) |

## Editor support

* Vim: [vim-hdl](https://github.com/suoto/vim-hdl/)

---

## Style checking

Style checks are independent of a third-party compiler. Checking includes:

* Unused signals, constants, generics, shared variables, libraries, types and
 attributes
* Comment tags (`FIXME`, `TODO`, `XXX`)

Notice that currently the unused reports has caveats, namely declarations with
the same name inherited from a component, function, procedure, etc. In the
following example, the signal `rdy` won't be reported as unused in spite of the
fact it is not used.

```vhdl
signal rdy, refclk, rst : std_logic;
...

idelay_ctrl_u : idelay_ctrl
    port map (rdy    => open,
              refclk => refclk,
              rst    => rst);
```

---

## Issues

You can use the [issue tracker][issue_tracker] for bugs, feature request and so on.

## License

This software is licensed under the [GPL v3 license][gpl].

## Notice

Mentor Graphics®, ModelSim® and their respective logos are trademarks or registered
trademarks of Mentor Graphics, Inc.

Altera® and its logo is a trademark or registered trademark of Altera Corporation.

Xilinx® and its logo is a trademark or registered trademark of Xilinx, Inc.

`hdlcc`'s author has no connection or affiliation to any of the trademarks mentioned
or used by this software.

[Mentor_msim]: http://www.mentor.com/products/fv/modelsim/
[Altera_msim]: https://www.altera.com/downloads/download-center.html
[Xilinx_Vivado]: http://www.xilinx.com/products/design-tools/vivado/vivado-webpack.html
[gpl]: http://www.gnu.org/copyleft/gpl.html
[issue_tracker]: https://github.com/suoto/hdlcc/issues
[async_fifo_tb]: https://github.com/suoto/hdl_lib/blob/master/memory/testbench/async_fifo_tb.vhd
[LSP]: https://en.wikipedia.org/wiki/Language_Server_Protocol
[vim-hdl]: https://github.com/suoto/vim-hdl/
