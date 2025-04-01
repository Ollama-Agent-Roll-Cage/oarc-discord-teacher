@echo off
REM Startup script for Ollama Learning Discord Bot on Windows

REM Navigate to the bot directory
cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Ensure data directories exist
if not exist data mkdir data
if not exist data\papers mkdir data\papers
if not exist data\searches mkdir data\searches
if not exist data\crawls mkdir data\crawls

REM Check if Ollama is running
tasklist | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo Starting Ollama...
    start "" ollama serve
    REM Wait for Ollama to start
    timeout /t 5
)

:loop
echo Starting Ollama Learning Discord Bot...
python bot.py

REM If the bot exits with code 0, it was a clean shutdown
if %errorlevel% equ 0 (
    echo Bot shut down cleanly. Exiting...
    goto :end
)

echo Bot crashed or encountered an error. Restarting in 10 seconds...
timeout /t 10
goto :loop

:end
pause