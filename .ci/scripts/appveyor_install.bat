
echo "Starting path is %CD%"
echo "HDLCC_CI=%HDLCC_CI%"
echo "Configured builder is %BUILDER_NAME%"

git submodule update --init --recursive
if not exist %HDLCC_CI% git clone https://github.com/suoto/hdlcc_ci %HDLCC_CI% --recursive

if %ARCH% == 32 (
    set PYTHON=C:\Python27
) else (
    set PYTHON=C:\Python27-x64
)

echo "Python selected is %PYTHON%"

set PATH=%PYTHON%;%PYTHON%\Scripts;%PATH%

IF %APPVEYOR% == "True" (
    appveyor DownloadFile https://bootstrap.pypa.io/get-pip.py
    python get-pip.py
)

pip install -r requirements.txt
pip install git+https://github.com/suoto/rainbow_logging_handler

if not exist "%CACHE_PATH%" mkdir "%CACHE_PATH%"


if "%BUILDER_NAME%" == "msim"
  call %APPVEYOR_BUILD_FOLDER%\\.ci\\scripts\\setup_msim.bat

if "%BUILDER_NAME%" == "ghdl"
  call %APPVEYOR_BUILD_FOLDER%\\.ci\\scripts\\setup_ghdl.bat

if "%BUILDER_NAME%" == "msim"
  %BUILDER_PATH%\\vcom -version

pip install -U -e %APPVEYOR_BUILD_FOLDER%

