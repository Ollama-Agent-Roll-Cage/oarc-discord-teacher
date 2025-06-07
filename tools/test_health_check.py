#!/usr/bin/env python3
"""
Health check utility for the OARC Discord Teacher UI
This script checks the health of key components and services
"""

import os
import sys
import logging
import requests
import json
import subprocess
import platform
import importlib
import time
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HealthCheck")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def check_ollama_api():
    """Check if Ollama API is accessible"""
    try:
        logger.info("Checking Ollama API...")
        
        # First try using the ollama package
        try:
            import ollama
            result = ollama.list()
            logger.info(f"Ollama API is working (via ollama package)")
            
            # Try to check the first model details
            try:
                models = []
                if hasattr(result, 'models'):
                    models = result.models
                    if models:
                        model_name = models[0].name
                        logger.info(f"Getting details for model: {model_name}")
                        show_result = ollama.show(model_name)
                        logger.info(f"Model details retrieved successfully")
                        return True, "Ollama API is working properly"
            except Exception as e:
                logger.warning(f"Could not check model details: {e}")
            
            return True, "Ollama API is accessible but couldn't check model details"
            
        except ImportError:
            logger.warning("Ollama package not installed, trying direct API")
            
        # Fall back to direct HTTP request
        response = requests.get("http://localhost:11434/api/version", timeout=5)
        if response.status_code == 200:
            data = response.json()
            version = data.get("version", "unknown")
            logger.info(f"Ollama API is accessible via HTTP. Version: {version}")
            return True, f"Ollama API is accessible (version: {version})"
        else:
            return False, f"Ollama API HTTP status: {response.status_code}"
            
    except requests.exceptions.ConnectionError:
        return False, "Ollama API connection error - is Ollama running?"
    except Exception as e:
        return False, f"Ollama API error: {str(e)}"

def check_ui_api():
    """Check if UI API server is running"""
    try:
        logger.info("Checking UI API server...")
        response = requests.get("http://localhost:8080/api/dashboard/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"UI API is accessible: {data}")
            return True, f"UI API is accessible"
        else:
            return False, f"UI API HTTP status: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "UI API connection error - is the UI running?"
    except Exception as e:
        return False, f"UI API error: {str(e)}"

def check_dependencies():
    """Check if required dependencies are installed"""
    logger.info("Checking Python dependencies...")
    dependencies = {
        "PyQt6": "UI framework",
        "httpx": "HTTP client",
        "ollama": "Ollama API client",
        "discord": "Discord bot",
        "pyarrow": "Parquet storage",
        "pandas": "Data processing"
    }
    
    missing = []
    for package, description in dependencies.items():
        try:
            importlib.import_module(package)
            logger.info(f"✓ {package} - OK")
        except ImportError:
            logger.error(f"✗ {package} - MISSING ({description})")
            missing.append(package)
    
    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}"
    else:
        return True, "All dependencies installed"

def check_discord_token():
    """Check if Discord token is set"""
    logger.info("Checking Discord token...")
    
    # Check environment variable
    token = os.getenv("DISCORD_TOKEN")
    if token:
        token_preview = token[:5] + "..." + token[-5:] if len(token) > 10 else "***"
        return True, f"Discord token is set: {token_preview}"
    
    # Check .env file
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            content = f.read()
            if "DISCORD_TOKEN" in content:
                return True, "Discord token found in .env file"
    
    return False, "Discord token not found"

def check_file_structure():
    """Check if required files and directories exist"""
    logger.info("Checking file structure...")
    
    required_files = [
        "start_ui.py",
        "ui/ollama_teacher_ui_manager.py",
        "ui/fallback_models.py",
        "splitBot/main.py",
        "splitBot/config.py",
        "splitBot/utils.py"
    ]
    
    required_dirs = [
        "data",
        "data/papers",
        "data/searches",
        "data/crawls",
        "data/links",
        "data/user_profiles"
    ]
    
    missing_files = []
    for file in required_files:
        path = os.path.join(PROJECT_ROOT, file)
        if not os.path.isfile(path):
            missing_files.append(file)
            logger.error(f"✗ File missing: {file}")
        else:
            logger.info(f"✓ File exists: {file}")
    
    missing_dirs = []
    for directory in required_dirs:
        path = os.path.join(PROJECT_ROOT, directory)
        if not os.path.isdir(path):
            missing_dirs.append(directory)
            logger.error(f"✗ Directory missing: {directory}")
        else:
            logger.info(f"✓ Directory exists: {directory}")
    
    if missing_files or missing_dirs:
        return False, f"Missing files: {missing_files}, Missing directories: {missing_dirs}"
    else:
        return True, "All required files and directories exist"

def run_all_checks():
    """Run all health checks and report results"""
    logger.info("=== Running OARC Discord Teacher Health Check ===")
    
    # System info
    logger.info(f"Python version: {platform.python_version()}")
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Run checks
    checks = [
        ("Ollama API", check_ollama_api()),
        ("UI API", check_ui_api()),
        ("Dependencies", check_dependencies()),
        ("Discord Token", check_discord_token()),
        ("File Structure", check_file_structure())
    ]
    
    # Print results
    logger.info("\n=== Health Check Results ===")
    
    all_pass = True
    for name, (success, message) in checks:
        status = "PASS" if success else "FAIL"
        logger.info(f"{name}: {status} - {message}")
        if not success:
            all_pass = False
    
    # Overall result
    if all_pass:
        logger.info("\n✅ All checks passed! System is healthy.")
        return True
    else:
        logger.info("\n❌ Some checks failed. See above for details.")
        return False

if __name__ == "__main__":
    success = run_all_checks()
    sys.exit(0 if success else 1)
