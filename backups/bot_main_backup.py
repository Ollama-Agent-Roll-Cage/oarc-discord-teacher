import os
import asyncio
from dotenv import load_dotenv
from discord import Intents, Message, Embed, Color, File, Game
from discord.ext import commands
import ollama
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import re
import time
import aiohttp
from datetime import datetime
import markdown
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import json
from bs4 import BeautifulSoup

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
            # Create a description of the DataFrame
            df_head = dataframe.head().to_string()
            df_info = f"DataFrame info:\nShape: {dataframe.shape}\nColumns: {', '.join(dataframe.columns)}\n"
            
            # Construct the prompt for code generation
            prompt = f"""You are an expert in Python and pandas. 
            I have a pandas DataFrame with the following structure:
            
            {df_info}
            
            Here is the head of the DataFrame:
            {df_head}
            
            Please write a pandas code snippet to answer this query: "{query}"
            
            Return ONLY the executable Python code snippet, nothing else. 
            The code should:
            1. Use the variable `df` to refer to the DataFrame
            2. Be concise but complete
            3. Include only the necessary operations to answer the query
            """
            
            # Get code from Ollama
            code_response = await get_ollama_response(prompt, with_context=False)
            
            # Extract code (remove markdown code blocks if present)
            code = code_response.strip()
            if code.startswith("```python"):
                code = code[9:]
            if code.startswith("```"):
                code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()
            
            # Define a safe local scope with the dataframe
            local_scope = {'df': dataframe, 'pd': pd}
            
            # Execute the code
            try:
                result = eval(code, {"__builtins__": {}}, local_scope)
                
                # Format the result
                if isinstance(result, pd.DataFrame):
                    result_text = result.to_string()
                elif isinstance(result, pd.Series):
                    result_text = result.to_string()
                else:
                    result_text = str(result)
                    
                # Generate explanation
                explanation_prompt = f"""I executed this pandas code to answer the query "{query}":
                
                ```python
                {code}
                ```
                
                The result was:
                ```
                {result_text}
                ```
                
                Please explain what this code does and interpret the result in a clear, educational way.
                Format your response in markdown.
                """
                
                explanation = await get_ollama_response(explanation_prompt, with_context=False)
                
                return {
                    "query": query,
                    "code": code,
                    "result_text": result_text,
                    "explanation": explanation
                }
                
            except Exception as e:
                error_prompt = f"""This pandas code generated an error:
                
                ```python
                {code}
                ```
                
                The error is: {str(e)}
                
                Please correct the code to properly answer the query: "{query}"
                Return ONLY the corrected Python code snippet, nothing else.
                """
                
                corrected_code = await get_ollama_response(error_prompt, with_context=False)
                
                # Try again with corrected code
                return await PandasQueryEngine.execute_query(dataframe, query)
                
        except Exception as e:
            logger.error(f"Error in PandasQueryEngine: {e}")
            return {
                "query": query,
                "error": str(e),
                "explanation": f"I encountered an error while trying to analyze the data: {str(e)}"
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
                'timestamp': datetime.utcnow().isoformat()
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
                                'timestamp': datetime.utcnow().isoformat(),
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
            
            if description_div:
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
                            'timestamp': datetime.utcnow().isoformat(),
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
    """Resets the conversation log."""
    conversation_logs.clear()
    conversation_logs.append({'role': 'system', 'content': SYSTEM_PROMPT})
    await ctx.send("✅ Conversation context has been reset.")

@bot.command(name='help')
async def help_command(ctx):
    """Display help information."""
    help_text = """# 🤖 Ollama Teacher Bot Commands

## Direct Commands (use with ! prefix)
- `!help` - Show this help message
- `!reset` - Clear conversation history
- `!learn` - Show learning resources

## AI-Powered Commands
- `!arxiv <arxiv_url_or_id> <question>` - Learn from ArXiv papers
- `!ddg <query> <question>` - Search DuckDuckGo and learn
- `!crawl <url> <question>` - Learn from web pages
- `!pandas <query>` - Query stored data

## Chat Mode
- Mention the bot without commands to start a conversation
- Example: @Ollama Teacher What is machine learning?

## Examples
```
!arxiv 1706.03762 Explain attention mechanism
!ddg "python asyncio" How to use async/await?
!crawl https://pypi.org/project/ollama/ How to use this package?
!pandas Show recent ArXiv papers
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
async def arxiv_search(ctx, arxiv_url_or_id: str, *, question: str = None):
    """Search for an ArXiv paper and learn from it."""
    try:
        async with ctx.typing():
            # Extract ArXiv ID
            arxiv_id = ArxivSearcher.extract_arxiv_id(arxiv_url_or_id)
            
            # Check if we already have this paper
            paper_file = f"{DATA_DIR}/papers/{arxiv_id}.parquet"
            existing_paper = ParquetStorage.load_from_parquet(paper_file)
            
            if existing_paper is not None and len(existing_paper) > 0:
                # Convert DataFrame row to dict
                paper_info = existing_paper.iloc[0].to_dict()
                logger.info(f"Using cached paper info for {arxiv_id}")
            else:
                # Fetch paper info
                paper_info = await ArxivSearcher.fetch_paper_info(arxiv_id)
            
            # Format paper for learning
            paper_text = await ArxivSearcher.format_paper_for_learning(paper_info)
            
            # If there's a question, use the AI to answer it based on the paper
            if question:
                prompt = f"""I want to learn about the following research paper:

{paper_text}

My question is: {question}

Please provide a detailed answer formatted in markdown, with relevant information from the paper. 
Include code examples if applicable.
"""
                ai_response = await get_ollama_response(prompt, with_context=False)
                await send_in_chunks(ctx, ai_response, reference=ctx.message)
            else:
                # Just send the paper information
                await send_in_chunks(ctx, paper_text, reference=ctx.message)
                
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
async def crawl_url(ctx, url: str, *, question: str = None):
    """Crawl a webpage and learn from it."""
    try:
        async with ctx.typing():
            # Check if it's a PyPI package
            pypi_pattern = r'https?://pypi\.org/project/([^/]+)/?.*'
            pypi_match = re.match(pypi_pattern, url)
            
            if pypi_match:
                # Extract package name from URL
                package_name = pypi_match.group(1)
                logging.info(f"Detected PyPI package: {package_name}")
                
                # Fetch the webpage
                html_content = await WebCrawler.fetch_url_content(url)
                
                if html_content:
                    # Extract the content using our specialized extractor
                    pypi_info = await WebCrawler.extract_pypi_content(html_content, package_name)
                    
                    if pypi_info:
                        # Format as markdown
                        formatted_content = f"# {pypi_info['name']} PyPI Package\n\n"
                        
                        # Add metadata
                        if pypi_info['metadata']:
                            formatted_content += "## Package Information\n\n"
                            for section, items in pypi_info['metadata'].items():
                                formatted_content += f"### {section}\n"
                                for item in items:
                                    formatted_content += f"- {item}\n"
                                formatted_content += "\n"
                        
                        # Add documentation
                        if pypi_info['documentation']:
                            formatted_content += "## Documentation\n\n"
                            formatted_content += pypi_info['documentation']
                        
                        # Use the extracted content
                        if question:
                            prompt = f"""I'm looking at the Python package '{package_name}' from PyPI.
                            
The following documentation was extracted directly from the PyPI page:

{formatted_content}

My question is: {question}

Please provide a detailed answer using only the factual information from the documentation above.
Include Python code examples when relevant.
"""
                            ai_response = await get_ollama_response(prompt, with_context=False)
                            await send_in_chunks(ctx, ai_response, reference=ctx.message)
                        else:
                            # Just send the documentation
                            await send_in_chunks(ctx, formatted_content, reference=ctx.message)
                        return
                    
                    # If specialized extraction failed, fall back to regular method
                    logging.info("Specialized PyPI extraction failed. Falling back to regular extraction.")
            
            # Regular web crawling for non-PyPI sites or if PyPI extraction failed
            html_content = await WebCrawler.fetch_url_content(url)
            
            if html_content:
                # Extract text from HTML
                webpage_text = await WebCrawler.extract_text_from_html(html_content)
                
                # Log the extracted text (truncated)
                logging.info(f"Extracted text from {url} (first 200 chars): {webpage_text[:200]}...")
                
                # Summarize the webpage content
                summary_prompt = f"""I need a brief summary of the following webpage content from {url}:

Here's an excerpt of the page content:
{webpage_text[:5000]}...

Please provide a concise summary formatted in markdown with key points.
"""
                summary = await get_ollama_response(summary_prompt, with_context=False)
                
                # If there's a question, use the AI to answer it based on the webpage
                if question:
                    prompt = f"""I crawled this webpage: {url}

Here's a summary of the content:
{summary}

And here's some of the raw text from the page:
{webpage_text[:7000]}...

My question is: {question}

Please provide a detailed answer formatted in markdown, with relevant information from the webpage.
Include code examples if applicable.
"""
                    ai_response = await get_ollama_response(prompt, with_context=False)
                    await send_in_chunks(ctx, ai_response, reference=ctx.message)
                else:
                    # Just send the summary
                    header = f"# 🌐 Webpage Summary: {url}\n\n"
                    await send_in_chunks(ctx, header + summary, reference=ctx.message)
            else:
                await ctx.send(f"⚠️ Error: Could not fetch content from {url}")
                
    except Exception as e:
        logging.error(f"Error in crawl_url: {e}")
        await ctx.send(f"⚠️ Error: {str(e)}")

@bot.command(name='pandas')
async def pandas_query(ctx, *, query: str):
    """Query stored data using natural language and the Pandas Query Engine."""
    try:
        async with ctx.typing():
            # Determine which data to query based on the query
            query_lower = query.lower()
            
            if 'arxiv' in query_lower or 'paper' in query_lower:
                # Load all papers
                papers_file = f"{DATA_DIR}/papers/all_papers.parquet"
                df = ParquetStorage.load_from_parquet(papers_file)
                if df is None or len(df) == 0:
                    await ctx.send("No ArXiv papers have been searched yet.")
                    return
                
                data_desc = "ArXiv papers"
                
            elif 'search' in query_lower or 'duck' in query_lower or 'ddg' in query_lower:
                # Load search data
                search_files = list(Path(f"{DATA_DIR}/searches").glob("*.parquet"))
                if not search_files:
                    await ctx.send("No searches have been performed yet.")
                    return
                
                # Combine all search data
                dfs = []
                for file in search_files:
                    df_temp = ParquetStorage.load_from_parquet(str(file))
                    if df_temp is not None:
                        dfs.append(df_temp)
                
                if not dfs:
                    await ctx.send("No valid search data found.")
                    return
                    
                df = pd.concat(dfs, ignore_index=True)
                data_desc = "DuckDuckGo searches"
                
            elif 'crawl' in query_lower or 'web' in query_lower or 'url' in query_lower:
                # Load crawl data
                crawl_files = list(Path(f"{DATA_DIR}/crawls").glob("*.parquet"))
                if not crawl_files:
                    await ctx.send("No web crawls have been performed yet.")
                    return
                
                # Combine all crawl data
                dfs = []
                for file in crawl_files:
                    df_temp = ParquetStorage.load_from_parquet(str(file))
                    if df_temp is not None:
                        dfs.append(df_temp)
                
                if not dfs:
                    await ctx.send("No valid crawl data found.")
                    return
                    
                df = pd.concat(dfs, ignore_index=True)
                data_desc = "web crawls"
                
            else:
                # Try to find the most appropriate dataset based on query
                await ctx.send("Please specify which data to query: papers, searches, or crawls.")
                return
            
            # Execute the pandas query
            result = await PandasQueryEngine.execute_query(df, query)
            
            response_text = f"""# 📊 Data Query Results: {data_desc}

**Your query:** {query}

{result.get('explanation', 'No explanation available.')}

**Code used:**
```python
{result.get('code', 'No code available.')}
```

"""
            await send_in_chunks(ctx, response_text, reference=ctx.message)
                
    except Exception as e:
        logging.error(f"Error in pandas_query: {e}")
        await ctx.send(f"⚠️ Error in data query: {str(e)}")

# ---------- Message Event Handler ----------

@bot.event
async def on_message(message: Message):
    """Handles incoming messages."""
    # Don't respond to self
    if message.author == bot.user:
        return

    # Only process if bot is mentioned
    if bot.user and bot.user.mentioned_in(message):
        content = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
        
        # Process commands if starts with !
        if content.startswith('!'):
            # Create a new message object with the cleaned content
            message.content = content
            await bot.process_commands(message)
        # Handle conversation for non-command mentions
        else:
            conversation_logs.append({'role': 'user', 'content': content})
            async with message.channel.typing():
                response = await get_ollama_response(content)
            conversation_logs.append({'role': 'assistant', 'content': response})
            await send_in_chunks(message.channel, response, message)

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
    """Called when the bot is ready to start interacting with the server."""
    logging.info(f'{bot.user.name} is now running!')
    
    # Change the nickname if enabled
    if CHANGE_NICKNAME:
        for guild in bot.guilds:
            await change_nickname(guild)
    
    # Set custom status
    await bot.change_presence(activity=Game(name="!help for commands"))

def main():
    """Main function to run the bot."""
    bot.run(TOKEN)

if __name__ == '__main__':
    main()
