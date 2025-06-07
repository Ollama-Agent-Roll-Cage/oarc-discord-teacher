#!/usr/bin/env python3
"""
Start script for OARC Discord Teacher Bot
This script properly sets up the Python path and launches the bot
"""

import os
import sys
import logging
from pathlib import Path

# Ensure the project directory is in the Python path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BotStarter")

def main():
    """Main function to start the bot"""
    try:
        logger.info("Starting OARC Discord Teacher Bot...")
        
        # Create required directories
        data_dir = os.getenv('DATA_DIR', 'data')
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        Path(f"{data_dir}/searches").mkdir(parents=True, exist_ok=True)
        Path(f"{data_dir}/papers").mkdir(parents=True, exist_ok=True)
        Path(f"{data_dir}/crawls").mkdir(parents=True, exist_ok=True)
        Path(f"{data_dir}/links").mkdir(parents=True, exist_ok=True)
        Path(f"{data_dir}/user_profiles").mkdir(parents=True, exist_ok=True)
        
        # Import and run the bot
        from splitBot.main import main as run_bot
        run_bot()
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
