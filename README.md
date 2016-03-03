# HDL Code Checker

[![Build Status](https://travis-ci.org/suoto/hdlcc.svg?branch=master)](https://travis-ci.org/suoto/hdlcc)
[![Coverage Status](https://coveralls.io/repos/github/suoto/hdlcc/badge.svg?branch=master)](https://coveralls.io/github/suoto/hdlcc?branch=master)
[![Code Climate](https://codeclimate.com/github/suoto/hdlcc/badges/gpa.svg)](https://codeclimate.com/github/suoto/hdlcc)
[![Code Health](https://landscape.io/github/suoto/hdlcc/master/landscape.svg?style=flat)](https://landscape.io/github/suoto/hdlcc/master)

`hdlcc` provides a Python API between a VHDL project and some HDL compilers to
catch errors and warnings the compilers generate that can be used to populate
syntax checkers and linters of text editors. It takes into account the sources
dependencies when building so you don't need to provide a source list ordered by
hand.

* [Installation] (#installation)
* [Usage] (#usage)
  * [Standalone](#standalone)
  * [Within Python](#within-python)
* [Editor support] (#editor-support)
* [Supported third-party compilers] (#supported-third-party-compilers)
* [Style checking] (#style-checking)
* [Issues] (#issues)
* [License] (#license)

---

## Installation

This is mostly up to you. Common methods:

* Git submodule

    ```sh
    $ cd your/repo/path
    $ git submodule add https://github.com/suoto/hdlcc your/repo/submodules/path
    $ git submodule update
    ```

* Python distutils (under development)

    ```sh
    $ git clone https://github.com/suoto/hdlcc
    $ cd hdlcc
    $ python setup.py install
    ```

---

## Usage

`hdlcc` requires a configuration file listing libraries, source files, build flags,
etc. See the [wiki](https://github.com/suoto/hdlcc/wiki#project-file-formats) for
details on how to write it.

Besides that, it can be used [standalone](#standalone) or [within Python](#within-python).

### Standalone

You can use [hdlcc/hdlcc.py](https://github.com/suoto/hdlcc/blob/master/hdlcc.py)
as a standalone tool and a source for some usage examples.

```shell
$ ./hdlcc.py  -h
usage: hdlcc.py [-h] [--verbose] [--clean] [--build]
                [--sources [SOURCES [SOURCES ...]]] [--debug-print-sources]
                [--debug-print-compile-order] [--debug-parse-source-file]
                [--debug-run-static-check]
                [--debug-profiling [OUTPUT_FILENAME]]
                project_file

positional arguments:
  project_file          Configuration file that defines what should be built
                        (lists sources, libraries, build flags and so on

optional arguments:
  -h, --help            show this help message and exit
  --verbose, -v         Increases verbose level. Use multiple times to
                        increase more
  --clean, -c           Cleans the project before building
  --build, -b           Builds the project given by <project_file>
  --sources [SOURCES [SOURCES ...]], -s [SOURCES [SOURCES ...]]
                        Source(s) file(s) to build individually
  --debug-print-sources
  --debug-print-compile-order
  --debug-parse-source-file
  --debug-run-static-check
  --debug-profiling [OUTPUT_FILENAME]
```

### Within Python

Full API docs are not yet available. The example below should get you started, if
you need more info, check the code or open an issue at the [issue tracker][issue_tracker]
requesting help.

1. Subclass the ```ProjectBuilder``` class from ```hdlcc.project_builder```

    ```python
    from hdlcc.project_builder import ProjectBuilder

    class StandaloneProjectBuilder(ProjectBuilder):
        _ui_logger = logging.getLogger('UI')
        def handleUiInfo(self, message):
            self._ui_logger.info(message)

        def handleUiWarning(self, message):
            self._ui_logger.warning(message)

        def handleUiError(self, message):
            self._ui_logger.error(message)
    ```

1. Create a project object passing the configuration file as a parameter (for
 static checks only, no configuration file is needed). This triggers the
 project to be built in background

    ```python
    project = StandaloneProjectBuilder('path/to/config/file')
    project.waitForBuild()
    ```

1. You can now build a single file and get records that describe the messages it
 returns

    ```python
    for record in project.getMessagesByPath('path/to/the/source'):
        print "[{error_type}-{error_number}] @ " \
              "({line_number},{column}): {error_message}"\
                .format(**record)
    ```

 That should return something like

    ```
    [E-None] @ (83,30): no declaration for "integer_vector"
    [E-None] @ (83,30): no declaration for "integer_vector"
    [W-0] @ (29,14): constant 'ADDR_WIDTH' is never used
    ```

 (The example above uses GHDL to build 
[suoto/hdl_lib/code/memory/testbench/async_fifo_tb.vhd][async_fifo_tb])

---

## Editor support

* Vim: main target editor. Support is provided via [vim-hdl](https://github.com/suoto/vim-hdl.git)
 plugin.
* Komodo: under development at [Komodo HDL Lint](https://github.com/suoto/komodo-hdl-lint)

---

## Supported third-party compilers

* [Mentor Graphics® ModelSim®][Mentor_msim]
* [ModelSim-Altera® Edition][Altera_msim]

Tools with experimental support (need more testing):

* Xilinx XVHDL (bundled with [Vivado][Xilinx_Vivado], including the WebPACK edition)
* [GHDL](https://github.com/tgingold/ghdl)

Tools with planned support:

* [NVC](https://github.com/nickg/nvc)

---

## Style checking

Style checks are independent of a third-party compiler. Checking includes:

* Signal names in lower case
* Constants and generics in upper case
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
