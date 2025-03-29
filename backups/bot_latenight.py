import os
import asyncio
from dotenv import load_dotenv
from discord import Intents, Message, Embed, Color, File, Game, Status
from discord.ext import commands, tasks
import ollama
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import re
import time
import aiohttp
from datetime import datetime, timezone, UTC  # Import UTC from datetime
import markdown
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import json
from bs4 import BeautifulSoup
from collections import defaultdict

# Load environment variables from .env file
load_dotenv()

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Boolean variable to control whether to change the bot's nickname
CHANGE_NICKNAME = True  # Set to True to change nickname, False to keep the default

# Configuration variables
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_DIR = os.getenv('DATA_DIR', 'data')

MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3')  # Model name for the Ollama API
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))  # Temperature setting for the AI model
TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))  # Timeout setting for the API call

# Create data directory if it doesn't exist
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/searches").mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/papers").mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/crawls").mkdir(parents=True, exist_ok=True)

# System prompt for initializing the conversation
SYSTEM_PROMPT = """
You are a highly intelligent, friendly, and versatile learning assistant residing on Discord. 
Your primary goal is to help users learn about AI, ML, and programming concepts.
You specialize in explaining complex technical concepts in simple terms and providing code examples.
Always respond in markdown format to make your explanations clear and well-structured.
When sharing code, use appropriate markdown code blocks with language specification.
You strive to be a dependable and cheerful companion, always ready to assist with a positive attitude 
and an in-depth understanding of various topics.
"""

MAX_CONVERSATION_LOG_SIZE = 50  # Maximum size of the conversation log (including the system prompt)
MAX_TEXT_ATTACHMENT_SIZE = 20000  # Maximum combined characters for text attachments
MAX_FILE_SIZE = 2 * 1024 * 1024  # Maximum file size in bytes (2 MB)

# Configure bot intents
intents = Intents.default()
intents.message_content = True

def get_prefix(bot, message):
    """Get the command prefix for the bot."""
    # Only respond to commands if the bot is mentioned
    if bot.user and bot.user.mentioned_in(message):
        content = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
        if content.startswith('!'):
            return '!'
    return commands.when_mentioned(bot, message)

# Initialize the bot
bot = commands.Bot(command_prefix=get_prefix, intents=intents)

# Add this near the top of your file, after initializing the bot
bot.remove_command('help')  # Remove the default help command

# Global list to store conversation logs, starting with the system prompt
conversation_logs = [{'role': 'system', 'content': SYSTEM_PROMPT}]

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

# Add these global variables after other configurations
USER_CONVERSATIONS = defaultdict(lambda: [{'role': 'system', 'content': SYSTEM_PROMPT}])
COMMAND_MEMORY = defaultdict(dict)  # Stores persistent memory for commands
USER_PROFILES_DIR = os.path.join(DATA_DIR, 'user_profiles')
Path(USER_PROFILES_DIR).mkdir(parents=True, exist_ok=True)

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
    # Convert markdown to Discord-friendly format
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        ref = reference if i == 0 else None
        await ctx.send(chunk, reference=ref)

async def get_ollama_response(prompt, with_context=True):
    """Gets a response from the Ollama model."""
    try:
        if with_context:
            messages_to_send = conversation_logs.copy()
        else:
            messages_to_send = [{'role': 'system', 'content': SYSTEM_PROMPT}, 
                               {'role': 'user', 'content': prompt}]
            
        response = await asyncio.wait_for(
            ollama.AsyncClient(timeout=TIMEOUT).chat(
                model=MODEL_NAME,
                messages=messages_to_send,
                options={'temperature': TEMPERATURE}
            ),
            timeout=TIMEOUT
        )
        return response['message']['content']
    except asyncio.TimeoutError:
        return "The request timed out. Please try again."
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return f"An error occurred: {e}"

# Add this helper function
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
        # Get user_key based on whether it's a DM or guild message
        if message.guild:
            user_key = f"{message.guild.id}_{message.author.id}"
            guild_id = message.guild.id
        else:
            user_key = f"dm_{message.author.id}"
            guild_id = None
            
        timestamp = datetime.now(UTC).isoformat()
        
        conversation_entry = {
            'role': 'assistant' if is_bot else 'user',
            'content': content,
            'timestamp': timestamp,
            'user_id': message.author.id,
            'guild_id': guild_id,
            'username': message.author.display_name or message.author.name,
            'is_dm': guild_id is None
        }
        
        USER_CONVERSATIONS[user_key].append(conversation_entry)
        
    except Exception as e:
        logging.error(f"Error storing conversation: {e}")

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
            logger.info(f"Data saved to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving to Parquet: {e}")
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
            logger.error(f"Error loading from Parquet: {e}")
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
            logger.error(f"Error appending to Parquet: {e}")
            return False

# ---------- Pandas Query Engine ----------

