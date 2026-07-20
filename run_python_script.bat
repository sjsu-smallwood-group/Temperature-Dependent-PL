@echo off
setlocal
cd /d "%~dp0"

set "PY=C:\ProgramData\anaconda3\python.exe"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "REQ=%~dp0requirements.txt"

if not exist "%PY%" (
    echo ERROR: Anaconda Python not found at:
    echo   %PY%
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo Creating project virtual environment...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create .venv
        pause
        exit /b 1
    )
)

echo Ensuring dependencies are installed...
"%VENV_PY%" -m pip install -q -r "%REQ%"
if errorlevel 1 (
    echo ERROR: Failed to install requirements from requirements.txt
    pause
    exit /b 1
)

"%VENV_PY%" arduino_controlled_picomotor.py %*
pause
