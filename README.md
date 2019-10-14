# HDL Checker

[![PyPI version](https://img.shields.io/pypi/v/hdl_checker.svg)](https://pypi.org/project/hdl_checker/)
[![Build Status](https://travis-ci.org/suoto/hdl_checker.svg?branch=master)](https://travis-ci.org/suoto/hdl_checker)
[![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdl_checker/branch/master)
[![codecov](https://codecov.io/gh/suoto/hdl_checker/branch/master/graph/badge.svg)](https://codecov.io/gh/suoto/hdl_checker)
[![Code Climate](https://codeclimate.com/github/suoto/hdl_checker/badges/gpa.svg)](https://codeclimate.com/github/suoto/hdl_checker)
[![Join the chat at https://gitter.im/suoto/hdl_checker](https://badges.gitter.im/suoto/hdl_checker.svg)](https://gitter.im/suoto/hdl_checker?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Analytics](https://ga-beacon.appspot.com/UA-68153177-4/hdlcc/README.md?pixel)](https://github.com/suoto/hdl_checker)

HDL Checker is a language server that wraps VHDL/Verilg/SystemVerilog tools that
aims to reduce the boilerplate code needed to set things up. It supports
[Language Server Protocol][LSP] or a custom HTTP interface; can infer library
VHDL files likely belong to, besides working out mixed language dependencies,
compilation order, interpreting some compilers messages and providing some
(limited) static checks.

---

* [Installation](#installation)
* [Editor support](#editor-support)
* [Usage](#usage)
  * [Third-party tools](#third-party-tools)
  * [Configuring HDL Checker](#configuring-HDL-Checker)
  * [LSP server](#lsp-server)
  * [HTTP server](#http-server)
* [Testing](#testing)
* [Supported systems](#supported-systems)
* [Style checking](#style-checking)
* [Issues](#issues)
* [License](#license)

## Installation

```sh
pip install hdl-checker --upgrade
```

or

```sh
pip install hdl-checker --user --upgrade
```

(Need to add `$HOME/.local/bin` to your `PATH` environment variable)

## Editor support

| Editor                          | Info                                                        |
| :---                            | :---                                                        |
| Vim - [dense-analysis/ale][ALE] | Soon, see (PR [#2804][ALE_PR])                              |
| Vim - [coc.vim][coc_vim]        | Will add instructions to the [Wiki][hdl_checker_wiki] soon  |
| VSCode                          | [HDL Checker HDL Checker VSCode client][hdl_checker_vscode] |

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

See the [Setting up a new project][hdl_checker_wiki_setup] section on the wiki.

### LSP server

HDL Checker has beta support for [Language Server Protocol][LSP]. To start
in LSP mode:

```bash
hdl_checker --lsp
```

On a Linux system, log file will be at `/tmp/hdl_checker_log_pid<PID_NUMBER>.log` and
`/tmp/hdl_checker_stderr_pid<PID_NUMBER>.log`.

As a language server, HDL Checker will provide

* Diagnostics
* Hover information
  * Dependencies: will report which path and library have been assigned
  * Design units: will report the compilation sequence and libraries
* Go to definition of dependencies

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

The container used for testing is [suoto/hdl_checker_test][hdl_checker_container]

## Supported systems

| System  | CI   | CI status                                                                                                                                                               |
| :--:    | :--: | :--:                                                                                                                                                                    |
| Linux   | Yes  | [![Build Status](https://travis-ci.org/suoto/hdl_checker.svg?branch=master)](https://travis-ci.org/suoto/hdl_checker)                                                   |
| Windows | Yes  | [![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdl_checker/branch/master) |

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

[ALE]: https://github.com/dense-analysis/ale
[ALE_PR]: https://github.com/dense-analysis/ale/pull/2804
[coc_vim]: https://github.com/neoclide/coc.nvim
[docker]: https://www.docker.com/
[GHDL]: https://github.com/ghdl/ghdl
[gpl]: http://www.gnu.org/copyleft/gpl.html
[hdl_checker_container]: https://cloud.docker.com/u/suoto/repository/docker/suoto/hdl_checker_test
[hdl_checker_vscode]: https://marketplace.visualstudio.com/items?itemName=suoto.hdl-checker-client
[hdl_checker_wiki]: https://github.com/suoto/hdl_checker/wiki
[hdl_checker_wiki_setup]: https://github.com/suoto/hdl_checker/wiki/Setting-up-a-project
[Intel_msim]: https://www.intel.com/content/www/us/en/software/programmable/quartus-prime/model-sim.html
[issue_tracker]: https://github.com/suoto/hdl_checker/issues
[LSP]: https://en.wikipedia.org/wiki/Language_Server_Protocol
[Mentor_msim]: http://www.mentor.com/products/fv/modelsim/
[vim-hdl]: https://github.com/suoto/vim-hdl/
[Vivado_Simulator]: https://www.xilinx.com/products/design-tools/vivado/simulator.html
[Xilinx_Vivado]: http://www.xilinx.com/products/design-tools/vivado/vivado-webpack.html
