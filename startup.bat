@echo off
title OARC Discord Teacher Bot
echo Starting OARC Discord Teacher Bot...
echo.

REM Check if UV is installed
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo UV package manager not found.
    echo Installing UV using PowerShell...
    powershell -Command "iwr -useb https://install.ultraviolet.rs | iex"
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install UV. Please install manually:
        echo https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    echo UV installed successfully.
)

REM Check if virtual environment exists
IF NOT EXIST .venv\Scripts\activate.bat (
    echo Creating virtual environment with UV...
    uv venv -p 3.11 .venv
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment with UV.
        echo Falling back to standard venv...
        python -m venv .venv
    )
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install or update dependencies using UV
echo Checking dependencies using UV...
uv pip install -r requirements.txt

REM Install core utilities
echo Installing core utilities...
uv pip install uv pip wheel setuptools build twine

REM Run tests to validate setup
echo Testing imports...
python test_imports.py

REM Check if .env file exists
IF NOT EXIST .env (
    echo Creating .env file...
    python create_env_file.py
)

REM Run the UI
echo Starting Discord Teacher UI...
python start_ui.py

REM Keep the window open if there's an error
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo Error occurred! Please check the logs above.
    pause
)
