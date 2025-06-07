import os
import logging
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import asyncio
from pathlib import Path
from datetime import datetime, timezone, UTC
from tabulate import tabulate
import re
import sys

# System prompt for initializing the conversation
SYSTEM_PROMPT = """
You are Ollama Teacher, a friendly AI assistant focused on AI, machine learning, and programming topics.

As an assistant:
- Respond directly to questions with clear, helpful information
- Be conversational and personable while staying focused on the user's query
- Format output using markdown when appropriate for clarity
- Provide code examples when relevant, properly formatted in code blocks
- Address users by name when available
"""

# Constants
MAX_CONVERSATION_LOG_SIZE = 50  # Maximum size of the conversation log (including the system prompt)
MAX_TEXT_ATTACHMENT_SIZE = 20000  # Maximum combined characters for text attachments
MAX_FILE_SIZE = 2 * 1024 * 1024  # Maximum file size in bytes (2 MB)

# Default learning resources
DEFAULT_RESOURCES = [
    "https://github.com/ollama/ollama/blob/main/docs/api.md",
    "https://pypi.org/project/ollama/",
    "https://www.npmjs.com/package/ollama",
    "https://huggingface.co/docs",
    "https://huggingface.co/docs/transformers/index",
    "https://huggingface.co/docs/hub/index",
    "https://github.com/Ollama-Agent-Roll-Cage/oarc",
    "https://arxiv.org/abs/1706.03762"  # Attention Is All You Need paper
]

# ---------- Helper Functions ----------

def is_text_file(file_content):
    """Determine if the file content can be read as text."""
    try:
        file_content.decode('utf-8')
        return True
    except (UnicodeDecodeError, AttributeError):
        return False

async def send_in_chunks(ctx, text, reference=None, chunk_size=1950):
    """Sends long messages in chunks to avoid exceeding Discord's message length limit."""
    # Add debug logging
    logging.info(f"send_in_chunks called with text of length: {len(text) if text else 0}")
    
    # Check if text is empty
    if not text or len(text.strip()) == 0:
        logging.warning("Empty response detected in send_in_chunks")
        await ctx.send("⚠️ No content to display. The result was empty.", reference=reference)
        return
    
    # Find natural breakpoints for chunks (paragraphs, headers, code blocks)
    natural_breaks = [
        "\n\n", "\n## ", "\n# ", "```\n",
        "\n- ", "\n1. ", "\n---", "\n***"
    ]
    
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first
    paragraphs = re.split(r'(\n\n|\n#+\s|\n---|\n\*\*\*|\n```)', text)
    
    for i in range(0, len(paragraphs), 2):
        paragraph = paragraphs[i] if i < len(paragraphs) else ""
        delimiter = paragraphs[i+1] if i+1 < len(paragraphs) else ""
        
        # If adding this paragraph would exceed chunk size, start a new chunk
        if len(current_chunk) + len(paragraph) + len(delimiter) > chunk_size:
            chunks.append(current_chunk)
            current_chunk = paragraph + delimiter
        else:
            current_chunk += paragraph + delimiter
    
    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    # If chunking didn't work well, use simpler approach
    if not chunks:
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        # Skip empty chunks
        if not chunk or len(chunk.strip()) == 0:
            logging.warning(f"Empty chunk #{i} detected, skipping")
            continue
        
        # Add continuation marker for clarity
        if i > 0:
            chunk = "(continued) " + chunk
        
        # Add unfinished marker if needed
        if i < len(chunks) - 1:
            if not chunk.endswith("\n"):
                chunk += "\n"
            chunk += "_(continued in next message)_"
            
        ref = reference if i == 0 else None
        try:
            await ctx.send(chunk, reference=ref)
            # Small delay between chunks to prevent rate limiting
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"Error sending chunk #{i}: {e}")
            try:
                await ctx.send(f"⚠️ Error sending part of the response. Please try again or use a shorter query.")
            except:
                pass

def get_user_key(ctx_or_message):
    """Generate a unique key for user storage.
    Works with both Context and Message objects."""
    try:
        # Handle both Context and Message objects
        if hasattr(ctx_or_message, 'guild'):
            # It's a Context object
            guild = ctx_or_message.guild
            author = ctx_or_message.author
        else:
            # It's a Message object
            guild = ctx_or_message.guild
            author = ctx_or_message.author
            
        # Handle DMs (no guild)
        if guild is None:
            return f"dm_{author.id}"
            
        return f"{guild.id}_{author.id}"
        
    except Exception as e:
        logging.error(f"Error generating user key: {e}")
        # Fallback to just user ID if there's an error
        return f"user_{ctx_or_message.author.id}"

