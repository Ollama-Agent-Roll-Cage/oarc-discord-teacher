#!/usr/bin/env python3
"""
Fix script for WebEngine environment issues in the OARC Discord Teacher Bot UI
This script can be run directly to fix SSL certificate and WebEngine issues
"""

import os
import sys
import logging
import certifi
from pathlib import Path

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WebEngineFix")

def fix_webengine_env():
    """Fix WebEngine environment variables"""
    logger.info("Setting up WebEngine environment variables...")
    
    # Disable sandbox for development environment
    os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    
    # Add Chrome flags to bypass security restrictions for local development
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --allow-file-access-from-files --ignore-certificate-errors"
    
    # Enable remote debugging on port 9222
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"
    
    # Set SSL certificate path using certifi's CA bundle
    cert_path = certifi.where()
    os.environ["SSL_CERT_FILE"] = cert_path
    os.environ["REQUESTS_CA_BUNDLE"] = cert_path
    
    logger.info(f"Using certifi's CA bundle: {cert_path}")
    
    # Log all environment variables we've set
    logger.info("WebEngine environment variables:")
    logger.info(f"  QTWEBENGINE_DISABLE_SANDBOX={os.environ.get('QTWEBENGINE_DISABLE_SANDBOX')}")
    logger.info(f"  QTWEBENGINE_CHROMIUM_FLAGS={os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS')}")
    logger.info(f"  QTWEBENGINE_REMOTE_DEBUGGING={os.environ.get('QTWEBENGINE_REMOTE_DEBUGGING')}")
    logger.info(f"  SSL_CERT_FILE={os.environ.get('SSL_CERT_FILE')}")
    logger.info(f"  REQUESTS_CA_BUNDLE={os.environ.get('REQUESTS_CA_BUNDLE')}")
    
    logger.info("WebEngine environment successfully configured")
    logger.info(f"Remote debugging available at http://127.0.0.1:{os.environ.get('QTWEBENGINE_REMOTE_DEBUGGING', '9222')}")
    
    return True

def set_webengine_environment():
    """Alias for fix_webengine_env for compatibility"""
    return fix_webengine_env()

def main():
    """Run as a standalone script"""
    fix_webengine_env()
    print("WebEngine environment variables have been set")
    print(f"SSL certificate path: {os.environ.get('SSL_CERT_FILE')}")
    print("You can now run start_ui.py to launch the UI")

if __name__ == "__main__":
    main()
