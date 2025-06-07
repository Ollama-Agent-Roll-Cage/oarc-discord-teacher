"""
OARC Discord Teacher Bot - Core Module

This package contains the core functionality for the Ollama Discord Teacher Bot,
providing AI-powered assistance through Discord using Ollama models.
"""

__version__ = "1.0.0"

# Import core components for easy access
from splitBot.utils import ParquetStorage, SYSTEM_PROMPT, send_in_chunks, get_user_key
from splitBot.config import DATA_DIR, MODEL_NAME, TEMPERATURE, TIMEOUT, CHANGE_NICKNAME