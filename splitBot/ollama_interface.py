import logging
import httpx
from typing import List, Dict, Any, Optional

try:
    import ollama
    from ollama import Client, AsyncClient, ResponseError
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("Ollama package not found. Please install with 'pip install ollama'")

class OllamaInterface:
    """
    A unified interface for interacting with Ollama using the official Python library.
    This class provides a consistent way to access Ollama functionality
    throughout the agentChef package.
    """
    
    def __init__(self, model_name="llama3", host="http://localhost:11434"):
        """
        Initialize the Ollama interface.
        
        Args:
            model_name (str): Name of the Ollama model to use
            host (str): Ollama API host URL
        """
        self.model = model_name
        self.host = host
        self.logger = logging.getLogger(__name__)
        self.ollama_available = OLLAMA_AVAILABLE
        
        # Set up clients if ollama is available
        if self.ollama_available:
            try:
                self.client = Client(host=self.host)
                self.async_client = AsyncClient(host=self.host)
            except Exception as e:
                self.logger.warning(f"Could not initialize Ollama clients: {e}")
                self.ollama_available = False
    
    def chat(self, messages: List[Dict[str, str]], stream=False) -> Dict[str, Any]:
        """
        Send a chat request to Ollama.
        
        Args:
            messages (List[Dict[str, str]]): List of message objects in the format:
                [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            stream (bool): Whether to stream the response
            
        Returns:
            Dict[str, Any]: Response from Ollama or an error message
        """
        if not self.ollama_available:
            error_msg = "Ollama is not available. Please install with 'pip install ollama'"
            self.logger.error(error_msg)
            return {"error": error_msg, "message": {"content": error_msg}}
        
        try:
            return ollama.chat(model=self.model, messages=messages, stream=stream)
        except ResponseError as e:
            error_msg = f"Ollama API error: {e.error} (Status code: {e.status_code})"
            self.logger.error(error_msg)
            return {"error": error_msg, "message": {"content": error_msg}}
        except Exception as e:
            error_msg = f"Error communicating with Ollama: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg, "message": {"content": error_msg}}
    
    def embeddings(self, text: str) -> List[float]:
        """
        Generate embeddings for text using Ollama.
        
        Args:
            text (str): Text to create embeddings for
        
        Returns:
            List[float]: Embedding vector or empty list on error
        """
        if not self.ollama_available:
            self.logger.error("Ollama is not available. Please install with 'pip install ollama'")
            return []
        
        try:
            response = ollama.embed(model=self.model, input=text)
            return response.get("embedding", [])
        except Exception as e:
            self.logger.error(f"Error generating embeddings: {str(e)}")
            return []
    
    def is_available(self) -> bool:
        """
        Check if Ollama is available and working.
        
        Returns:
            bool: True if Ollama is available and working, False otherwise
        """
        if not self.ollama_available:
            return False
            
        try:
            # First try direct HTTP check which is more reliable
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.host}/api/version")
                if response.status_code == 200:
                    return True
        except Exception:
            pass
            
        # Fall back to Python package if HTTP check fails
        try:
            # Use a simple list call to check if Ollama server is responding
            self.client.list()
            return True
        except Exception as e:
            self.logger.error(f"Ollama is not accessible: {str(e)}")
            return False
    
    async def async_chat(self, messages: List[Dict[str, str]], stream=False):
        """
        Asynchronously send a chat request to Ollama.
        
        Args:
            messages (List[Dict[str, str]]): List of message objects
            stream (bool): Whether to stream the response
            
        Returns:
            Response from Ollama or async generator if streaming
        """
        if not self.ollama_available:
            error_msg = "Ollama is not available. Please install with 'pip install ollama'"
            self.logger.error(error_msg)
            return {"error": error_msg, "message": {"content": error_msg}}
        
        try:
            return await self.async_client.chat(model=self.model, messages=messages, stream=stream)
        except Exception as e:
            error_msg = f"Error in async communication with Ollama: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg, "message": {"content": error_msg}}
    
    async def list_models(self):
        """Get list of available models."""
        try:
            # First try direct HTTP API for more consistent results
            try:
                self.logger.info("Attempting to get models via HTTP API")
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(f"{self.host}/api/tags")
                    if response.status_code == 200:
                        data = response.json()
                        if 'models' in data:
                            models = [model.get('name') for model in data['models'] if 'name' in model]
                            self.logger.info(f"Found {len(models)} models via HTTP API")
                            return models or ["llama3"]
            except Exception as http_err:
                self.logger.warning(f"HTTP API model listing failed: {http_err}")
            
            # Fall back to ollama package
            self.logger.info("Calling client.list() to get available models")
            result = self.client.list()
            
            # Check if it's the new ListResponse format
            if hasattr(result, 'models'):
                models = [model.name for model in result.models if hasattr(model, 'name')]
                self.logger.info(f"Found {len(models)} models (new API format)")
            # Check if it's the list of Model objects format
            elif isinstance(result, list):
                models = [model.model for model in result if hasattr(model, 'model')]
                self.logger.info(f"Found {len(models)} models (list format)")
            # Check if it's the old format (dict with 'models' key)
            elif isinstance(result, dict) and 'models' in result:
                models = [model.get('name', 'unknown') for model in result['models'] if 'name' in model]
                self.logger.info(f"Found {len(models)} models (dict format)")
            else:
                self.logger.warning(f"Unexpected response format from client.list(): {type(result)}")
                return ["llama3"]  # Return default model if format unknown
                
            return models or ["llama3"]  # Return default if no models found
                
        except Exception as e:
            self.logger.error(f"Error listing models: {str(e)}")
            return ["llama3"]  # Return default model on error
    
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific model.
        
        Args:
            model_name (str): Name of the model to get info for
        
        Returns:
            Dict[str, Any]: Model information including capabilities
        """
        if not self.ollama_available:
            self.logger.error("Ollama is not available")
            return {}
            
        try:
            # Try direct HTTP API first with POST method
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.post(
                        f"{self.host}/api/show",
                        json={"name": model_name}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        self.logger.info(f"Got model info for {model_name} via HTTP API")
                        # Get capabilities
                        capabilities = []
                        if 'details' in data and 'capabilities' in data['details']:
                            capabilities = data['details']['capabilities']
                            
                        return {
                            'name': model_name,
                            'parameters': data.get('parameters', 'Unknown'),
                            'capabilities': capabilities,
                            'details': data.get('details', {}),
                            'has_vision': 'vision' in capabilities
                        }
            except Exception as http_err:
                self.logger.warning(f"HTTP API model info failed: {http_err}")
                
            # Fall back to ollama package with client
            model_info = self.client.show(model=model_name)
            
            # Extract capabilities
            capabilities = []
            has_vision = False
            
            if hasattr(model_info, 'details') and hasattr(model_info.details, 'capabilities'):
                capabilities = model_info.details.capabilities
                has_vision = 'vision' in capabilities
            elif isinstance(model_info, dict) and 'details' in model_info:
                details = model_info['details']
                if isinstance(details, dict) and 'capabilities' in details:
                    capabilities = details['capabilities']
                    has_vision = 'vision' in capabilities
                    
            return {
                'name': model_name,
                'parameters': getattr(model_info, 'parameters', 'Unknown') if not isinstance(model_info, dict) else model_info.get('parameters', 'Unknown'),
                'capabilities': capabilities,
                'has_vision': has_vision
            }
                
        except Exception as e:
            self.logger.error(f"Error getting model info for {model_name}: {str(e)}")
            return {
                'name': model_name,
                'error': str(e),
                'has_vision': False  # Default to no vision capability
            }
    
    def set_model(self, model_name: str):
        """Set the active model."""
        self.model = model_name
        self.logger.info(f"Set active model to: {model_name}")
        
    async def detect_vision_models(self):
        """
        Detect which models have vision capabilities.
        
        Returns:
            Tuple[List[Dict], List[Dict]]: Lists of base models and vision models
        """
        base_models = []
        vision_models = []
        
        try:
            # Get all available models
            model_names = await self.list_models()
            
            for name in model_names:
                try:
                    # Get model info including capabilities
                    info = await self.get_model_info(name)
                    
                    # Create model entry
                    model_entry = {
                        "name": name,
                        "size": info.get('parameters', 'Unknown'),
                        "family": name.split(':')[0] if ':' in name else name,
                        "is_installed": True
                    }
                    
                    # Add to appropriate list based on vision capability
                    if info.get('has_vision', False):
                        vision_models.append(model_entry)
                        self.logger.info(f"Detected vision model: {name}")
                    else:
                        base_models.append(model_entry)
                        
                except Exception as e:
                    self.logger.warning(f"Error checking model {name}: {str(e)}")
                    # Make a best guess based on name
                    model_entry = {
                        "name": name,
                        "size": "Unknown",
                        "family": name.split(':')[0] if ':' in name else name,
                        "is_installed": True
                    }
                    
                    # Simple heuristic for vision models based on name
                    if any(vision_term in name.lower() for vision_term in ['llava', 'vision', 'clip', 'visual', 'image']):
                        vision_models.append(model_entry)
                    else:
                        base_models.append(model_entry)
            
            return base_models, vision_models
            
        except Exception as e:
            self.logger.error(f"Error detecting vision models: {str(e)}")
            # Return empty lists on error
            return [], []