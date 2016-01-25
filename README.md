 [![Build Status](https://travis-ci.org/suoto/hdlcc.svg?branch=master)](https://travis-ci.org/suoto/hdlcc)
 [![Build status](https://ci.appveyor.com/api/projects/status/hum48l6gwoqofwk8/branch/master?svg=true)](https://ci.appveyor.com/project/suoto/hdlcc/branch/master)
 [![codecov.io](https://codecov.io/github/suoto/hdlcc/coverage.svg?branch=master)](https://codecov.io/github/suoto/hdlcc?branch=master)

# HDL Code Checker

`hdlcc` is a tool that catches errors and warnings from HDL compilers so they can
be processed later. It was designed to be a syntax checker back end provider to text
editors.

## Editor support

* Vim: main target editor. Support is provided via [vim-hdl](https://github.com/suoto/vim-hdl.git)
 plugin.
* Komodo: under development at [Komodo HDL Lint](https://github.com/suoto/komodo-hdl-lint)

## Usage

`hdlcc` requires a configuration file listing libraries, source files, build flags,
etc. See the [wiki](https://github.com/suoto/hdlcc/wiki#project-file-formats) for
details on how to write it.

## Supported third-party compilers

* [Mentor Graphics® ModelSim®][Mentor_msim]
* [ModelSim-Altera® Edition][Altera_msim]

Tools with experimental support (need more testing):

* Xilinx XVHDL (bundled with [Vivado][Xilinx_Vivado], including the WebPACK edition)
* [GHDL](https://github.com/tgingold/ghdl)

Tools with planned support:

* [NVC](https://github.com/nickg/nvc)

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
