"""
Configuration module for the Discord Teacher Bot
"""
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Storage directory
DATA_DIR = os.getenv('DATA_DIR', 'data')
logger.info(f"DATA_DIR: {DATA_DIR}")

# Model settings
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3')
VISION_MODEL_NAME = os.getenv('OLLAMA_VISION_MODEL', 'llava')
logger.info(f"MODEL_NAME: {MODEL_NAME}")
logger.info(f"VISION_MODEL_NAME: {VISION_MODEL_NAME}")

# Behavior settings
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))
TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))
CHANGE_NICKNAME = os.getenv('CHANGE_NICKNAME', 'True').lower() in ('true', '1', 't', 'yes')
logger.info(f"TEMPERATURE: {TEMPERATURE}")
logger.info(f"TIMEOUT: {TIMEOUT}")
logger.info(f"CHANGE_NICKNAME: {CHANGE_NICKNAME}")

# Optional Groq API settings
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3-8b-8192')
if GROQ_API_KEY:
    logger.info(f"GROQ_MODEL: {GROQ_MODEL}")
    logger.info("GROQ_API_KEY is set")
else:
    logger.info("GROQ_API_KEY is not set, Groq features will be unavailable")

# System prompt
SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT', """
You are Ollama Teacher, a friendly AI assistant focused on AI, machine learning, and programming topics.

As an assistant:
- Respond directly to questions with clear, helpful information
- Be conversational and personable while staying focused on the user's query
- Format output using markdown when appropriate for clarity
- Provide code examples when relevant, properly formatted in code blocks
- Address users by name when available
""".strip())

# Maximum message sizes
MAX_CONVERSATION_LOG_SIZE = int(os.getenv('MAX_CONVERSATION_LOG_SIZE', '50'))
MAX_TEXT_ATTACHMENT_SIZE = int(os.getenv('MAX_TEXT_ATTACHMENT_SIZE', '20000'))
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', str(2 * 1024 * 1024)))  # 2MB default

def update_config(updates):
    """Update configuration variables with new values"""
    global MODEL_NAME, VISION_MODEL_NAME, TEMPERATURE, TIMEOUT, CHANGE_NICKNAME
    global GROQ_API_KEY, GROQ_MODEL, SYSTEM_PROMPT, DATA_DIR
    
    # Update values if provided
    if 'MODEL_NAME' in updates:
        MODEL_NAME = updates['MODEL_NAME']
        os.environ['OLLAMA_MODEL'] = MODEL_NAME
        
    if 'VISION_MODEL_NAME' in updates:
        VISION_MODEL_NAME = updates['VISION_MODEL_NAME'] 
        os.environ['OLLAMA_VISION_MODEL'] = VISION_MODEL_NAME
        
    if 'TEMPERATURE' in updates:
        TEMPERATURE = float(updates['TEMPERATURE'])
        os.environ['TEMPERATURE'] = str(TEMPERATURE)
        
    if 'TIMEOUT' in updates:
        TIMEOUT = float(updates['TIMEOUT'])
        os.environ['TIMEOUT'] = str(TIMEOUT)
        
    if 'CHANGE_NICKNAME' in updates:
        CHANGE_NICKNAME = updates['CHANGE_NICKNAME']
        os.environ['CHANGE_NICKNAME'] = str(CHANGE_NICKNAME)
        
    if 'GROQ_API_KEY' in updates:
        GROQ_API_KEY = updates['GROQ_API_KEY']
        if GROQ_API_KEY:
            os.environ['GROQ_API_KEY'] = GROQ_API_KEY
            
    if 'GROQ_MODEL' in updates:
        GROQ_MODEL = updates['GROQ_MODEL']
        os.environ['GROQ_MODEL'] = GROQ_MODEL
        
    if 'SYSTEM_PROMPT' in updates:
        SYSTEM_PROMPT = updates['SYSTEM_PROMPT']
        os.environ['SYSTEM_PROMPT'] = SYSTEM_PROMPT
        
    if 'DATA_DIR' in updates:
        DATA_DIR = updates['DATA_DIR']
        os.environ['DATA_DIR'] = DATA_DIR
        
    logger.info(f"Configuration updated: {', '.join(updates.keys())}")
    return True