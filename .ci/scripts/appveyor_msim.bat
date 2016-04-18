
set APPVEYOR_BUILD_FOLDER=%CD%
set CACHE_PATH="%LOCALAPPDATA%\\cache"
set HDLCC_CI="%LOCALAPPDATA%\\hdlcc_ci"
set BUILDER_NAME=msim
set BUILDER_PATH="%LOCALAPPDATA%\\modelsim_ase\\win32aloem"
set ARCH=32
set URL=http://download.altera.com/akdlm/software/acdsinst/15.1/185/ib_installers/ModelSimSetup-15.1.0.185-windows.exe

set VENV_PATH="%LOCALAPPDATA%\\venv_%BUILDER_NAME%\\"

if exist %VENV_PATH% rmdir %VENV_PATH% /s /q

virtualenv %VENV_PATH%
call %VENV_PATH%\\Scripts\\activate.bat

.ci\\scripts\\appveyor_install.bat

