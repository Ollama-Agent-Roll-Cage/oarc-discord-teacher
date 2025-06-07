#!/usr/bin/env python3
"""
Fix script for UI API issues in the OARC Discord Teacher Bot
This script diagnoses and fixes common issues with the UI API
"""

import os
import sys
import logging
import json
import time
import requests
import subprocess
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("UIAPIFix")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def test_api_connection(port=8080):
    """Test if the UI API server is accessible"""
    logger.info(f"Testing API connection on port {port}...")
    
    try:
        response = requests.get(f"http://localhost:{port}/api/dashboard/stats", timeout=5)
        if response.status_code == 200:
            logger.info(f"API connection successful! Status: {response.status_code}")
            try:
                data = response.json()
                logger.info(f"Dashboard stats: {data}")
                return True, data
            except json.JSONDecodeError:
                logger.error("API returned invalid JSON")
                return False, None
        else:
            logger.error(f"API connection failed with status code: {response.status_code}")
            return False, None
    except requests.exceptions.ConnectionError:
        logger.error(f"Could not connect to API server on port {port}")
        return False, None
    except Exception as e:
        logger.error(f"Error testing API connection: {e}")
        return False, None

def check_bot_manager():
    """Check if the BotManager module is working properly"""
    logger.info("Checking BotManager module...")
    
    try:
        # Try to import and initialize BotManager
        from splitBot.bot_manager import BotManager
        manager = BotManager()
        
        # Test if the process checking function works
        is_running = manager._is_process_running()
        logger.info(f"BotManager._is_process_running() returned: {is_running}")
        
        # Check if the bot is actually running by looking for Python processes with main.py
        import psutil
        bot_processes = []
        for process in psutil.process_iter(['pid', 'name', 'cmdline']):
            if process.info['name'] == 'python.exe' or process.info['name'] == 'python':
                if process.info['cmdline'] and any('main.py' in cmd for cmd in process.info['cmdline']):
                    bot_processes.append(process.info['pid'])
        
        logger.info(f"Found {len(bot_processes)} bot processes: {bot_processes}")
        
        # Compare with BotManager's finding
        if is_running and not bot_processes:
            logger.warning("BotManager thinks bot is running but no matching processes found!")
        elif not is_running and bot_processes:
            logger.warning("BotManager thinks bot is not running but processes were found!")
        
        return True
    except ImportError:
        logger.error("Could not import BotManager module")
        return False
    except Exception as e:
        logger.error(f"Error checking BotManager: {e}")
        return False

def fix_zombie_processes():
    """Find and kill any zombie bot processes"""
    logger.info("Looking for zombie bot processes...")
    
    try:
        import psutil
        killed = 0
        
        for process in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if process.info['name'] == 'python.exe' or process.info['name'] == 'python':
                    if process.info['cmdline'] and any('main.py' in cmd for cmd in process.info['cmdline']):
                        logger.info(f"Found bot process: PID {process.info['pid']}")
                        
                        # Ask before killing
                        if input(f"Kill process {process.info['pid']}? (y/n): ").lower() == 'y':
                            if sys.platform == "win32":
                                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.info['pid'])], 
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            else:
                                process.kill()
                            logger.info(f"Killed process {process.info['pid']}")
                            killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        logger.info(f"Killed {killed} zombie processes")
        return killed
    except ImportError:
        logger.error("psutil module not available, cannot check for zombie processes")
        return 0
    except Exception as e:
        logger.error(f"Error fixing zombie processes: {e}")
        return 0

def fix_bot_manager_issues():
    """Fix issues with BotManager"""
    logger.info("Attempting to fix BotManager issues...")
    
    # Check if splitBot/bot_manager.py exists
    bot_manager_path = os.path.join(PROJECT_ROOT, "splitBot", "bot_manager.py")
    if not os.path.exists(bot_manager_path):
        logger.error(f"BotManager file not found at {bot_manager_path}")
        return False
    
    # Read the file to check for issues
    with open(bot_manager_path, "r") as f:
        content = f.read()
    
    # Check for common issues and fix them
    fixes_needed = []
    
    # Check if psutil import is missing
    if "import psutil" not in content:
        fixes_needed.append("Missing psutil import")
    
    # Check if _is_process_running has proper error handling
    if "_is_process_running" in content and "except Exception" not in content:
        fixes_needed.append("Missing exception handling in _is_process_running")
    
    # Print found issues
    if fixes_needed:
        logger.info(f"Issues found in BotManager: {fixes_needed}")
        logger.info("Please run the UI API fix script to apply fixes automatically")
    else:
        logger.info("No issues found in BotManager code")
    
    return len(fixes_needed) == 0

def main():
    """Main function to diagnose and fix UI API issues"""
    logger.info("=== OARC Discord Teacher UI API Diagnostics ===")
    
    # Test API connection
    success, data = test_api_connection()
    
    # Check BotManager
    bot_manager_ok = check_bot_manager()
    
    # Offer to kill zombie processes
    if not success or not bot_manager_ok:
        print("\nWould you like to check for and kill any zombie bot processes? (y/n): ", end="")
        if input().lower() == 'y':
            fix_zombie_processes()
    
    # Check for BotManager issues
    fix_bot_manager_issues()
    
    # Print summary
    print("\n=== Diagnostic Summary ===")
    print(f"API Connection: {'✅ Success' if success else '❌ Failed'}")
    print(f"BotManager: {'✅ OK' if bot_manager_ok else '❌ Issues found'}")
    
    # Suggestions
    print("\n=== Suggestions ===")
    if not success:
        print("1. Make sure the UI application is running")
        print("2. Check if the HTTP server started correctly in the UI logs")
        print("3. Try restarting the UI application")
    
    if not bot_manager_ok:
        print("1. Check the BotManager implementation for errors")
        print("2. Make sure psutil is installed (pip install psutil)")
        print("3. Apply the recommended fixes to the BotManager code")
    
    if success and bot_manager_ok:
        print("✅ Everything seems to be working correctly!")
        
    return 0 if success and bot_manager_ok else 1

if __name__ == "__main__":
    sys.exit(main())
