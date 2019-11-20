# HDL Checker

[![PyPI version](https://img.shields.io/pypi/v/hdl_checker.svg)](https://pypi.org/project/hdl_checker/)
[![Build Status](https://travis-ci.org/suoto/hdl_checker.svg?branch=master)](https://travis-ci.org/suoto/hdl_checker)
[![Build status](https://ci.appveyor.com/api/projects/status/kbvor84i6xlnw79f/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdl-checker/branch/master)
[![codecov](https://codecov.io/gh/suoto/hdl_checker/branch/master/graph/badge.svg)](https://codecov.io/gh/suoto/hdl_checker)
[![Join the chat at https://gitter.im/suoto/hdl_checker](https://badges.gitter.im/suoto/hdl_checker.svg)](https://gitter.im/suoto/hdl_checker?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Mentioned in Awesome Computer Architecture](https://awesome.re/mentioned-badge.svg)](https://github.com/rajesh-s/awesome-computer-architecture)
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
  * [VS Code](#vs-code)
  * [Vim/NeoVim](#vimneovim)
  * [Emacs](#emacs)
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

**Note:** Make sure you can run `hdl_checker --version`, especially if using PIP
with the `--user` option.

## Editor support

### VS Code

Install the [HDL Checker VSCode client][hdl_checker_vscode] on VS Code.

### Vim/NeoVim

#### Using [dense-analysis/ale][vim_ale]

See (PR [#2804][vim_ale_pr]), once it gets merged, ALE should support HDL Checker
out of the box.

#### Using [coc.nvim][vim_coc_nvim]

Following [coc.nvim custom language server setup][vim_coc_nvim_register_lsp], add
this to your [coc.nvim configuration file][vim_coc_nvim_config_file]:

```json
{
    "languageserver": {
        "hdlChecker": {
            "command": "hdl_checker",
            "args": [
                "--lsp"
            ],
            "filetypes": [
                "vhdl",
                "verilog",
                "systemverilog"
            ]
        }
    }
}
```

#### Using [autozimu/LanguageClient-neovim][vim_lc_nvim]

Add HDL Checker to the server commands:

```viml
let g:LanguageClient_serverCommands = {
\   'vhdl': ['hdl_checker', '--lsp'],
\   'verilog': ['hdl_checker', '--lsp'],
\   'systemverilog': ['hdl_checker', '--lsp'],
\}
```

Please note that this will start one server per language

### Emacs

#### Using [emacs-lsp/lsp-mode][emacs_lsp]

Add this to your Emacs config file

```elisp
(require 'use-package)
(setq lsp-vhdl-server-path "~/.local/bin/hdl_checker") ; only needed if hdl_checker is not already on the PATH
(custom-set-variables
  '(lsp-vhdl-server 'hdl-checker))
(use-package lsp-mode
  :config (add-hook 'vhdl-mode-hook 'lsp))
```

## Usage

HDL Checker server can be started via `hdl_checker` command. Use `hdl_checker
--help` for more info on how to use it.

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
* [Vivado Simulator][Vivado_Simulator] (bundled with [Xilinx
  Vivado][Xilinx_Vivado])

### Configuring HDL Checker

See the [Setting up a new project][hdl_checker_wiki_setup] section on the wiki.

### LSP server

HDL Checker has beta support for [Language Server Protocol][LSP]. To start in LSP
mode:

```bash
hdl_checker --lsp
```

On a Linux system, log file will be at `/tmp/hdl_checker_log_pid<PID_NUMBER>.log`
and `/tmp/hdl_checker_stderr_pid<PID_NUMBER>.log`.

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

*Please note that this mode **does not use LSP over http to communicate**.
Request/response API is not yet available and is going to be deprecated in the
future. A reference implementation can be found in [vim-hdl][vim-hdl]*

## Testing

HDL Checker uses a [docker][docker] container to run tests. If you wish to run
them, clone this repository and on the root folder run

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

You can use the [issue tracker][issue_tracker] for bugs, feature request and so
on.

## License

This software is licensed under the [GPL v3 license][gpl].

## Notice

Mentor Graphics®, ModelSim® and their respective logos are trademarks or
registered trademarks of Mentor Graphics, Inc.

Intel® and its logo is a trademark or registered trademark of Intel Corporation.

Xilinx® and its logo is a trademark or registered trademark of Xilinx, Inc.

HDL Checker's author has no connection or affiliation to any of the trademarks
mentioned or used by this software.

[docker]: https://www.docker.com/
[emacs_lsp]: https://github.com/emacs-lsp/lsp-mode/
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
[vim_ale]: https://github.com/dense-analysis/ale
[vim_ale_pr]: https://github.com/dense-analysis/ale/pull/2804
[vim_coc_nvim]: https://github.com/neoclide/coc.nvim
[vim_coc_nvim_config_file]: https://github.com/neoclide/coc.nvim/wiki/Using-the-configuration-file
[vim_coc_nvim_register_lsp]: https://github.com/neoclide/coc.nvim/wiki/Language-servers#register-custom-language-servers
[vim_lc_nvim]: https://github.com/autozimu/LanguageClient-neovim
[Vivado_Simulator]: https://www.xilinx.com/products/design-tools/vivado/simulator.html
[Xilinx_Vivado]: http://www.xilinx.com/products/design-tools/vivado/vivado-webpack.html
