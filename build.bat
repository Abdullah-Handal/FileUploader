@echo off
REM Build the Python half of the Windows app into dist\.
REM
REM   build.bat   ->  dist\fileuploader.exe
REM
REM That is the server, the upload machinery and the launcher. It is NOT the
REM whole download: the window is a separate Pake (Tauri) binary that needs
REM Node and Rust to build, and that the launcher expects to find at
REM window\FileUploaderWindow.exe beside it. Without it the app still works and
REM opens in your browser instead of its own window.
REM
REM To build both, run the GitHub Actions "Windows build" workflow, which is
REM what every v* tag does. To build just the window here:
REM
REM   npm install -g pake-cli
REM   pake --config pake.json

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
echo.
echo This half opens in your browser. For the app window, put the Pake build
echo at dist\window\FileUploaderWindow.exe -- see the README.
endlocal