class PandasQueryEngine:
    @staticmethod
    async def execute_query(dataframe, query):
        """Execute a natural language query on a pandas DataFrame using Ollama."""
        try:
            # Create datetime column for filtering
            dataframe['date'] = pd.to_datetime(dataframe['timestamp']).dt.strftime('%Y-%m-%d')
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Clean up content for display if it exists
            if 'content' in dataframe.columns:
                # Remove HTML tags and clean up whitespace
                dataframe['display_content'] = dataframe['content'].apply(lambda x: 
                    BeautifulSoup(x, 'html.parser').get_text(separator=' ', strip=True)[:200] + '...' 
                    if isinstance(x, str) else '')
            
            # Common query patterns
            query_lower = query.lower()
            
            if 'today' in query_lower:
                result = dataframe[dataframe['date'] == today]
            elif 'recent' in query_lower:
                result = dataframe.head(10)
            elif 'count' in query_lower:
                if 'date' in query_lower:
                    result = dataframe['date'].value_counts().head(10)
                else:
                    result = dataframe['url'].value_counts().head(10)
            else:
                result = dataframe.head(5)
            
            # Sort by timestamp
            if isinstance(result, pd.DataFrame):
                result = result.sort_values('timestamp', ascending=False)
                
                # Format the output columns
                if 'content' in result.columns:
                    # For crawled pages, show URL and preview
                    display_cols = ['url', 'timestamp', 'display_content']
                    result = result[display_cols].copy()
                    result.columns = ['URL', 'Timestamp', 'Content Preview']
            
            # Format result based on type
            if isinstance(result, pd.DataFrame):
                if len(result) > 0:
                    result_str = result.to_string(index=False)
                else:
                    result_str = "No matching results found"
            else:
                result_str = result.to_string()
            
            return {
                "code": "df.sort_values('timestamp', ascending=False)",
                "result": result_str,
                "explanation": f"Showing {'all' if len(result) < 5 else 'top'} results ordered by time"
            }
                
        except Exception as e:
            logging.error(f"Error in PandasQueryEngine: {e}")
            return {
                "error": str(e),
                "explanation": f"Query engine error: {str(e)}"
            }

# ---------- ArXiv Integration ----------

