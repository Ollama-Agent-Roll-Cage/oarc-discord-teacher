import os
import logging
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from datetime import datetime, timezone, UTC

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
    "https://github.com/Leoleojames1/ollama_agent_roll_cage",
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

async def send_in_chunks(ctx, text, reference=None, chunk_size=2000):
    """Sends long messages in chunks to avoid exceeding Discord's message length limit."""
    # Add debug logging
    logging.info(f"send_in_chunks called with text of length: {len(text) if text else 0}")
    logging.info(f"Text content (first 100 chars): {text[:100] if text else 'None'}")
    
    # Check if text is empty
    if not text or len(text.strip()) == 0:
        logging.warning("Empty response detected in send_in_chunks")
        await ctx.send("⚠️ No content to display. The result was empty.", reference=reference)
        return
    
    # Convert markdown to Discord-friendly format
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        # Skip empty chunks
        if not chunk or len(chunk.strip()) == 0:
            logging.warning(f"Empty chunk #{i} detected, skipping")
            continue
            
        ref = reference if i == 0 else None
        await ctx.send(chunk, reference=ref)

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
    async def execute_query(dataframe, query):
        """Execute a natural language query on a pandas DataFrame using Ollama."""
        try:
            from services import get_ollama_response
            
            # Print sample timestamp for debugging
            if 'timestamp' in dataframe.columns and not dataframe.empty:
                sample_timestamp = dataframe['timestamp'].iloc[0]
                logging.info(f"Sample timestamp format: '{sample_timestamp}'")
                logging.info(f"Timestamp dtype: {dataframe['timestamp'].dtype}")
                logging.info(f"Dataframe columns: {dataframe.columns.tolist()}")
            
            # Handle timestamp conversion as before
            try:
                # Create a custom parser function to handle both formats
                def parse_timestamp(ts):
                    if pd.isna(ts):
                        return None
                    try:
                        # Remove any timezone info before parsing
                        if '+' in ts:
                            ts_clean = ts.split('+')[0]
                            return pd.Timestamp(ts_clean)
                        else:
                            return pd.Timestamp(ts)
                    except:
                        return None
                
                # Apply the custom parser
                dataframe['parsed_timestamp'] = dataframe['timestamp'].apply(parse_timestamp)
                dataframe['date'] = dataframe['parsed_timestamp'].dt.date
                logging.info(f"Successfully converted timestamps with custom parser")
                
                # Format readable timestamps for display
                dataframe['formatted_time'] = dataframe['parsed_timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                
            except Exception as e:
                logging.error(f"Custom timestamp parsing failed: {e}")
                # Use dummy dates as a last resort
                dataframe['date'] = datetime.now(UTC).date()
                dataframe['formatted_time'] = 'Unknown'
            
            # Create a prompt that follows the llama-index pattern for PandasQueryEngine
            # We'll get the first 5 rows as a string to help the model understand the data
            df_head = dataframe.head(5).to_string()
            
            instruction_str = """
            1. Convert the query to executable Python code using Pandas.
            2. The final line of code should be a Python expression that can be called with the `eval()` function.
            3. The code should represent a solution to the query.
            4. PRINT ONLY THE EXPRESSION.
            5. Do not quote the expression.
            """
            
            prompt = f"""You are working with a pandas dataframe in Python.
            The name of the dataframe is `df`.
            This is the result of `print(df.head())`:
            {df_head}

            Follow these instructions:
            {instruction_str}
            Query: {query}

            Expression:"""
            
            # Get the pandas code to execute
            pandas_instruction = await get_ollama_response(prompt, with_context=False)
            pandas_instruction = pandas_instruction.strip()
            
            logging.info(f"Generated pandas instruction: {pandas_instruction}")
            
            # For safety, check the code doesn't have dangerous operations
            dangerous_terms = ['import', 'exec', 'eval(', 'os.', 'subprocess', 'sys.', 'shutil', 'open(']
            if any(term in pandas_instruction for term in dangerous_terms):
                return {
                    "error": "Potentially unsafe code detected",
                    "explanation": "The generated pandas code contains potentially unsafe operations."
                }
            
            # Execute the pandas code
            try:
                # Use a copy of the dataframe to avoid modifying the original
                df = dataframe.copy()
                # Execute the code and capture the result
                result = eval(pandas_instruction)
                
                # Convert the result to a string for display
                if isinstance(result, pd.DataFrame):
                    if 'parsed_timestamp' in result.columns:
                        result = result.sort_values('parsed_timestamp', ascending=False)
                    
                    # Format the output
                    if 'query' in result.columns:
                        # For search results, create a more structured table
                        display_df = result[['query', 'formatted_time']].copy()
                        display_df.columns = ['Search Query', 'Time']
                        result_str = "## Recent Searches\n\n"
                        result_str += display_df.to_string(index=False)
                    else:
                        # Generic dataframe display
                        result_str = result.to_string(index=False)
                else:
                    result_str = str(result)
                
                # Follow the llama-index pattern for returning metadata
                return {
                    "pandas_instruction_str": pandas_instruction,
                    "result": result_str,
                    "explanation": f"Found {len(result) if isinstance(result, pd.DataFrame) else 'N/A'} records matching your query."
                }
            except Exception as e:
                logging.error(f"Error executing pandas code: {e}")
                
                # Try common query patterns as fallback
                today = datetime.now(UTC).date()
                query_lower = query.lower()
                
                if 'today' in query_lower:
                    result = dataframe[dataframe['date'] == today]
                elif 'recent' in query_lower or 'show' in query_lower:
                    result = dataframe.head(10)
                elif 'count' in query_lower:
                    if 'date' in query_lower:
                        result = dataframe['date'].value_counts().head(10)
                    else:
                        result = len(dataframe)
                else:
                    result = dataframe.head(5)
                
                # Format the result
                if isinstance(result, pd.DataFrame):
                    if 'parsed_timestamp' in result.columns:
                        result = result.sort_values('parsed_timestamp', ascending=False)
                    
                    # Format the output
                    if 'query' in result.columns:
                        display_df = result[['query', 'formatted_time']].copy()
                        display_df.columns = ['Search Query', 'Time']
                        result_str = "## Recent Searches\n\n"
                        result_str += display_df.to_string(index=False)
                    else:
                        result_str = result.to_string(index=False)
                else:
                    result_str = str(result)
                
                return {
                    "code": "df.head()",  # Fallback simple code
                    "result": result_str,
                    "explanation": f"The original query failed with error: {str(e)}. Showing fallback results."
                }
                
        except Exception as e:
            logging.error(f"Error in PandasQueryEngine: {e}")
            return {
                "error": str(e),
                "explanation": f"Query engine error: {str(e)}"
            }