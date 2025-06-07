#!/usr/bin/env python3
"""
Test script to verify that all necessary imports work correctly.
Run this to check if your environment is properly set up.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ImportTester")

def test_imports():
    """Test all required imports"""
    
    required_modules = [
        "PyQt6",
        "requests",
        "ollama",
        "discord",
        "httpx",
        "json",
        "certifi"
    ]
    
    optional_modules = [
        "groq",
        "pandas",
        "numpy"
    ]
    
    missing_required = []
    missing_optional = []
    
    # Test required modules
    logger.info("Testing required modules...")
    for module in required_modules:
        try:
            __import__(module)
            logger.info(f"✓ {module}")
        except ImportError:
            logger.error(f"✗ {module} - MISSING")
            missing_required.append(module)
    
    # Test optional modules
    logger.info("\nTesting optional modules...")
    for module in optional_modules:
        try:
            __import__(module)
            logger.info(f"✓ {module}")
        except ImportError:
            logger.warning(f"✗ {module} - MISSING (optional)")
            missing_optional.append(module)
    
    # Check for ui.fallback_models
    try:
        from ui import fallback_models
        logger.info("✓ ui.fallback_models")
    except ImportError:
        logger.error("✗ ui.fallback_models - MISSING")
        missing_required.append("ui.fallback_models")
    
    # Report status
    if missing_required:
        logger.error(f"\nMissing required modules: {', '.join(missing_required)}")
        logger.error("Please install missing modules with: pip install module_name")
        return False
    
    if missing_optional:
        logger.warning(f"\nMissing optional modules: {', '.join(missing_optional)}")
        logger.warning("These are not required but may enhance functionality.")
    
    logger.info("\nAll required modules available!")
    return True

if __name__ == "__main__":
    success = test_imports()
    if not success:
        sys.exit(1)
    sys.exit(0)
