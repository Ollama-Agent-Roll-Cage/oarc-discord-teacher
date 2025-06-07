#!/usr/bin/env python3
"""
UI diagnostic tool for the OARC Discord Teacher Bot
This tool helps diagnose issues with the PyQt6 UI and WebEngine rendering
"""

import os
import sys
import logging
import platform
import traceback
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ui_diagnostic.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("UIDiagnostic")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def check_pyqt_installation():
    """Check if PyQt6 is properly installed"""
    logger.info("Checking PyQt6 installation...")
    
    try:
        from PyQt6.QtCore import QCoreApplication
        logger.info("✓ PyQt6.QtCore imported successfully")
        
        from PyQt6.QtGui import QGuiApplication
        logger.info("✓ PyQt6.QtGui imported successfully")
        
        from PyQt6.QtWidgets import QApplication
        logger.info("✓ PyQt6.QtWidgets imported successfully")
        
        logger.info("PyQt6 version: " + QCoreApplication.applicationVersion())
        
        return True, "PyQt6 installed correctly"
    except ImportError as e:
        logger.error(f"✗ PyQt6 import error: {e}")
        return False, f"PyQt6 not installed correctly: {str(e)}"
    except Exception as e:
        logger.error(f"✗ PyQt6 error: {e}")
        return False, f"PyQt6 error: {str(e)}"

def check_webengine_installation():
    """Check if PyQt6 WebEngine is properly installed"""
    logger.info("Checking PyQt6 WebEngine installation...")
    
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        logger.info("✓ PyQt6.QtWebEngineWidgets imported successfully")
        
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        logger.info("✓ PyQt6.QtWebEngineCore imported successfully")
        
        # Check if WebEngine attributes are available
        attributes = [attr for attr in dir(QWebEngineSettings.WebAttribute) if not attr.startswith('_')]
        logger.info(f"Available WebEngine attributes: {', '.join(attributes)}")
        
        return True, "WebEngine installed correctly"
    except ImportError as e:
        logger.error(f"✗ WebEngine import error: {e}")
        return False, f"WebEngine not installed correctly: {str(e)}"
    except Exception as e:
        logger.error(f"✗ WebEngine error: {e}")
        return False, f"WebEngine error: {str(e)}"

def test_minimal_window():
    """Try to create a minimal QApplication and window"""
    logger.info("Testing minimal QApplication and window...")
    
    try:
        from PyQt6.QtWidgets import QApplication, QLabel
        
        # Create application
        app = QApplication([])
        
        # Create window with visible text
        window = QLabel("UI Diagnostic - If you can see this, QApplication works!")
        window.setMinimumSize(400, 200)
        window.show()
        
        logger.info("✓ Created minimal window successfully")
        logger.info("The window should now be visible. Press Ctrl+C to exit.")
        
        # Run for 5 seconds only
        from PyQt6.QtCore import QTimer
        timer = QTimer()
        timer.timeout.connect(app.quit)
        timer.start(5000)
        
        app.exec()
        
        return True, "Minimal window test succeeded"
    except Exception as e:
        logger.error(f"✗ Minimal window error: {e}")
        return False, f"Minimal window error: {str(e)}"

def test_webengine_window():
    """Try to create a minimal WebEngine window"""
    logger.info("Testing minimal WebEngine window...")
    
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QUrl
        
        # Create application
        app = QApplication([])
        
        # Create main window
        window = QMainWindow()
        window.setWindowTitle("WebEngine Test Window")
        window.setMinimumSize(800, 600)
        
        # Create central widget
        central = QWidget()
        window.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Create web engine view
        web_view = QWebEngineView()
        layout.addWidget(web_view)
        
        # Load simple HTML
        html = """
        <html>
        <head>
            <title>WebEngine Test</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #f0f0f0;
                }
                h1 { color: #007bff; }
            </style>
        </head>
        <body>
            <h1>WebEngine Test</h1>
            <p>If you can see this properly formatted text, WebEngine is working!</p>
            <p>The window will close automatically in 5 seconds.</p>
        </body>
        </html>
        """
        web_view.setHtml(html)
        
        # Show window
        window.show()
        logger.info("✓ Created WebEngine window successfully")
        logger.info("The WebEngine window should now be visible. Press Ctrl+C to exit.")
        
        # Run for 5 seconds only
        from PyQt6.QtCore import QTimer
        timer = QTimer()
        timer.timeout.connect(app.quit)
        timer.start(5000)
        
        app.exec()
        
        return True, "WebEngine window test succeeded"
    except Exception as e:
        logger.error(f"✗ WebEngine window error: {e}")
        return False, f"WebEngine window error: {str(e)}"