class ArxivSearcher:
    @staticmethod
    def extract_arxiv_id(url_or_id):
        """Extract arXiv ID from a URL or direct ID string."""
        patterns = [
            r'arxiv.org/abs/([\w.-]+)',
            r'arxiv.org/pdf/([\w.-]+)',
            r'^([\w.-]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
        
        raise ValueError("Could not extract arXiv ID from the provided input")

    @staticmethod
    async def fetch_paper_info(arxiv_id):
        """Fetch paper metadata from arXiv API."""
        base_url = 'http://export.arxiv.org/api/query'
        query_params = {
            'id_list': arxiv_id,
            'max_results': 1
        }
        
        url = f"{base_url}?{urllib.parse.urlencode(query_params)}"
        
        try:
            with urllib.request.urlopen(url) as response:
                xml_data = response.read().decode('utf-8')
            
            root = ET.fromstring(xml_data)
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            entry = root.find('atom:entry', namespaces)
            if entry is None:
                raise ValueError("No paper found with the provided ID")
            
            paper_info = {
                'arxiv_id': arxiv_id,
                'title': entry.find('atom:title', namespaces).text.strip(),
                'authors': [author.find('atom:name', namespaces).text 
                           for author in entry.findall('atom:author', namespaces)],
                'abstract': entry.find('atom:summary', namespaces).text.strip(),
                'published': entry.find('atom:published', namespaces).text,
                'pdf_link': next(
                    link.get('href') for link in entry.findall('atom:link', namespaces)
                    if link.get('type') == 'application/pdf'
                ),
                'arxiv_url': next(
                    link.get('href') for link in entry.findall('atom:link', namespaces)
                    if link.get('rel') == 'alternate'
                ),
                'categories': [cat.get('term') for cat in entry.findall('atom:category', namespaces)],
                'timestamp': datetime.now(UTC).isoformat()
            }
            
            # Add optional fields if present
            optional_fields = ['comment', 'journal_ref', 'doi']
            for field in optional_fields:
                elem = entry.find(f'arxiv:{field}', namespaces)
                if elem is not None:
                    paper_info[field] = elem.text
                    
            # Save paper info to Parquet
            file_path = f"{DATA_DIR}/papers/{arxiv_id}.parquet"
            ParquetStorage.save_to_parquet(paper_info, file_path)
            
            # Also append to all papers list
            all_papers_path = f"{DATA_DIR}/papers/all_papers.parquet"
            ParquetStorage.append_to_parquet(paper_info, all_papers_path)
            
            return paper_info
            
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to arXiv API: {e}")
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse API response: {e}")

    @staticmethod
    async def format_paper_for_learning(paper_info):
        """Format paper information for the learning bot."""
        formatted_text = f"""# {paper_info['title']}

**Authors:** {', '.join(paper_info['authors'])}

**Published:** {paper_info['published'][:10]}

**Categories:** {', '.join(paper_info['categories'])}

## Abstract
{paper_info['abstract']}

**Links:**
- [ArXiv Page]({paper_info['arxiv_url']})
- [PDF Download]({paper_info['pdf_link']})
"""
        if 'comment' in paper_info and paper_info['comment']:
            formatted_text += f"\n**Comments:** {paper_info['comment']}\n"
            
        if 'journal_ref' in paper_info and paper_info['journal_ref']:
            formatted_text += f"\n**Journal Reference:** {paper_info['journal_ref']}\n"
            
        if 'doi' in paper_info and paper_info['doi']:
            formatted_text += f"\n**DOI:** {paper_info['doi']}\n"
            
        return formatted_text

# ---------- DuckDuckGo Search Integration ----------

class DuckDuckGoSearcher:
    @staticmethod
    async def text_search(search_query, max_results=5):
        """Perform an async text search using DuckDuckGo."""
        try:
            encoded_query = urllib.parse.quote(search_query)
            url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&pretty=1"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        result_text = await response.text()
                        try:
                            results = json.loads(result_text)
                            
                            # Save search results to Parquet
                            search_data = {
                                'query': search_query,
                                'timestamp': datetime.now(UTC).isoformat(),
                                'raw_results': result_text
                            }
                            
                            # Generate a filename from the query
                            filename = re.sub(r'[^\w]', '_', search_query)[:50]
                            file_path = f"{DATA_DIR}/searches/{filename}_{int(datetime.now().timestamp())}.parquet"
                            ParquetStorage.save_to_parquet(search_data, file_path)
                            
                            # Format the response nicely for Discord
                            formatted_results = "# DuckDuckGo Search Results\n\n"
                            
                            if 'AbstractText' in results and results['AbstractText']:
                                formatted_results += f"## Summary\n{results['AbstractText']}\n\n"
                                
                            if 'RelatedTopics' in results:
                                formatted_results += "## Related Topics\n\n"
                                count = 0
                                for topic in results['RelatedTopics']:
                                    if count >= max_results:
                                        break
                                    if 'Text' in topic and 'FirstURL' in topic:
                                        formatted_results += f"- [{topic['Text']}]({topic['FirstURL']})\n"
                                        count += 1
                            
                            return formatted_results
                        except json.JSONDecodeError:
                            return "Error: Could not parse the search results."
                    else:
                        return f"Error: Received status code {response.status} from DuckDuckGo API."
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return f"An error occurred during the search: {str(e)}"

# ---------- Web Crawling Integration ----------

class WebCrawler:
    @staticmethod
    async def extract_pypi_content(html, package_name):
        """Specifically extract PyPI package documentation from HTML."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract package metadata from the sidebar
            metadata = {}
            sidebar = soup.find('div', {'class': 'sidebar'})
            if (sidebar):
                for section in sidebar.find_all('div', {'class': 'sidebar-section'}):
                    title_elem = section.find(['h3', 'h4'])
                    if title_elem:
                        section_title = title_elem.get_text().strip()
                        content_list = []
                        for p in section.find_all('p'):
                            content_list.append(p.get_text().strip())
                        metadata[section_title] = content_list
            
            # Find the project description section which contains the actual documentation
            description_div = soup.find('div', {'class': 'project-description'})
            
            if (description_div):
                # Extract text while preserving structure
                content = ""
                for element in description_div.children:
                    if hasattr(element, 'name'):  # Check if it's a tag
                        if element.name in ['h1', 'h2', 'h3', 'h4']:
                            heading_level = int(element.name[1])
                            heading_text = element.get_text().strip()
                            content += f"{'#' * heading_level} {heading_text}\n\n"
                        elif element.name == 'p':
                            content += f"{element.get_text().strip()}\n\n"
                        elif element.name == 'pre':
                            code = element.get_text().strip()
                            # Detect if there's a code element inside
                            code_element = element.find('code')
                            language = "python" if code_element and 'python' in str(code_element.get('class', [])).lower() else ""
                            content += f"```{language}\n{code}\n```\n\n"
                        elif element.name == 'ul':
                            for li in element.find_all('li', recursive=False):
                                content += f"- {li.get_text().strip()}\n"
                            content += "\n"
                
                # Construct a structured representation
                package_info = {
                    'name': package_name,
                    'metadata': metadata,
                    'documentation': content
                }
                
                return package_info
            else:
                return None
        except Exception as e:
            logging.error(f"Error extracting PyPI content: {e}")
            return None
    
    @staticmethod
    async def format_pypi_info(package_data):
        """Format PyPI package data into a readable markdown format."""
        if not package_data:
            return "Could not retrieve package information."
        
        info = package_data.get('info', {})
        
        # Basic package information
        name = info.get('name', 'Unknown')
        version = info.get('version', 'Unknown')
        summary = info.get('summary', 'No summary available')
        description = info.get('description', 'No description available')
        author = info.get('author', 'Unknown')
        author_email = info.get('author_email', 'No email available')
        home_page = info.get('home_page', '')
        project_urls = info.get('project_urls', {})
        requires_dist = info.get('requires_dist', [])
        
        # Format the markdown response
        md = f"""# {name} v{version}

        ## Summary
        {summary}

        ## Basic Information
        - **Author**: {author} ({author_email})
        - **License**: {info.get('license', 'Not specified')}
        - **Homepage**: {home_page}

        ## Project URLs
        """
        
        for name, url in project_urls.items():
            md += f"- **{name}**: {url}\n"
        
        md += "\n## Dependencies\n"
        
        if requires_dist:
            for dep in requires_dist:
                md += f"- {dep}\n"
        else:
            md += "No dependencies listed.\n"
        
        md += "\n## Quick Install\n```\npip install " + name + "\n```\n"
        
        # Truncate the description if it's too long
        if len(description) > 1000:
            short_desc = description[:1000] + "...\n\n(Description truncated for brevity)"
            md += f"\n## Description Preview\n{short_desc}"
        else:
            md += f"\n## Description\n{description}"
        
        return md
    
    @staticmethod
    async def fetch_url_content(url):
        """Fetch content from a URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Save crawled content
                        crawl_data = {
                            'url': url,
                            'timestamp': datetime.now(UTC).isoformat(),
                            'content': html[:100000]  # Limit content size
                        }
                        
                        # Generate a filename from the URL
                        filename = re.sub(r'[^\w]', '_', url.split('//')[-1])[:50]
                        file_path = f"{DATA_DIR}/crawls/{filename}_{int(datetime.now().timestamp())}.parquet"
                        ParquetStorage.save_to_parquet(crawl_data, file_path)
                        
                        return html
                    else:
                        return None
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return None

    # Then update the WebCrawler.extract_text_from_html method
    @staticmethod
    async def extract_text_from_html(html):
        """Extract main text content from HTML using BeautifulSoup."""
        if html:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.extract()
                    
                # Get text
                text = soup.get_text(separator=' ', strip=True)
                
                # Clean up whitespace
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Limit to first ~10,000 characters
                return text[:15000] + ("..." if len(text) > 15000 else "")
            except Exception as e:
                logging.error(f"Error parsing HTML: {e}")
                # Fall back to regex method if BeautifulSoup fails
                clean_html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
                clean_html = re.sub(r'<style.*?>.*?</style>', '', clean_html, flags=re.DOTALL)
                text = re.sub(r'<.*?>', ' ', clean_html)
                text = re.sub(r'\s+', ' ', text).strip()
                return text[:10000] + ("..." if len(text) > 10000 else "")
        return "Failed to extract text from the webpage."

# ---------- Bot Commands ----------

@bot.command(name='reset')
async def reset(ctx):
    """Resets the user's conversation log."""
    user_key = get_user_key(ctx)
    USER_CONVERSATIONS[user_key] = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    COMMAND_MEMORY[user_key].clear()
    await ctx.send("✅ Your conversation context has been reset.")

@bot.command(name='globalReset')
async def global_reset(ctx):
    """Resets all conversation logs (admin only)."""
    if not ctx.author.guild_permissions.administrator and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("⚠️ Only server administrators and owner can use this command.")
        return
        
    USER_CONVERSATIONS.clear()
    COMMAND_MEMORY.clear()
    await ctx.send("🔄 Global conversation context has been reset.")

@bot.command(name='help')
async def help_command(ctx):
    """Display help information."""
    help_text = """# 🤖 Ollama Teacher Bot Commands

## Personal Commands
- `!profile` - View your learning profile
- `!profile <question>` - Ask about your learning history
- `!reset` - Clear your conversation history

## AI-Powered Commands
- `!arxiv <arxiv_url_or_id> [--memory] <question>` - Learn from ArXiv papers
- `!ddg <query> <question>` - Search DuckDuckGo and learn
- `!crawl <url> <question>` - Learn from web pages
- `!pandas <query>` - Query stored data

## Admin Commands
- `!globalReset` - Reset all conversations (admin only)

## Chat Mode
- Mention the bot without commands to start a conversation
- Example: @Ollama Teacher What is machine learning?

## Examples
```
!profile                                    # View your profile
!profile What topics have I been learning?  # Ask about your progress
!arxiv --memory 1706.03762 Tell me about attention mechanisms
!ddg "python asyncio" How to use async/await?
!crawl https://pypi.org/project/ollama/ How to use this package?
```
"""
    await send_in_chunks(ctx, help_text)

@bot.command(name='learn')
async def learn_default(ctx):
    """Show default learning resources."""
    resources_text = """# 📚 Learning Resources

## Documentation
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Ollama Python](https://pypi.org/project/ollama/)
- [Hugging Face](https://huggingface.co/docs)
- [Transformers](https://huggingface.co/docs/transformers/index)

## Key Papers
- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)

## Commands to Try
```
!arxiv 1706.03762 What is self-attention?
!ddg "ollama api" How do I use it?
!crawl https://pypi.org/project/ollama/ Usage examples?
```

## Study Tips
1. Start with official documentation
2. Try code examples
3. Ask specific questions
4. Practice with examples
"""
    await send_in_chunks(ctx, resources_text)

@bot.command(name='arxiv')
async def arxiv_search(ctx, arxiv_ids: str, *, question: str = None):
    """Search for multiple ArXiv papers and learn from them."""
    try:
        # Check for memory flag
        user_key = get_user_key(ctx)
        use_memory = '--memory' in arxiv_ids
        arxiv_ids = arxiv_ids.replace('--memory', '').strip()
        
        async with ctx.typing():
            # Get previous context if using memory
            previous_context = COMMAND_MEMORY[user_key].get('arxiv', '') if use_memory else ''
            
            # Split IDs by space or comma
            id_list = re.split(r'[,\s]+', arxiv_ids.strip())
            all_papers = []
            
            for arxiv_id_or_url in id_list:
                try:
                    arxiv_id = ArxivSearcher.extract_arxiv_id(arxiv_id_or_url.strip())
                    
                    # Check cache
                    paper_file = f"{DATA_DIR}/papers/{arxiv_id}.parquet"
                    existing_paper = ParquetStorage.load_from_parquet(paper_file)
                    
                    if existing_paper is not None and len(existing_paper) > 0:
                        paper_info = existing_paper.iloc[0].to_dict()
                        logger.info(f"Using cached paper info for {arxiv_id}")
                    else:
                        paper_info = await ArxivSearcher.fetch_paper_info(arxiv_id)
                        
                    paper_text = await ArxivSearcher.format_paper_for_learning(paper_info)
                    all_papers.append({"id": arxiv_id, "content": paper_text})
                    
                    # Store the paper details in user's memory if memory flag is used
                    if use_memory:
                        memory_key = f"paper_{arxiv_id}"
                        COMMAND_MEMORY[user_key][memory_key] = paper_text
                        
                except Exception as e:
                    logger.error(f"Error processing {arxiv_id_or_url}: {e}")
                    await ctx.send(f"⚠️ Error with {arxiv_id_or_url}: {str(e)}")
            
            if not all_papers:
                await ctx.send("Could not process any of the provided ArXiv papers")
                return
                
            if question:
                # Include previous context in prompt if memory is enabled
                combined_prompt = ""
                if use_memory and previous_context:
                    combined_prompt = f"""Previous context:
{previous_context}

New papers to analyze:
"""
                
                combined_prompt += "I want to learn from these research papers:\n\n"
                for paper in all_papers:
                    combined_prompt += f"Paper {paper['id']}:\n{paper['content']}\n\n"
                combined_prompt += f"\nMy question is: {question}\n\nPlease provide a detailed answer using information from all papers."
                
                if use_memory:
                    combined_prompt += "\n\nIncorporate relevant information from previously discussed papers if available."
                
                ai_response = await get_ollama_response(combined_prompt, with_context=False)
                
                # Store context if using memory
                if use_memory:
                    COMMAND_MEMORY[user_key]['arxiv'] = combined_prompt + f"\n\nAnswer: {ai_response}"
                
                # Format response with memory indicator
                response_text = f"""{'🧠 Using Memory: Previous context incorporated\n\n' if use_memory and previous_context else ''}# ArXiv Paper Analysis

**Papers analyzed:** {', '.join(p['id'] for p in all_papers)}
{f'**Memory active:** Previous context from {len(previous_context.split()) // 100} discussions' if use_memory and previous_context else ''}

{ai_response}

{'> Use !reset to clear your memory context' if use_memory else '> Add --memory flag to enable persistent memory'}"""
                
                await send_in_chunks(ctx, response_text, reference=ctx.message)
            else:
                # Send each paper's information
                for paper in all_papers:
                    header = "🧠 Memory Stored: " if use_memory else ""
                    await send_in_chunks(ctx, header + paper['content'], reference=ctx.message)
            
            # Store conversation in user history
            await store_user_conversation(
                ctx.author.id, 
                ctx.guild.id, 
                f"Asked about ArXiv papers: {arxiv_ids}" + (f" with question: {question}" if question else ""),
                is_bot=False
            )
            
            if ai_response:
                await store_user_conversation(
                    ctx.author.id,
                    ctx.guild.id,
                    ai_response,
                    is_bot=True
                )
                
    except Exception as e:
        logging.error(f"Error in arxiv_search: {e}")
        await ctx.send(f"⚠️ Error: {str(e)}")

@bot.command(name='ddg')
async def duckduckgo_search(ctx, query: str, *, question: str = None):
    """Search using DuckDuckGo and learn from the results."""
    try:
        async with ctx.typing():
            # Perform the search
            search_results = await DuckDuckGoSearcher.text_search(query)
            
            # If there's a question, use the AI to answer it based on the search results
            if question:
                prompt = f"""I searched for information about "{query}" and got these results:

{search_results}

My question is: {question}

Please provide a detailed answer formatted in markdown, with relevant information from the search results.
Include code examples if applicable.
"""
                ai_response = await get_ollama_response(prompt, with_context=False)
                await send_in_chunks(ctx, ai_response, reference=ctx.message)
            else:
                # Just send the search results
                await send_in_chunks(ctx, search_results, reference=ctx.message)
                
    except Exception as e:
        logging.error(f"Error in duckduckgo_search: {e}")
        await ctx.send(f"⚠️ Error: {str(e)}")

@bot.command(name='crawl')
async def crawl_url(ctx, urls: str, *, question: str = None):
    """Crawl multiple webpages and learn from them."""
    try:
        async with ctx.typing():
            # Split URLs by space or comma
            url_list = re.split(r'[,\s]+', urls.strip())
            all_content = []
            
            for url in url_list:
                url = url.strip()
                if not url:
                    continue
                    
                # Check if it's a PyPI package
                pypi_match = re.match(r'https?://pypi\.org/project/([^/]+)/?.*', url)
                
                if pypi_match:
                    # Handle PyPI URL
                    package_name = pypi_match.group(1)
                    html_content = await WebCrawler.fetch_url_content(url)
                    if html_content:
                        pypi_info = await WebCrawler.extract_pypi_content(html_content, package_name)
                        if pypi_info:
                            formatted_content = f"# {pypi_info['name']} PyPI Package\n\n"
                            if pypi_info['metadata']:
                                formatted_content += "## Package Information\n\n"
                                for section, items in pypi_info['metadata'].items():
                                    formatted_content += f"### {section}\n"
                                    for item in items:
                                        formatted_content += f"- {item}\n"
                                    formatted_content += "\n"
                            if pypi_info['documentation']:
                                formatted_content += "## Documentation\n\n"
                                formatted_content += pypi_info['documentation']
                            all_content.append({"url": url, "content": formatted_content})
                else:
                    # Handle regular URL
                    html_content = await WebCrawler.fetch_url_content(url)
                    if html_content:
                        webpage_text = await WebCrawler.extract_text_from_html(html_content)
                        all_content.append({"url": url, "content": webpage_text})
            
            if not all_content:
                await ctx.send("⚠️ Could not fetch content from any of the provided URLs")
                return
                
            # Combine all content for the question
            if question:
                combined_prompt = "I've gathered information from multiple sources:\n\n"
                for item in all_content:
                    combined_prompt += f"From {item['url']}:\n{item['content'][:5000]}...\n\n"
                combined_prompt += f"\nMy question is: {question}\n\nPlease provide a detailed answer using information from all sources."
                
                ai_response = await get_ollama_response(combined_prompt, with_context=False)
                await send_in_chunks(ctx, ai_response, reference=ctx.message)
            else:
                # Send summaries of each source
                for item in all_content:
                    header = f"# 🌐 Summary: {item['url']}\n\n"
                    summary = await get_ollama_response(f"Summarize this content:\n{item['content'][:7000]}", with_context=False)
                    await send_in_chunks(ctx, header + summary, reference=ctx.message)
                
    except Exception as e:
        logging.error(f"Error in crawl_url: {e}")
        await ctx.send(f"⚠️ Error: {str(e)}")

@bot.command(name='pandas')
async def pandas_query(ctx, *, query: str):
    """Query stored data using natural language and the Pandas Query Engine."""
    try:
        async with ctx.typing():
            # First check if data directories exist
            if not os.path.exists(DATA_DIR):
                await ctx.send("⚠️ No data directory found. Please perform some searches or paper queries first.")
                return

            # Determine which data to query based on the query
            query_lower = query.lower()
            df = None
            data_desc = ""

            if 'arxiv' in query_lower or 'paper' in query_lower:
                papers_dir = Path(f"{DATA_DIR}/papers")
                if not papers_dir.exists() or not list(papers_dir.glob("*.parquet")):
                    await ctx.send("No ArXiv papers have been searched yet.")
                    return
                    
                papers_file = papers_dir / "all_papers.parquet"
                if papers_file.exists():
                    df = ParquetStorage.load_from_parquet(str(papers_file))
                    data_desc = "ArXiv papers"
                else:
                    await ctx.send("No consolidated ArXiv data found.")
                    return

            elif 'crawl' in query_lower or 'web' in query_lower:
                crawls_dir = Path(f"{DATA_DIR}/crawls")
                if not crawls_dir.exists():
                    await ctx.send("No crawled web pages found.")
                    return

                crawl_files = list(crawls_dir.glob("*.parquet"))
                if not crawl_files:
                    await ctx.send("No web pages have been crawled yet.")
                    return

                dfs = []
                for file in crawl_files:
                    try:
                        df_temp = ParquetStorage.load_from_parquet(str(file))
                        if df_temp is not None and not df_temp.empty:
                            dfs.append(df_temp)
                    except Exception as e:
                        logging.error(f"Error loading crawl file {file}: {e}")

                if not dfs:
                    await ctx.send("No valid crawl data found in the files.")
                    return

                df = pd.concat(dfs, ignore_index=True)
                data_desc = "Crawled web pages"

            elif 'search' in query_lower or 'duck' in query_lower or 'ddg' in query_lower:
                searches_dir = Path(f"{DATA_DIR}/searches")
                if not searches_dir.exists():
                    await ctx.send("No search data directory found.")
                    return

                search_files = list(searches_dir.glob("*.parquet"))
                if not search_files:
                    await ctx.send("No DuckDuckGo searches have been performed yet.")
                    return

                dfs = []
                for file in search_files:
                    try:
                        df_temp = ParquetStorage.load_from_parquet(str(file))
                        if df_temp is not None and not df_temp.empty:
                            dfs.append(df_temp)
                    except Exception as e:
                        logging.error(f"Error loading search file {file}: {e}")

                if not dfs:
                    await ctx.send("No valid search data found in the files.")
                    return

                df = pd.concat(dfs, ignore_index=True)
                data_desc = "DuckDuckGo searches"

            else:
                help_text = """Please specify data type in your query:
- `arxiv` or `paper` - Query ArXiv paper information
- `crawl` or `web` - Query crawled webpage data
- `search`, `duck`, or `ddg` - Query DuckDuckGo search history

Examples:
```
!pandas show recent searches
!pandas show arxiv papers from today
!pandas show crawled pages
```"""
                await ctx.send(help_text)
                return

            if df is None or df.empty:
                await ctx.send("No data available to query.")
                return

            # Add data type descriptions
            data_descriptions = {
                "ArXiv papers": "Scientific papers fetched from ArXiv",
                "Crawled web pages": "Content from crawled web pages",
                "DuckDuckGo searches": "Search queries and results from DuckDuckGo"
            }

            # Format DataFrame info
            df_info = f"""**Data Type:** {data_desc}
**Description:** {data_descriptions.get(data_desc, '')}
**Total Records:** {df.shape[0]}
**Available Fields:** {', '.join(df.columns)}
**Date Range:** {pd.to_datetime(df['timestamp']).min().strftime('%Y-%m-%d')} to {pd.to_datetime(df['timestamp']).max().strftime('%Y-%m-%d')}"""

            # Execute the pandas query
            result = await PandasQueryEngine.execute_query(df, query)
            
            # Format response
            response_text = f"""# 📊 Data Query Results: {data_desc}

**Your query:** {query}

## Dataset Information
{df_info}

## Query Results
```
{result.get('result', 'No results available.')}
```

**Code used:**
```python
{result.get('code', 'No code available.')}
```

{result.get('explanation', '')}

## Tip
Use more specific queries like:
- "Show items from today"
- "Show most recent 5 entries"
- "Count items by date"
"""
            await send_in_chunks(ctx, response_text, reference=ctx.message)
                
    except Exception as e:
        logging.error(f"Error in pandas_query: {e}")
        await ctx.send(f"⚠️ Error in data query: {str(e)}\nTry using !reset if the issue persists.")

@bot.command(name='profile')
async def view_profile(ctx, *, question: str = None):
    """View your user profile or ask questions about your learning history."""
    try:
        user_key = get_user_key(ctx)
        user_name = ctx.author.display_name or ctx.author.name
        profile_path = os.path.join(USER_PROFILES_DIR, f"{user_key}_profile.json")
        
        # Check if profile exists
        if not os.path.exists(profile_path):
            await ctx.send(f"⚠️ No profile found for {user_name}. Interact with me more to build your profile!")
            return
            
        # Load profile data
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile_data = json.load(f)
            
        # Get conversation history
        conversations = USER_CONVERSATIONS.get(user_key, [])
        user_messages = [
            conv for conv in conversations 
            if conv['role'] == 'user' and 'content' in conv
        ]
        
        # Format basic profile info
        profile_text = f"""# 👤 Profile for {user_name}

## Activity Summary
- Messages: {len(user_messages)}
- First Interaction: {user_messages[0]['timestamp'] if user_messages else 'N/A'}
- Last Active: {profile_data.get('timestamp', 'Unknown')}

## Learning Analysis
{profile_data.get('analysis', 'No analysis available yet.')}
"""

        if question:
            # Create context for answering questions about the user
            context = f"""User Profile Information:
{profile_data.get('analysis', '')}

Recent Conversations:
{chr(10).join([f"- {msg['content']}" for msg in user_messages[-10:]])}

Question about the user: {question}

Please provide a detailed, personalized answer based on the user's profile and conversation history.
Address the user by name ({user_name}) in your response."""

            async with ctx.typing():
                answer = await get_ollama_response(context, with_context=False)
                await send_in_chunks(ctx, f"# 🔍 Profile Query\n\n{answer}", reference=ctx.message)
        else:
            # Just show the profile
            await send_in_chunks(ctx, profile_text, reference=ctx.message)
            
    except Exception as e:
        logging.error(f"Error in view_profile: {e}")
        await ctx.send(f"⚠️ Error accessing profile: {str(e)}")

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

# ---------- Message Event Handler ----------

@bot.event
async def on_message(message: Message):
    """Handles incoming messages."""
    # Don't respond to self
    if message.author == bot.user:
        return

    # Get user's preferred name
    user_name = message.author.display_name or message.author.name
    
    # Only process if bot is mentioned
    if bot.user and bot.user.mentioned_in(message):
        content = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
        
        # Store user information
        await store_user_conversation(message, content)
        
        # Add personalized greeting for direct questions
        if not content.startswith('!'):
            greeting = f"Hi {user_name}! "
        else:
            greeting = ""
        
        # Process commands if starts with !
        if content.startswith('!'):
            message.content = content
            await bot.process_commands(message)
        # Handle conversation for non-command mentions
        else:
            try:
                # Handle file attachments
                if message.attachments:
                    files_content = []
                    for attachment in message.attachments:
                        try:
                            file_content = await process_file_attachment(attachment)
                            files_content.append(f"File: {attachment.filename}\n{file_content}")
                        except ValueError as e:
                            await message.channel.send(f"⚠️ {user_name}, there was an error with {attachment.filename}: {str(e)}")
                            continue
                    
                    if files_content:
                        # Combine file contents with the question
                        combined_prompt = f"""The user {user_name} has provided these file(s) to analyze:

{chr(10).join(files_content)}

Their question or request is: {content}

Please provide a detailed response, including code examples if relevant. Address the user by name in your response."""
                        
                        conversation_logs.append({'role': 'user', 'content': combined_prompt})
                        async with message.channel.typing():
                            response = await get_ollama_response(combined_prompt)
                        conversation_logs.append({'role': 'assistant', 'content': response})
                        await store_user_conversation(message, response, is_bot=True)
                        await send_in_chunks(message.channel, greeting + response, message)
                        return
                
                # Regular conversation without files
                personalized_content = f"{user_name} asks: {content}\n\nProvide a helpful response, addressing them by name."
                conversation_logs.append({'role': 'user', 'content': personalized_content})
                async with message.channel.typing():
                    response = await get_ollama_response(personalized_content)
                conversation_logs.append({'role': 'assistant', 'content': response})
                await store_user_conversation(message, response, is_bot=True)
                await send_in_chunks(message.channel, greeting + response, message)
            
            except Exception as e:
                logging.error(f"Error processing message: {e}")
                await message.channel.send(f"⚠️ {user_name}, an error occurred: {str(e)}")

async def change_nickname(guild):
    """Change the bot's nickname in the specified guild."""
    nickname = f"Ollama Teacher"
    try:
        await guild.me.edit(nick=nickname)
        logging.info(f"Nickname changed to {nickname} in guild {guild.name}")
    except Exception as e:
        logging.error(f"Failed to change nickname in guild {guild.name}: {str(e)}")

@bot.event
async def on_ready():
    """Called when the bot is ready."""
    try:
        # Log startup
        logging.info(f'{bot.user.name} is now running!')
        logging.info(f'Connected to {len(bot.guilds)} guilds')
        
        # Start periodic tasks
        analyze_user_profiles.start()
        
        # Initialize user data storage
        for guild in bot.guilds:
            logging.info(f'Initializing data for guild: {guild.name}')
            guild_dir = Path(f"{DATA_DIR}/guilds/{guild.id}")
            guild_dir.mkdir(parents=True, exist_ok=True)
            
            # Store member information
            member_data = {}
            for member in guild.members:
                if not member.bot:
                    member_data[str(member.id)] = {
                        'name': member.name,
                        'display_name': member.display_name,
                        'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                        'roles': [role.name for role in member.roles if role.name != "@everyone"],
                        'last_active': datetime.now(UTC).isoformat()
                    }
            
            # Save member data
            member_file = guild_dir / 'members.json'
            with open(member_file, 'w', encoding='utf-8') as f:
                json.dump(member_data, f, indent=2)
        
        # Change nicknames if enabled
        if CHANGE_NICKNAME:
            for guild in bot.guilds:
                try:
                    await guild.me.edit(nick="Ollama Teacher")
                    logging.info(f'Nickname changed in guild {guild.name}')
                except Exception as e:
                    logging.error(f'Failed to change nickname in {guild.name}: {e}')
        
        # Set custom status with help command info
        status_text = "!help | Mention me with questions!"
        await bot.change_presence(
            activity=Game(name=status_text),
            status=Status.online
        )
        
        logging.info('Bot initialization complete!')
        
    except Exception as e:
        logging.error(f'Error in on_ready: {e}')

@tasks.loop(minutes=30)
async def analyze_user_profiles():
    """Analyze user conversations and update profiles periodically."""
    try:
        for user_key, conversations in USER_CONVERSATIONS.items():
            guild_id, user_id = map(int, user_key.split('_'))
            
            # Get user messages only
            user_messages = [
                conv['content'] for conv in conversations 
                if conv['role'] == 'user'
            ]
            
            if not user_messages:
                continue
                
            # Create analysis prompt
            analysis_prompt = f"""Analyze these user messages and extract key information:
{chr(10).join(user_messages[-50:])}

Please identify:
1. Main topics of interest
2. Technical skill level
3. Common questions or patterns
4. Learning progress
5. Key concepts discussed

Format the response as concise bullet points."""
            
            # Get AI analysis
            analysis = await get_ollama_response(analysis_prompt, with_context=False)
            
            # Save to user profile
            profile_path = os.path.join(USER_PROFILES_DIR, f"{user_key}_profile.json")
            profile_data = {
                'timestamp': datetime.now(UTC).isoformat(),
                'analysis': analysis,
                'username': bot.get_user(int(user_id)).name if bot.get_user(int(user_id)) else 'Unknown'
            }
            
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2)
                
    except Exception as e:
        logging.error(f"Error in analyze_user_profiles: {e}")

def main():
    """Main function to run the bot."""
    bot.run(TOKEN)

if __name__ == '__main__':
    main()
