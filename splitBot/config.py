"""
Configuration module for the Ollama Discord Teacher bot.
This centralizes all configuration settings in one place.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANGE_NICKNAME = True  # Set to True to change nickname, False to keep the default

# Ollama API configuration
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3')  # Model name for the Ollama API
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))  # Temperature setting for the AI model
TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))  # Timeout for API calls

# Data storage configuration
DATA_DIR = os.getenv('DATA_DIR', 'data')
MAX_CONVERSATION_LOG_SIZE = 50  # Maximum size of the conversation log
MAX_TEXT_ATTACHMENT_SIZE = 20000  # Maximum characters for text attachments
MAX_FILE_SIZE = 2 * 1024 * 1024  # Maximum file size in bytes (2 MB)

# Bot behavior
SYSTEM_PROMPT = """
You are a highly intelligent, friendly, and versatile learning assistant residing on Discord. 
Your primary goal is to help users learn about AI, ML, and programming concepts.
You specialize in explaining complex technical concepts in simple terms and providing code examples.
Always respond in markdown format to make your explanations clear and well-structured.
When sharing code, use appropriate markdown code blocks with language specification.
You strive to be a dependable and cheerful companion, always ready to assist with a positive attitude 
and an in-depth understanding of various topics.
"""

# Default learning resources
DEFAULT_RESOURCES = [
    "https://github.com/ollama/ollama/blob/main/docs/api.md",
    "https://pypi.org/project/ollama/",
    "https://www.npmjs.com/package/ollama",
    "https://huggingface.co/docs",
    "https://huggingface.co/docs/transformers/index",
    "https://huggingface.co/docs/hub/index",
    "https://github.com/Leoleojames1/ollama_agent_roll_cage",
    "https://arxiv.org/abs/1706.03762"  # Attention Is All You Need paper
]