def check_system_info():
    """Check system information relevant to UI rendering"""
    logger.info("Checking system information...")
    
    info = {
        "Platform": platform.platform(),
        "Python Version": platform.python_version(),
        "Architecture": platform.architecture()[0],
        "Processor": platform.processor(),
        "Display Server": os.environ.get('DISPLAY', 'Not set') if platform.system() != 'Windows' else 'Windows',
    }
    
    # Check if running on WSL
    is_wsl = False
    if platform.system() == 'Linux':
        try:
            with open('/proc/version', 'r') as f:
                is_wsl = 'microsoft' in f.read().lower() or 'wsl' in f.read().lower()
        except:
            pass
            
    info["WSL"] = "Yes" if is_wsl else "No"
    
    # Add Qt environment variables
    qt_vars = [var for var in os.environ if var.startswith('QT_') or 'QPA' in var]
    for var in qt_vars:
        info[f"Env: {var}"] = os.environ[var]
        
    # Print all info
    for key, value in info.items():
        logger.info(f"{key}: {value}")
        
    return info

def fix_webengine_env():
    """Apply fixes for WebEngine environment"""
    logger.info("Applying WebEngine environment fixes...")
    
    try:
        # Import the fix module
        from ui.fix_webengine_env import fix_webengine_env
        fix_webengine_env()
        logger.info("✓ Applied WebEngine environment fixes")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to apply WebEngine environment fixes: {e}")
        
        # Try applying fixes directly
        try:
            logger.info("Applying manual WebEngine environment fixes...")
            
            # Try to import certifi
            try:
                import certifi
                cert_path = certifi.where()
                os.environ["SSL_CERT_FILE"] = cert_path
                os.environ["REQUESTS_CA_BUNDLE"] = cert_path
                logger.info(f"Set certificate path to: {cert_path}")
            except ImportError:
                logger.warning("certifi not installed, skipping certificate setup")
            
            # Set WebEngine environment variables
            os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --allow-file-access-from-files --ignore-certificate-errors"
            os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"
            logger.info("Set WebEngine environment variables manually")
            
            return True
        except Exception as manual_e:
            logger.error(f"✗ Manual WebEngine fix failed: {manual_e}")
            return False

def run_diagnostic():
    """Run the full UI diagnostic"""
    logger.info("=== Starting OARC Discord Teacher UI Diagnostic ===")
    
    # Check system information
    system_info = check_system_info()
    
    # Apply WebEngine fixes
    fix_webengine_env()
    
    # Run tests
    tests = [
        ("PyQt6 Installation", check_pyqt_installation()),
        ("WebEngine Installation", check_webengine_installation()),
        ("Minimal Window", test_minimal_window()),
        ("WebEngine Window", test_webengine_window())
    ]
    
    # Print results
    logger.info("\n=== Test Results ===")
    
    all_pass = True
    for name, (success, message) in tests:
        status = "PASS" if success else "FAIL"
        logger.info(f"{name}: {status} - {message}")
        if not success:
            all_pass = False
    
    # Overall result
    if all_pass:
        logger.info("\n✅ All tests passed! UI components are working correctly.")
    else:
        logger.info("\n❌ Some tests failed. UI may not display correctly.")
        
    # Recommendations
    logger.info("\n=== Recommendations ===")
    
    if platform.system() == 'Linux' and system_info["WSL"] == "Yes":
        logger.warning("Running in WSL: GUI apps may not display correctly without a proper X server.")
        logger.info("Recommendation: Install VcXsrv on Windows and set DISPLAY environment variable.")
    
    if not all_pass:
        logger.info("1. Try reinstalling PyQt6 with: pip install PyQt6 PyQt6-WebEngine --upgrade")
        logger.info("2. Check if you have a compatible graphics environment")
        logger.info("3. On Windows, ensure you have the latest Visual C++ Redistributable installed")
        logger.info("4. On Linux, ensure required libraries are installed (libxcb, etc.)")
    
    return all_pass

if __name__ == "__main__":
    try:
        success = run_diagnostic()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Diagnostic interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"Unexpected error in diagnostic: {e}")
        traceback.print_exc()
        sys.exit(1)
