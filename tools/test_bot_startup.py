#!/usr/bin/env python3
"""
Test script to verify the Discord bot can start properly
This script can help diagnose startup issues without running the full UI.
"""
import os
import sys
import logging
import asyncio
import importlib.util
import subprocess
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BotStartupTest")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def test_imports():
    """Test that all required modules can be imported"""
    try:
        logger.info("Testing imports...")
        modules = [
            "splitBot.config",
            "splitBot.utils",
            "splitBot.commands",
            "splitBot.main",
            "splitBot.services",
            "splitBot.slash_commands"
        ]
        
        success = True
        for module_name in modules:
            try:
                module = importlib.import_module(module_name)
                logger.info(f"✅ Successfully imported {module_name}")
            except ImportError as e:
                logger.error(f"❌ Failed to import {module_name}: {e}")
                success = False
        
        return success
    except Exception as e:
        logger.error(f"Error testing imports: {e}")
        return False

def check_command_functions():
    """Check that all command functions referenced in register_commands exist"""
    try:
        logger.info("Checking command functions...")
        from splitBot.commands import register_commands
        
        # Mock a bot object
        class MockBot:
            def __init__(self):
                self.commands = {}
                
            def command(self, *args, **kwargs):
                def decorator(func):
                    return func
                return decorator
        
        mock_bot = MockBot()
        
        # Get the command mappings
        commands = register_commands(mock_bot)
        
        # Check each command function exists
        success = True
        for name, func in commands.items():
            if func is None:
                logger.error(f"❌ Command function '{name}' is None")
                success = False
            else:
                logger.info(f"✅ Command '{name}' function exists")
        
        return success
    except Exception as e:
        logger.error(f"Error checking command functions: {e}")
        return False

def test_bot_startup():
    """Start the bot in a subprocess and check for errors"""
    try:
        logger.info("Testing bot startup...")
        
        # Check if the env file exists
        env_file = os.path.join(PROJECT_ROOT, ".env")
        if not os.path.exists(env_file):
            logger.warning("⚠️ .env file not found, the bot may not be able to connect to Discord")
        
        # Path to the main script
        main_script = os.path.join(PROJECT_ROOT, "splitBot", "main.py")
        
        # Start the process with a timeout
        process = subprocess.Popen(
            [sys.executable, main_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read output for 10 seconds and check for errors
        start_time = time.time()
        errors = []
        success = True
        
        while time.time() - start_time < 10:
            line = process.stdout.readline()
            if not line:
                break
                
            line = line.strip()
            print(line)
            
            if "ERROR" in line or "Error" in line or "error" in line:
                errors.append(line)
                success = False
                
            if "Bot is ready" in line:
                logger.info("✅ Bot started successfully")
                break
        
        # Terminate the process
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        
        if errors:
            logger.error("❌ Bot startup encountered errors:")
            for error in errors:
                logger.error(f"  - {error}")
        
        return success
    except Exception as e:
        logger.error(f"Error testing bot startup: {e}")
        return False

if __name__ == "__main__":
    import time
    
    # Run the tests
    imports_ok = test_imports()
    print("\n---\n")
    
    functions_ok = check_command_functions()
    print("\n---\n")
    
    startup_ok = test_bot_startup()
    print("\n---\n")
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Imports: {'✅ PASS' if imports_ok else '❌ FAIL'}")
    print(f"Command Functions: {'✅ PASS' if functions_ok else '❌ FAIL'}")
    print(f"Bot Startup: {'✅ PASS' if startup_ok else '❌ FAIL'}")
    
    # Exit with appropriate code
    if imports_ok and functions_ok and startup_ok:
        print("\n✅ All tests passed! The bot should start without issues.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Fix the issues before starting the bot.")
        sys.exit(1)
