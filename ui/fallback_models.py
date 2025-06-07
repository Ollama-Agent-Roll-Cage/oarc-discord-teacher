"""
Fallback models for Ollama Teacher UI.
This file provides default model lists when the Ollama API is unavailable.
"""
import logging
import httpx
logger = logging.getLogger(__name__)

# Basic models that should be available in most Ollama installations
BASE_MODELS = [
    {
        "name": "llama3.1:8b",
        "size": "8.0B",
        "family": "llama",
        "quantization": "Q4_0",
        "is_installed": True
    },
    {
        "name": "llama3.2:3b",
        "size": "3.2B",
        "family": "llama",
        "quantization": "Q4_K_M",
        "is_installed": True
    },
    {
        "name": "phi3:latest",
        "size": "4B",
        "family": "llama",
        "quantization": "Q4_K_M",
        "is_installed": True
    },
    {
        "name": "phi4:latest",
        "size": "7B",
        "family": "phi",
        "quantization": "Q4_K_M",
        "is_installed": True
    },
    {
        "name": "gemma3:4b",
        "size": "3.88B",
        "family": "gemma3",
        "quantization": "Q4_K_M",
        "is_installed": True
    },
    {
        "name": "llama-guard3:8b",
        "size": "8.0B",
        "family": "llama",
        "quantization": "Q4_K_M",
        "is_installed": True
    }
]

# Vision-capable models
VISION_MODELS = [
    {
        "name": "llava:latest",
        "size": "7B",
        "family": "llama",
        "quantization": "Q4_0",
        "is_installed": True
    },
    {
        "name": "llava-phi3:latest",
        "size": "4B",
        "family": "llama",
        "quantization": "Q4_K_M",
        "is_installed": True
    },
    {
        "name": "gemma3:4b",
        "size": "3.88B",
        "family": "gemma3",
        "quantization": "Q4_K_M",
        "is_installed": True
    }
]

def get_base_models():
    """Return the list of fallback base models"""
    return BASE_MODELS

def get_vision_models():
    """Return the list of fallback vision models"""
    return VISION_MODELS

