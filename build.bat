@echo off
REM Build the standalone Windows executable into dist\.
REM
REM   build.bat   ->  one self-contained file (dist\fileuploader.exe)
REM
REM Only needed if you want to build on your own Windows machine. The GitHub
REM Actions workflow does the same thing on every v* tag.

setlocal
cd /d "%~dp0"

where python >nul 2>&1 || (echo Python is not on PATH. Install it from python.org, ticking "Add to PATH". & exit /b 1)

if not exist ".venv" (
  echo Creating virtualenv
  python -m venv .venv || exit /b 1
)

echo Installing dependencies
call .venv\Scripts\pip.exe install -q -r requirements-dev.txt || exit /b 1

echo Building
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
set FILEUPLOADER_ONEFILE=1
call .venv\Scripts\pyinstaller.exe --noconfirm --clean fileuploader.spec || exit /b 1

if not exist "dist\fileuploader.exe" (echo Build finished but dist\fileuploader.exe is missing. & exit /b 1)
echo.
echo Built dist\fileuploader.exe
endlocal
