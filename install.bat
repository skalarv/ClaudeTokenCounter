@echo off
rem ==============================================================
rem  TokenFollow / ClaudeTokenCounter installer
rem  - Verifies Python 3.8+ and tkinter.
rem  - Installs dev dependencies (pytest, pytest-cov) for running tests.
rem  - Creates a Desktop shortcut to TokenFollow.bat.
rem ==============================================================
setlocal enabledelayedexpansion
pushd "%~dp0"

echo.
echo ============================================================
echo   TokenFollow installer
echo ============================================================
echo.

rem ----- [1/4] Python ----------------------------------------------------
echo [1/4] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   ERROR: 'python' was not found on PATH.
  echo   Install Python 3.8 or newer from https://www.python.org/downloads/
  echo   During setup, tick "Add python.exe to PATH".
  echo.
  popd & endlocal & exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>nul
if errorlevel 1 (
  echo.
  echo   ERROR: Python 3.8+ is required.
  python --version
  echo.
  popd & endlocal & exit /b 1
)
for /f "delims=" %%V in ('python -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%V"
echo   OK: Python !PYVER!

rem ----- [2/4] tkinter ---------------------------------------------------
echo [2/4] Checking tkinter (needed for the overlay window)...
python -c "import tkinter" 2>nul
if errorlevel 1 (
  echo.
  echo   ERROR: tkinter is not available in this Python.
  echo   This happens with some slim distributions (conda minimal,
  echo   Microsoft Store Python). Reinstall Python from python.org;
  echo   the official Windows installer bundles tkinter by default.
  echo.
  popd & endlocal & exit /b 1
)
echo   OK: tkinter available.

rem ----- [3/4] Dev dependencies -----------------------------------------
echo [3/4] Installing test dependencies (pytest, pytest-cov)...
python -m pip install --disable-pip-version-check --quiet pytest pytest-cov
if errorlevel 1 (
  echo.
  echo   WARNING: Failed to install pytest / pytest-cov.
  echo   The app will still run; you just cannot run the test suite.
  echo.
) else (
  echo   OK: test dependencies installed.
)

rem ----- [4/4] Desktop shortcut -----------------------------------------
echo [4/4] Creating Desktop shortcut...
set "TARGET=%~dp0TokenFollow.bat"
set "WORKDIR=%~dp0"
if "%WORKDIR:~-1%"=="\" set "WORKDIR=%WORKDIR:~0,-1%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$path = [Environment]::GetFolderPath('Desktop') + '\TokenFollow.lnk'; " ^
  "$s = $ws.CreateShortcut($path); " ^
  "$s.TargetPath = '%TARGET%'; " ^
  "$s.WorkingDirectory = '%WORKDIR%'; " ^
  "$s.IconLocation = 'shell32.dll,13'; " ^
  "$s.Description = 'TokenFollow - Claude token usage overlay'; " ^
  "$s.Save()"

if errorlevel 1 (
  echo   WARNING: Could not create Desktop shortcut via PowerShell.
  echo   Fallback: copy TokenFollow.bat to your Desktop manually.
) else (
  echo   OK: Desktop shortcut created.
)

echo.
echo ============================================================
echo   Install complete.
echo ============================================================
echo.
echo   Double-click 'TokenFollow' on your Desktop to launch the
echo   overlay. Config is written next to the script on first run
echo   (config.json, cache.json). Close the overlay from its title
echo   bar; position and budgets are remembered between runs.
echo.
echo   To run the test suite:   run_tests.bat
echo.
popd & endlocal