def detect_vision_models(refresh=False):
    """
    Detect vision-capable models by querying the Ollama API
    Returns: Tuple of (base_models, vision_models)
    """
    try:
        logger.info("Attempting to detect models from Ollama API")
        # First try direct API call with httpx which is more reliable
        try:
            # IMPORTANT: Use a POST request instead of GET for /api/show
            with httpx.Client(timeout=5.0) as client:
                response = client.get("http://127.0.0.1:11434/api/tags")
                if response.status_code == 200:
                    models_data = response.json()
                    model_list = models_data.get('models', [])
                    logger.info(f"Found {len(model_list)} models via direct API call")
                    
                    # Now check each model with more detailed info - using POST for /api/show
                    base_models = []
                    vision_models = []
                    
                    for model in model_list:
                        model_name = model.get('name')
                        if not model_name:
                            continue
                        
                        # Get model details using POST request instead of GET
                        try:
                            model_details = client.post(
                                "http://127.0.0.1:11434/api/show",
                                json={"name": model_name}
                            )
                            
                            if model_details.status_code == 200:
                                details_data = model_details.json()
                                
                                # Check for vision capability
                                has_vision = False
                                if 'details' in details_data:
                                    capabilities = details_data.get('details', {}).get('capabilities', [])
                                    has_vision = 'vision' in capabilities
                                
                                # Create model entry
                                model_entry = {
                                    "name": model_name,
                                    "size": details_data.get('parameters', 'Unknown'),
                                    "family": model_name.split(':')[0] if ':' in model_name else model_name,
                                    "quantization": details_data.get('details', {}).get('quantization', 'Unknown'),
                                    "is_installed": True
                                }
                                
                                # Add to appropriate list
                                if has_vision:
                                    vision_models.append(model_entry)
                                    logger.info(f"Detected vision model: {model_name}")
                                else:
                                    base_models.append(model_entry)
                            else:
                                logger.warning(f"Failed to get details for {model_name}: HTTP {model_details.status_code}")
                                # Fallback: guess based on name
                                model_entry = {
                                    "name": model_name,
                                    "size": "Unknown",
                                    "family": model_name.split(':')[0] if ':' in model_name else model_name,
                                    "quantization": "Unknown",
                                    "is_installed": True
                                }
                                
                                if any(term in model_name.lower() for term in ['llava', 'vision', 'clip', 'image', 'visual']):
                                    vision_models.append(model_entry)
                                else:
                                    base_models.append(model_entry)
                        except Exception as e:
                            logger.warning(f"Error checking model {model_name}: {str(e)}")
                            
                    if base_models or vision_models:
                        # Only use detected models if we found some
                        if not base_models:
                            base_models = BASE_MODELS
                        if not vision_models:
                            vision_models = VISION_MODELS
                        
                        return base_models, vision_models
        except Exception as e:
            logger.warning(f"Direct API call failed: {str(e)}")
        
        # If direct API fails, try using the ollama module
        import ollama
        
        # List models
        result = ollama.list()
        
        # Handle different response formats
        if hasattr(result, 'models'):
            # Newer API format
            models = result.models
            model_names = [model.name for model in models]
        elif isinstance(result, dict) and 'models' in result:
            # Older API format
            models = result['models']
            model_names = [model.get('name', 'unknown') for model in models]
        else:
            logger.warning(f"Unexpected format from ollama.list(): {type(result)}")
            return BASE_MODELS, VISION_MODELS
            
        logger.info(f"Found {len(model_names)} models from Ollama API")
        
        # Check each model for vision capabilities using ollama.show()
        base_models = []
        vision_models = []
        
        # Using client class to use POST requests
        client = ollama.Client(host="http://localhost:11434")
        
        for name in model_names:
            try:
                # Use POST request with client object
                model_info = client.show(model=name)
                
                # Extract model details
                model_entry = {
                    "name": name,
                    "size": "Unknown",
                    "family": name.split(':')[0] if ':' in name else name,
                    "quantization": "Unknown",
                    "is_installed": True
                }
                
                # Try to extract size/parameters info
                if hasattr(model_info, 'parameters'):
                    model_entry["size"] = f"{model_info.parameters}"
                elif isinstance(model_info, dict):
                    if 'parameters' in model_info:
                        model_entry["size"] = f"{model_info['parameters']}"
                    elif 'modelfile' in model_info:
                        model_entry["size"] = "Custom model"
                
                # Check for vision capability
                has_vision = False
                
                # Check in different formats
                if isinstance(model_info, dict) and 'details' in model_info:
                    details = model_info['details']
                    if isinstance(details, dict) and 'capabilities' in details:
                        capabilities = details['capabilities']
                        has_vision = 'vision' in capabilities
                elif hasattr(model_info, 'capabilities'):
                    capabilities = model_info.capabilities
                    has_vision = 'vision' in capabilities
                
                # Add to appropriate list
                if has_vision:
                    vision_models.append(model_entry)
                else:
                    base_models.append(model_entry)
                    
            except Exception as e:
                logger.warning(f"Error checking model {name}: {str(e)}")
                # Make a best guess based on name
                model_entry = {
                    "name": name,
                    "size": "Unknown",
                    "family": name.split(':')[0] if ':' in name else name,
                    "quantization": "Unknown",
                    "is_installed": True
                }
                
                if any(term in name.lower() for term in ['llava', 'vision', 'clip', 'image', 'visual']):
                    vision_models.append(model_entry)
                else:
                    base_models.append(model_entry)
        
        # If no models found, use fallbacks
        if not base_models:
            base_models = BASE_MODELS
        if not vision_models:
            vision_models = VISION_MODELS
            
        return base_models, vision_models
        
    except Exception as e:
        logger.error(f"Error detecting models: {str(e)}")
        return BASE_MODELS, VISION_MODELS
