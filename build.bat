@echo off
setlocal enabledelayedexpansion
title JuteSliverAnalyzer - Build

echo ============================================
echo  JuteSliverAnalyzer - Build Script
echo ============================================
echo.

set PYEXE=

REM ── 1. Use a system Python if one is already on PATH ───────────────────────
python --version >nul 2>&1
if not errorlevel 1 (
    set PYEXE=python
    echo Using the Python already installed on this machine.
    goto :install_packages
)

REM ── 2. No system Python found - fetch a private portable copy ourselves ───
echo No Python installation found on this machine.
echo Setting one up automatically - no installer, nothing to click through.
echo ^(first run only - needs an internet connection^)
echo.

if exist "python-embed\python.exe" (
    set PYEXE=python-embed\python.exe
    echo Portable Python already present from a previous run - skipping download.
    goto :install_packages
)

set PY_VER=3.11.9
set PY_ZIP=python-%PY_VER%-embed-amd64.zip
set PY_URL=https://www.python.org/ftp/python/%PY_VER%/%PY_ZIP%

echo Fetching Python %PY_VER% ^(~10 MB^)...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'"
if errorlevel 1 (
    echo.
    echo ERROR: Could not download Python. Check your internet connection
    echo and try again.
    pause
    exit /b 1
)

echo Extracting...
powershell -NoProfile -Command "Expand-Archive -Path '%PY_ZIP%' -DestinationPath 'python-embed' -Force"
del "%PY_ZIP%"

REM Enable site-packages + pip support in the portable distribution
(
    echo python311.zip
    echo .
    echo Lib\site-packages
    echo.
    echo import site
) > "python-embed\python311._pth"

echo Setting up pip...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'"
if errorlevel 1 (
    echo.
    echo ERROR: Could not download pip. Check your internet connection
    echo and try again.
    pause
    exit /b 1
)
python-embed\python.exe get-pip.py --no-warn-script-location >nul 2>&1
del get-pip.py

set PYEXE=python-embed\python.exe

:install_packages
echo.
echo Checking required packages ^(Flask, Pillow, PyInstaller^)...
set NEED_INSTALL=0

"%PYEXE%" -c "import flask" 2>nul
if errorlevel 1 set NEED_INSTALL=1

"%PYEXE%" -c "import PIL" 2>nul
if errorlevel 1 set NEED_INSTALL=1

"%PYEXE%" -c "import PyInstaller" 2>nul
if errorlevel 1 set NEED_INSTALL=1

if !NEED_INSTALL! == 1 (
    echo Installing missing packages automatically...
    "%PYEXE%" -m pip install --upgrade pip >nul 2>&1
    "%PYEXE%" -m pip install flask pillow pyinstaller --no-warn-script-location
    if errorlevel 1 (
        echo.
        echo ERROR: pip install failed. Check your internet connection
        echo and try again.
        pause
        exit /b 1
    )
) else (
    echo All required packages already installed - skipping.
)

echo.
echo ============================================
echo  Building JuteSliverAnalyzer.exe ...
echo ============================================
echo.

"%PYEXE%" -m PyInstaller JuteSliverAnalyzer.spec

if errorlevel 1 (
    echo.
    echo Build failed - see the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Your exe is at: dist\JuteSliverAnalyzer.exe
echo ============================================
pause
