# Issue details

For questions or help, consider using [gitter.im](https://gitter.im/suoto/hdl_checker)

When opening an issue, make sure you provide

* Output of `hdl_checker -V`
* Python version used
* OS
* Compiler and version, one of
  * `vsim -version`
  * `ghdl --version`
  * `xvhdl -version`
* HDL Checker log output if possible
  * Please note that this typically includes filenames, compiler name and version and some design unit names!

To enable logging, you'll need to setup the LSP client to start HDL Checker with `--log-stream <path/to/log/file> --log-level DEBUG`.

Please note that the issue will have to be reproduced to be fixed, so adding a minimal reproducible example goes a long way.
