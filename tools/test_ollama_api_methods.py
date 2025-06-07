#!/usr/bin/env python3
"""
Test Ollama API methods to verify proper usage
This script tests both GET and POST methods for the Ollama API endpoints
"""
import httpx
import json
import logging
import sys
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("OllamaAPITester")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Constants
OLLAMA_API_BASE = "http://127.0.0.1:11434"

def test_ollama_api_methods():
    """
    Test various methods of accessing the Ollama API
    """
    logger.info("Testing Ollama API Methods")
    
    # 1. Test the /api/version endpoint (should work with GET)
    logger.info("\n=== Testing /api/version (GET) ===")
    try:
        with httpx.Client() as client:
            response = client.get(f"{OLLAMA_API_BASE}/api/version")
            logger.info(f"Status code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Success! Ollama version: {data.get('version')}")
            else:
                logger.error(f"Failed with status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
    except Exception as e:
        logger.error(f"Error with GET /api/version: {e}")

    # 2. Test the /api/tags endpoint (should work with GET)
    logger.info("\n=== Testing /api/tags (GET) ===")
    try:
        with httpx.Client() as client:
            response = client.get(f"{OLLAMA_API_BASE}/api/tags")
            logger.info(f"Status code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if 'models' in data:
                    models = data['models']
                    logger.info(f"Success! Found {len(models)} models")
                    if models:
                        logger.info(f"First model: {models[0].get('name')}")
                else:
                    logger.error("No 'models' field in response")
            else:
                logger.error(f"Failed with status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
    except Exception as e:
        logger.error(f"Error with GET /api/tags: {e}")

    # 3. Test the /api/show endpoint with GET (should fail)
    logger.info("\n=== Testing /api/show with GET (expect failure) ===")
    try:
        with httpx.Client() as client:
            # Use first model name from tags if available
            model_name = "llama3"
            try:
                tags_response = client.get(f"{OLLAMA_API_BASE}/api/tags")
                if tags_response.status_code == 200:
                    tags_data = tags_response.json()
                    if 'models' in tags_data and tags_data['models']:
                        model_name = tags_data['models'][0].get('name', model_name)
            except Exception as e:
                logger.warning(f"Couldn't get model name from tags: {e}")
            
            # Now try the GET request to /api/show
            response = client.get(f"{OLLAMA_API_BASE}/api/show?name={model_name}")
            logger.info(f"Status code: {response.status_code}")
            logger.info(f"Response: {response.text[:200]}")
            if response.status_code == 405:
                logger.info("GET method not allowed, as expected.")
            elif response.status_code == 200:
                logger.warning("GET method worked unexpectedly! Are you using a newer Ollama version?")
            else:
                logger.error(f"Unexpected status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error with GET /api/show: {e}")

    # 4. Test the /api/show endpoint with POST (should work)
    logger.info("\n=== Testing /api/show with POST (should succeed) ===")
    try:
        with httpx.Client() as client:
            # Use first model name from tags if available
            model_name = "llama3"
            try:
                tags_response = client.get(f"{OLLAMA_API_BASE}/api/tags")
                if tags_response.status_code == 200:
                    tags_data = tags_response.json()
                    if 'models' in tags_data and tags_data['models']:
                        model_name = tags_data['models'][0].get('name', model_name)
            except Exception as e:
                logger.warning(f"Couldn't get model name from tags: {e}")
            
            # Now try the POST request to /api/show
            response = client.post(
                f"{OLLAMA_API_BASE}/api/show",
                json={"name": model_name}
            )
            logger.info(f"Status code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Success! Model details retrieved")
                logger.info(f"Model parameters: {data.get('parameters', 'unknown')}")
                logger.info(f"Model details: {json.dumps(data.get('details', {}), indent=2)}")
                if 'details' in data and 'capabilities' in data['details']:
                    logger.info(f"Capabilities: {data['details']['capabilities']}")
            else:
                logger.error(f"Failed with status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
    except Exception as e:
        logger.error(f"Error with POST /api/show: {e}")

    # 5. Test the official Ollama Python client
    logger.info("\n=== Testing Ollama Python client ===")
    try:
        import ollama
        
        # Use the Client class rather than module-level functions
        client = ollama.Client(host="http://localhost:11434")
        
        # Try to list models
        logger.info("Calling client.list()")
        models_list = client.list()
        
        # Show models list
        if hasattr(models_list, 'models'):
            models = models_list.models
            logger.info(f"Success! Found {len(models)} models")
            if models:
                logger.info(f"First model: {models[0].name}")
        elif isinstance(models_list, dict) and 'models' in models_list:
            models = models_list['models']
            logger.info(f"Success! Found {len(models)} models")
            if models:
                logger.info(f"First model: {models[0].get('name')}")
        else:
            logger.warning(f"Unexpected format from client.list(): {type(models_list)}")

        # If we found any models, try the show method
        if 'models' in vars():
            model_name = None
            if hasattr(models[0], 'name'):
                model_name = models[0].name
            elif isinstance(models[0], dict) and 'name' in models[0]:
                model_name = models[0]['name']
                
            if model_name:
                logger.info(f"Calling client.show(model='{model_name}')")
                model_info = client.show(model=model_name)
                
                # Show model info
                if hasattr(model_info, 'parameters'):
                    logger.info(f"Model parameters: {model_info.parameters}")
                elif isinstance(model_info, dict) and 'parameters' in model_info:
                    logger.info(f"Model parameters: {model_info['parameters']}")
                    
                # Check for vision capability
                has_vision = False
                if hasattr(model_info, 'details') and hasattr(model_info.details, 'capabilities'):
                    capabilities = model_info.details.capabilities
                    has_vision = 'vision' in capabilities
                    logger.info(f"Capabilities: {capabilities}")
                elif isinstance(model_info, dict) and 'details' in model_info:
                    details = model_info['details']
                    if isinstance(details, dict) and 'capabilities' in details:
                        capabilities = details['capabilities']
                        has_vision = 'vision' in capabilities
                        logger.info(f"Capabilities: {capabilities}")
                        
                logger.info(f"Has vision capability: {has_vision}")
    except ImportError:
        logger.error("Ollama Python package not installed")
    except Exception as e:
        logger.error(f"Error using Ollama Python client: {e}")

if __name__ == "__main__":
    test_ollama_api_methods()
    print("\nTesting complete. Check the logs above for results.")
