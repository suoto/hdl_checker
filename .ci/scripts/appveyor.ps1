$APPVEYOR_BUILD_FOLDER="e:\\vim-hdl\\dependencies\\hdlcc"
"LOCALAPPDATA = $env:LOCALAPPDATA"

$env:PYTHONPATH="$env:LOCALAPPDATA\\rainbow_logging_handler"

$env:PATH="C:\\Python27;$env:PATH"

pip install -e . --user -U

$env:BUILDER_NAME="ghdl"
$env:BUILDER_PATH="$env:LOCALAPPDATA\\ghdl-0.31-mcode-win32\\bin"

"BUILDER_NAME is $env:BUILDER_NAME"
"BUILDER_PATH is $env:BUILDER_PATH"

$TESTS=""

# REM  @set TESTS=hdlcc.tests.test_builders
# REM  @set TESTS=hdlcc.tests.test_config_parser
# REM  @set TESTS=hdlcc.tests.test_persistency
# REM  @set TESTS=hdlcc.tests.test_project_builder
# REM  @set TESTS=hdlcc.tests.test_source_file
# REM  @set TESTS=hdlcc.tests.test_standalone
# @set TESTS=hdlcc.tests.test_server_handlers


$RUNNER_ARGS="-vv --log-capture -F --debug"

"TESTS: $TESTS"

python $env:APPVEYOR_BUILD_FOLDER\\.ci\\scripts\\run_tests.py -vv --log-capture -F --debug