async def store_user_conversation(message, content, is_bot=False):
    """Store user conversation with metadata."""
    try:
        # Get user_key
        user_key = get_user_key(message)
        
        # Import module variables from main.py
        from main import USER_CONVERSATIONS, USER_PROFILES_DIR
            
        timestamp = datetime.now(UTC).isoformat()
        
        conversation_entry = {
            'role': 'assistant' if is_bot else 'user',
            'content': content,
            'timestamp': timestamp
        }
        
        # Make sure we're adding to the right user's conversation
        USER_CONVERSATIONS[user_key].append(conversation_entry)
        
        # Create a basic profile if one doesn't exist
        profile_path = os.path.join(USER_PROFILES_DIR, f"{user_key}_profile.json")
        if not os.path.exists(profile_path):
            profile_data = {
                'timestamp': timestamp,
                'analysis': 'Profile is being built as you interact more.',
                'username': message.author.display_name or message.author.name
            }
            
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2)
        
    except Exception as e:
        logging.error(f"Error storing conversation: {e}")

async def process_file_attachment(attachment):
    """Process a file attachment and return its content."""
    if attachment.size > MAX_FILE_SIZE:
        raise ValueError(f"File too large (max {MAX_FILE_SIZE/1024/1024}MB)")
        
    # Get file extension
    ext = attachment.filename.lower().split('.')[-1] if '.' in attachment.filename else ''
    
    try:
        content = await attachment.read()
        if is_text_file(content):
            text = content.decode('utf-8')
            
            # Format based on file type
            if ext in ['py', 'python']:
                return f"```python\n{text}\n```"
            elif ext in ['md', 'markdown']:
                return text
            else:
                return f"```\n{text}\n```"
        else:
            raise ValueError("File must be a text file")
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")

async def process_image_attachment(attachment):
    """Process an image attachment and return its base64 data."""
    if attachment.size > MAX_FILE_SIZE:
        raise ValueError(f"Image too large (max {MAX_FILE_SIZE/1024/1024}MB)")
        
    # Get file extension
    ext = attachment.filename.lower().split('.')[-1]
    
    if ext not in ['png', 'jpg', 'jpeg', 'webp']:
        raise ValueError("Invalid image format. Supported: PNG, JPG, JPEG, WEBP")
        
    try:
        # Download and convert to base64
        image_data = await attachment.read()
        return image_data
    except Exception as e:
        raise ValueError(f"Error processing image: {str(e)}")

# ---------- Parquet Storage ----------

class ParquetStorage:
    @staticmethod
    def save_to_parquet(data, file_path):
        """Save data to a Parquet file."""
        try:
            # Convert to DataFrame if it's a dictionary
            if isinstance(data, dict):
                df = pd.DataFrame([data])
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = data
                
            # Save to Parquet
            pq.write_table(pa.Table.from_pandas(df), file_path)
            logging.info(f"Data saved to {file_path}")
            return True
        except Exception as e:
            logging.error(f"Error saving to Parquet: {e}")
            return False
            
    @staticmethod
    def load_from_parquet(file_path):
        """Load data from a Parquet file."""
        try:
            if not os.path.exists(file_path):
                return None
                
            table = pq.read_table(file_path)
            df = table.to_pandas()
            return df
        except Exception as e:
            logging.error(f"Error loading from Parquet: {e}")
            return None
            
    @staticmethod
    def append_to_parquet(data, file_path):
        """Append data to an existing Parquet file or create a new one."""
        try:
            # Load existing data if available
            if os.path.exists(file_path):
                existing_df = ParquetStorage.load_from_parquet(file_path)
                if existing_df is not None:
                    # Convert new data to DataFrame
                    if isinstance(data, dict):
                        new_df = pd.DataFrame([data])
                    elif isinstance(data, list):
                        new_df = pd.DataFrame(data)
                    else:
                        new_df = data
                        
                    # Combine and save
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                    return ParquetStorage.save_to_parquet(combined_df, file_path)
            
            # If file doesn't exist or loading failed, create new file
            return ParquetStorage.save_to_parquet(data, file_path)
        except Exception as e:
            logging.error(f"Error appending to Parquet: {e}")
            return False

# ---------- Pandas Query Engine ----------

class PandasQueryEngine:
    @staticmethod
    async def execute_query(dataframe, query, model_name=None):
        """Execute a natural language query on a pandas DataFrame"""
        try:
            # First ensure we have proper timestamp handling
            if 'timestamp' in dataframe.columns and not dataframe.empty:
                dataframe['parsed_timestamp'] = pd.to_datetime(dataframe['timestamp'], utc=True)
                dataframe['date'] = dataframe['parsed_timestamp'].dt.date
                
            # For now, just return basic info about the dataframe
            result = {
                "success": True,
                "result": f"DataFrame with {len(dataframe)} rows and {len(dataframe.columns)} columns",
                "columns": list(dataframe.columns)
            }
            return result

        except Exception as e:
            logging.error(f"PandasQueryEngine error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }