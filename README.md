# HDL Checker

[![PyPI version](https://img.shields.io/pypi/v/hdl_checker.svg)](https://pypi.org/project/hdl_checker/)
[![Build Status](https://travis-ci.org/suoto/hdl_checker.svg?branch=master)](https://travis-ci.org/suoto/hdl_checker)
[![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdl_checker/branch/master)
[![codecov](https://codecov.io/gh/suoto/hdl_checker/branch/master/graph/badge.svg)](https://codecov.io/gh/suoto/hdl_checker)
[![Code Climate](https://codeclimate.com/github/suoto/hdl_checker/badges/gpa.svg)](https://codeclimate.com/github/suoto/hdl_checker)
[![Join the chat at https://gitter.im/suoto/hdl_checker](https://badges.gitter.im/suoto/hdl_checker.svg)](https://gitter.im/suoto/hdl_checker?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Analytics](https://ga-beacon.appspot.com/UA-68153177-4/hdlcc/README.md?pixel)](https://github.com/suoto/hdl_checker)

HDL Checker provides a Python API that uses HDL compilers to build a project and
return info that can be used to populate syntax checkers. It can infer library
VHDL files likely belong to, besides working out mixed language dependencies,
compilation order, interpreting some compilers messages and providing some
(limited) static checks.

---

* [Installation](#installation)
* [Usage](#usage)
  * [Third-party tools](#third-party-tools)
  * [Configuration file](#configuration-file)
  * [LSP server](#lsp-server)
  * [HTTP server](#http-server)
* [Testing](#testing)
* [Supported systems](#supported-systems)
* [Editor support](#editor-support)
* [Style checking](#style-checking)
* [Issues](#issues)
* [License](#license)

## Installation

```sh
pip install hdl_checker
```

## Usage

HDL Checker server can be started via `hdl_checker` command. Use `hdl_checker --help`
for more info on how to use it.

```bash
$ hdl_checker -h
usage: hdl_checker [-h] [--host HOST] [--port PORT] [--lsp]
             [--attach-to-pid ATTACH_TO_PID] [--log-level LOG_LEVEL]
             [--log-stream LOG_STREAM] [--stdout STDOUT]
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
                        or a temporary file named hdl_checker_log_pid<PID>.log when
                        in LSP mode
  --stdout STDOUT       [HTTP] File to redirect stdout to. Defaults to a
                        temporary file named hdl_checker_stdout_pid<PID>.log
  --stderr STDERR       [HTTP] File to redirect stdout to. Defaults to a
                        temporary file named hdl_checker_stderr_pid<PID>.log
  --version, -V         Prints hdl_checker version and exit
```

### Third-party tools

HDL Checker supports

* [Mentor ModelSim][Mentor_msim]
* [ModelSim Intel FPGA Edition][Intel_msim]
* [GHDL][GHDL]
* [Vivado Simulator][Vivado_Simulator] (bundled with [Xilinx Vivado][Xilinx_Vivado])

### Configuring HDL Checker

HDL Checker can work with or without a configuration file. When not using a
configuration file and LSP mode, HDL Checker will search for files on the root of
the workspace and try to work out libraries.

Because automatic library discovery might be incorrect, one can use a JSON
configuration file to list files or to hint those which libraries were guessed
incorrectly.

#### Using JSON file

JSON format is as show below:

```json5
{
  /*
   * List of source files (optional, defaults to []).
   * If specificed, must be a list of either strings or source spec tuples, where
   * source spec tuple is a tuple in the form [string, dict[string, string]] (see
   * below for details).
   */
  "sources": [

    /*
     * Sources can be defined solely by their paths. Absolute paths are
     * unchanged, relative paths are made absolute by using the path to the
     * configuration file. Sources imported from an included file will follow
     * the same principle but using the path to the included path.
     */
    "/path/to/file_0",

    /*
     * Tuples can be used to add more info on the path. First element of the
     * tuple must the a string with the path, second element is optional
     * (defaults to an empty dictionary). Dictionary can specify the path's
     * library ({"library": "name_of_the_library"}, special compile
     * flags({"flags": ["flag_1", "flag_2"]}) or both.
     */
    [ "/path/with/library/and/flags", { "library": "foo", "flags": ["-2008"] } ],
    [ "/path/with/library",           { "library": "foo" } ],
    [ "/path/with/flags",             { "flags": ["-2008"] } ]
  ],

  /*
   * Extra config files to be added to the project (optional, defaults to [])
   * If specificed, must be a list of stings.
   */
  "include": [ "/path/to/another/json/file" ],

  /*
   * Language / scope specific info (optional, defaults to {}). Setting these,
   * event if empty, will override values defined per compiler. Flags should be
   * specified as a list of strings.
   *
   * The scope keys are:
   *   - "single": flags used to build the file being checked
   *   - "dependencies": flags used to build the dependencies of the file being
   *     checked
   *   - "global": flags used on both target and its dependencies
   *
   * For example, suppose the compilation sequence for a given source S is A, B,
   * C and then S. The tool will compile A, B and C using global and dependencies
   * flags, while S will be compiled using global and single flags.
   */
  "vhdl": {
    "flags": {
      "single": ["flag_1", "flag_2"],
      "dependencies": [],
      "global": []
    }
  },

  "verilog": {
    "flags": {
      "single": [],
      "dependencies": [],
      "global": []
    }
  },
  "systemverilog": {
    "flags": {
      "single": [],
      "dependencies": [],
      "global": []
    }
  }
}
```

#### Using legacy `prj` file

Old style project file syntax is as follows:

```bash
# This is a comment

[ builder = (msim|ghdl|xvhdl) ] # This is being deprecated

[ global_build_flags[ (vhdl|verilog|systemverilog) ] = <language specific flags> ]

# Specifying sources
(vhdl|verilog|systemverilog) <library name> <path/to/source> [file specific flags]
```

An example project file could be:

```bash
# Specifying builder
# HDL Checker will try to use ModelSim, GHDL and XVHDL in this order, so
# only add this if you want to force to a particular one
builder = msim

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
# Wildcards are supported
vhdl          my_library library/*.vhd
vhdl          my_library library/*/*.vhd
```

Setting specific flags can be done per language or per file:

```
global_build_flags[vhdl] = <flags passed to the compiler when building VHDL files>
global_build_flags[verilog] = <flags passed to the compiler when building Verilog files>
global_build_flags[systemverilog] = <flags passed to the compiler when building SystemVerilog files>
```

When unset, HDL Checker sets the following default values depending on the
compiler being used:

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

HDL Checker has beta support for [Language Server Protocol][LSP]. To start
in LSP mode:

```bash
hdl_checker --lsp
```

On a Linux system, log file will be at `/tmp/hdl_checker_log_pid<PID_NUMBER>.log` and
`/tmp/hdl_checker_stderr_pid<PID_NUMBER>.log`.

### HTTP server

HDL Checker can be used in HTTP server mode also:

```bash
hdl_checker
```

*Please note that this mode **does not use LSP to communicate**. Request/response
API is not yet available, but a reference implementation can be found in
[vim-hdl][vim-hdl]*

## Testing

HDL Checker uses a [docker][docker] container to run tests. If you wish to
run them, clone this repository and on the root folder run

```bash
./run_tests.sh
```

The container used for testing is [suoto/hdl_checker][hdl_checker_container]

## Supported systems

| System  | CI   | CI status                                                                                                                                                         |
| :--:    | :--: | :--:                                                                                                                                                              |
| Linux   | Yes  | [![Build Status](https://travis-ci.org/suoto/hdl_checker.svg?branch=master)](https://travis-ci.org/suoto/hdl_checker)                                                         |
| Windows | Yes  | [![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdl_checker/branch/master) |

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

Intel® and its logo is a trademark or registered trademark of Intel Corporation.

Xilinx® and its logo is a trademark or registered trademark of Xilinx, Inc.

HDL Checker's author has no connection or affiliation to any of the
trademarks mentioned or used by this software.

[docker]: https://www.docker.com/
[GHDL]: https://github.com/ghdl/ghdl
[gpl]: http://www.gnu.org/copyleft/gpl.html
[hdl_checker_container]: https://cloud.docker.com/u/suoto/repository/docker/suoto/hdl_checker_test
[Intel_msim]: https://www.intel.com/content/www/us/en/software/programmable/quartus-prime/model-sim.html
[issue_tracker]: https://github.com/suoto/hdl_checker/issues
[LSP]: https://en.wikipedia.org/wiki/Language_Server_Protocol
[Mentor_msim]: http://www.mentor.com/products/fv/modelsim/
[vim-hdl]: https://github.com/suoto/vim-hdl/
[Vivado_Simulator]: https://www.xilinx.com/products/design-tools/vivado/simulator.html
[Xilinx_Vivado]: http://www.xilinx.com/products/design-tools/vivado/vivado-webpack.html
