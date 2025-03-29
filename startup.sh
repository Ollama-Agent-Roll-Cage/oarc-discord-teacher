#!/bin/bash
# Startup script for Ollama Learning Discord Bot

# Navigate to the bot directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Ensure data directories exist
mkdir -p data/papers data/searches data/crawls

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
    python bot.py
    
    # If the bot exits with code 0, it was a clean shutdown
    if [ $? -eq 0 ]; then
        echo "Bot shut down cleanly. Exiting..."
        break
    fi
    
    echo "Bot crashed or encountered an error. Restarting in 10 seconds..."
    sleep 10
done
