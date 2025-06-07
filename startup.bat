@echo off
title OARC Discord Teacher Bot
echo Starting OARC Discord Teacher Bot...
echo.

REM Check if virtual environment exists
IF NOT EXIST .venv\Scripts\activate.bat (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install or update dependencies
echo Checking dependencies...
pip install -r requirements.txt

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
