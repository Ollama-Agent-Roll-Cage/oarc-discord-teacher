#!/usr/bin/env python3
"""
Test script to verify Ollama model detection and capability identification.
Helps diagnose issues with the Ollama interface.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("OllamaModelTest")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

async def test_direct_api():
    """Test direct API calls to Ollama"""
    try:
        import httpx
        
        logger.info("Testing direct HTTP API access to Ollama...")
        
        # Test version endpoint
        async with httpx.AsyncClient(timeout=5.0) as client:
            logger.info("Calling /api/version...")
            response = await client.get("http://127.0.0.1:11434/api/version")
            if response.status_code == 200:
                version_data = response.json()
                logger.info(f"Ollama version: {version_data.get('version', 'unknown')}")
            else:
                logger.error(f"Failed to get version: HTTP {response.status_code}")
                return False
            
            # Test models endpoint (tags)
            logger.info("Calling /api/tags...")
            response = await client.get("http://127.0.0.1:11434/api/tags")
            if response.status_code == 200:
                models_data = response.json()
                
                if 'models' in models_data:
                    models = models_data['models']
                    logger.info(f"Found {len(models)} models")
                    
                    # Show first few models 
                    for i, model in enumerate(models[:3]):
                        logger.info(f"Model {i+1}: {model.get('name', 'unknown')}")
                    
                    # Test model info/capabilities for one model
                    if models:
                        first_model = models[0].get('name', 'unknown')
                        logger.info(f"Getting details for {first_model}...")
                        
                        show_response = await client.get(f"http://127.0.0.1:11434/api/show?name={first_model}")
                        if show_response.status_code == 200:
                            model_data = show_response.json()
                            logger.info(f"Model details: {model_data.get('details', {})}")
                            
                            # Check for capabilities
                            capabilities = model_data.get('details', {}).get('capabilities', [])
                            logger.info(f"Model capabilities: {capabilities}")
                            
                            # Determine if model has vision capability
                            has_vision = 'vision' in capabilities 
                            logger.info(f"Model has vision: {has_vision}")
                        else:
                            logger.error(f"Failed to get model details: HTTP {show_response.status_code}")
                else:
                    logger.warning("No 'models' field in API response")
                    return False
            else:
                logger.error(f"Failed to list models: HTTP {response.status_code}")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Error testing direct API: {e}")
        return False

async def test_ollama_interface():
    """Test the OllamaInterface class"""
    try:
        from splitBot.ollama_interface import OllamaInterface
        
        logger.info("Testing OllamaInterface...")
        interface = OllamaInterface()
        
        # Check availability
        is_available = interface.is_available()
        logger.info(f"Ollama available: {is_available}")
        
        if not is_available:
            logger.error("Ollama is not available, cannot proceed with tests")
            return False
        
        # List models
        models = await interface.list_models()
        logger.info(f"Found {len(models)} models: {', '.join(models[:3])}")
        
        # Get model capabilities
        if models:
            logger.info(f"Getting capabilities for {models[0]}...")
            model_info = await interface.get_model_info(models[0])
            logger.info(f"Model info: {model_info}")
            logger.info(f"Has vision capability: {model_info.get('has_vision', False)}")
        
        # Detect vision models
        logger.info("Detecting vision models...")
        base_models, vision_models = await interface.detect_vision_models()
        logger.info(f"Found {len(base_models)} base models and {len(vision_models)} vision models")
        
        if vision_models:
            logger.info(f"Vision models: {', '.join(m['name'] for m in vision_models)}")
        else:
            logger.warning("No vision models detected")
            
        return True
        
    except Exception as e:
        logger.error(f"Error testing OllamaInterface: {e}")
        return False

async def test_fallback_models():
    """Test the fallback_models module"""
    try:
        import ui.fallback_models as fallback
        
        logger.info("Testing fallback_models module...")
        
        # Get base and vision models
        base_models = fallback.get_base_models()
        vision_models = fallback.get_vision_models()
        
        logger.info(f"Fallback base models: {len(base_models)}")
        logger.info(f"Fallback vision models: {len(vision_models)}")
        
        # Test detection function
        logger.info("Testing detect_vision_models function...")
        detected_base, detected_vision = fallback.detect_vision_models()
        
        logger.info(f"Detected {len(detected_base)} base models and {len(detected_vision)} vision models")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing fallback_models: {e}")
        return False

async def main():
    """Run all tests"""
    logger.info("=== Ollama Model Test ===")
    
    # Test direct API
    direct_api_result = await test_direct_api()
    
    # Test OllamaInterface
    interface_result = await test_ollama_interface()
    
    # Test fallback_models
    fallback_result = await test_fallback_models()
    
    # Print results
    logger.info("\n=== Test Results ===")
    logger.info(f"Direct API test: {'✓ SUCCESS' if direct_api_result else '✗ FAILED'}")
    logger.info(f"OllamaInterface test: {'✓ SUCCESS' if interface_result else '✗ FAILED'}")
    logger.info(f"Fallback models test: {'✓ SUCCESS' if fallback_result else '✗ FAILED'}")
    
    if not all([direct_api_result, interface_result, fallback_result]):
        logger.error("Some tests failed. Check the logs above for details.")
        return 1
    else:
        logger.info("All tests passed successfully!")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
