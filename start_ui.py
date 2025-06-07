#!/usr/bin/env python3
"""
Start script for OARC Discord Teacher Bot UI
This script launches the UI for managing the Discord bot and Ollama models.
"""

import os
import sys
import logging
import signal
import traceback
import time
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ui_startup.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("UIStarter")

def setup_python_path():
    """Setup Python path to include all needed modules"""
    # Add current directory and subdirectories to path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add UI directory to path
    ui_path = os.path.join(script_dir, "ui")
    if ui_path not in sys.path:
        sys.path.insert(0, ui_path)
    
    # Add splitBot directory to path
    splitbot_path = os.path.join(script_dir, "splitBot")
    if splitbot_path not in sys.path:
        sys.path.insert(0, splitbot_path)
        
    # Add project root to path
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
        
    # Also add the project directory to path in case script is run from elsewhere
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    
    logger.info(f"Python path: {sys.path}")
    
    return True

def setup_ssl_certificates():
    """Setup SSL certificates for HTTPS requests"""
    try:
        import certifi
        cert_path = certifi.where()
        
        # Set environment variables for SSL certificate
        os.environ["SSL_CERT_FILE"] = cert_path
        os.environ["REQUESTS_CA_BUNDLE"] = cert_path
        
        logger.info(f"Using certifi's CA bundle: {cert_path}")
        return True
    except ImportError:
        logger.warning("certifi not installed, skipping certificate setup")
        return False
    except Exception as e:
        logger.error(f"Failed to setup SSL certificates: {e}")
        return False

def setup_webengine_environment():
    """Setup environment variables for PyQt WebEngine"""
    try:
        from ui.fix_webengine_env import fix_webengine_env
        
        # Apply WebEngine fixes
        fix_webengine_env()
        
        # Log current WebEngine environment variables
        logger.info("WebEngine environment variables:")
        logger.info(f"  QTWEBENGINE_DISABLE_SANDBOX={os.environ.get('QTWEBENGINE_DISABLE_SANDBOX', 'Not set')}")
        logger.info(f"  QTWEBENGINE_CHROMIUM_FLAGS={os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', 'Not set')}")
        logger.info(f"  QTWEBENGINE_REMOTE_DEBUGGING={os.environ.get('QTWEBENGINE_REMOTE_DEBUGGING', 'Not set')}")
        logger.info(f"  SSL_CERT_FILE={os.environ.get('SSL_CERT_FILE', 'Not set')}")
        logger.info(f"  REQUESTS_CA_BUNDLE={os.environ.get('REQUESTS_CA_BUNDLE', 'Not set')}")
        
        return True
    except ImportError:
        logger.error("Failed to import fix_webengine_env, trying manual setup")
        
        # Manually set environment variables
        os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --allow-file-access-from-files --ignore-certificate-errors"
        os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"
        
        return True
    except Exception as e:
        logger.error(f"Failed to setup WebEngine environment: {e}")
        return False

def start_ui():
    """Start the UI application"""
    try:
        logger.info("Starting OARC Discord Teacher Bot UI...")
        
        # Import UI manager class
        from ui.ollama_teacher_ui_manager import OllamaTeacherUI
        
        # Import PyQt modules
        from PyQt6.QtWidgets import QApplication
        
        # Create application instance
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # Keep running when window is closed
        app.setApplicationName("Ollama Teacher Bot")
        app.setApplicationVersion("2.0.0")
        app.setOrganizationName("OllamaTeacher")
        
        # Create UI manager
        ui = OllamaTeacherUI()
        
        # In case there's an issue with the window not showing
        ui.show()
        ui.raise_()  # Bring window to front
        ui.activateWindow()  # Activate the window
        
        # Handle SIGINT gracefully
        signal.signal(signal.SIGINT, lambda sig, frame: ui.quit_application())    
        
        # Start event loop
        return app.exec()
    except Exception as e:
        logger.error(f"Error starting UI: {e}")
        logger.error(traceback.format_exc())
        return 1

def main():
    """Main function"""
    try:
        # Setup Python path
        setup_python_path()
        
        # Setup SSL certificates
        setup_ssl_certificates()
        
        # Setup WebEngine environment
        setup_webengine_environment()
        
        # Start the UI
        exit_code = start_ui()
        
        return exit_code
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
        return 130
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
