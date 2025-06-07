#!/bin/bash
# Startup script for Ollama Learning Discord Bot

# Navigate to the bot directory
cd "$(dirname "$0")"

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "UV package manager not found. Installing UV..."
    curl -sSf https://install.ultraviolet.rs | sh
    
    # Check if installation was successful
    if [ $? -ne 0 ]; then
        echo "Failed to install UV. Please install manually:"
        echo "https://github.com/astral-sh/uv"
        exit 1
    fi
    echo "UV installed successfully."
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment with UV..."
    uv venv -p 3.11 .venv
    
    # Check if creation was successful
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment with UV."
        echo "Falling back to standard venv..."
        python -m venv .venv
    fi
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies using UV
echo "Installing dependencies using UV..."
uv pip install -r requirements.txt

# Install core utilities
echo "Installing core utilities..."
uv pip install uv pip wheel setuptools build twine

# Ensure data directories exist
mkdir -p data/papers data/searches data/crawls data/links data/user_profiles

# Check if Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    echo "Starting Ollama..."
    ollama serve &
    # Wait for Ollama to start
    sleep 5
fi

# Loop to restart the bot if it crashes
while true; do
    echo "Starting Ollama Learning Discord Bot..."
    python start_ui.py
    
    # If the bot exits with code 0, it was a clean shutdown
    if [ $? -eq 0 ]; then
        echo "Bot shut down cleanly. Exiting..."
        break
    fi
    
    echo "Bot crashed or encountered an error. Restarting in 10 seconds..."
    sleep 10
done
