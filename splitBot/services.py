import os
import re
import asyncio
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import json
import time
from datetime import datetime, timezone, UTC
from pathlib import Path
import aiohttp
from bs4 import BeautifulSoup
from pytube import YouTube
import concurrent.futures
import unicodedata

# Import Groq if available
try:
    from groq import AsyncGroq, Groq
    GROQ_AVAILABLE = True
except ImportError:
    pass  # No action needed if Groq API is not installed
    GROQ_AVAILABLE = False
    logging.warning("Groq package not installed. To use --groq flag, run: pip install groq")

import ollama

from utils import ParquetStorage, SYSTEM_PROMPT
from config import MODEL_NAME as CONFIG_MODEL_NAME

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
            logging.error(f"Error fetching URL {url}: {e}")
            return None

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
    
    @staticmethod
    async def extract_youtube_content(url):
        """Extract information from a YouTube video."""
        try:
            # Run YouTube download in a thread pool to avoid blocking
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(WebCrawler._extract_youtube_details, url)
                return await asyncio.wrap_future(future)
        except Exception as e:
            logging.error(f"Error extracting YouTube content: {e}")
            return None
    
    @staticmethod
    def _extract_youtube_details(url):
        """Extract YouTube video details."""
        yt = YouTube(url)
        
        # Build video information
        video_info = {
            'title': yt.title,
            'author': yt.author,
            'channel_url': yt.channel_url,
            'description': yt.description,
            'publish_date': yt.publish_date.isoformat() if yt.publish_date else None,
            'length': yt.length,
            'views': yt.views,
            'thumbnail_url': yt.thumbnail_url,
            'keywords': yt.keywords,
            'url': url,
            'captions': {},
            'transcript': '',
        }
        
        # Try to get captions
        try:
            captions = yt.captions
            if captions and 'en' in captions:
                caption = captions['en']
                transcript = caption.generate_srt_captions()
                
                # Clean up transcript
                transcript = re.sub(r'\d+:\d+:\d+,\d+ --> \d+:\d+:\d+,\d+', '', transcript)
                transcript = re.sub(r'^\d+$', '', transcript, flags=re.MULTILINE)
                transcript = unicodedata.normalize('NFKC', transcript)
                
                video_info['transcript'] = transcript.strip()
        except Exception as e:
            logging.warning(f"Could not get captions for {url}: {e}")
            
        return video_info

# Configuration variables from environment

# Import model name from config
from config import MODEL_NAME as CONFIG_MODEL_NAME

# Update the model selection logic

# Import directly from environment, with fallback to a reliable model
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'phi3:latest')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL = os.getenv('GROQ_MODEL')
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))  # Temperature setting for the AI model
TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))  # Timeout setting for the API call
DATA_DIR = os.getenv('DATA_DIR', 'data')

# ---------- Ollama Integration ----------

class ModelManager:
    """Manages Ollama model loading and unloading"""
    
    def __init__(self):
        self.current_base_model = None
        self.current_vision_model = None
        self.model_info = {}  # Cache model metadata
        
    async def load_model(self, model_name, is_vision=False):
        """Load a model and unload others if needed"""
        try:
            # Check if model is already loaded
            if (is_vision and self.current_vision_model == model_name) or (not is_vision and self.current_base_model == model_name):
                return True
                
            # Get model info if not cached
            if model_name not in self.model_info:
                client = ollama.AsyncClient()
                try:
                    # Test if model is available by attempting a minimal chat
                    test_message = {'role': 'user', 'content': 'test'}
                    await client.chat(model=model_name, messages=[test_message])
                    self.model_info[model_name] = {'loaded': True}
                    
                    # Update current model tracking
                    if is_vision:
                        self.current_vision_model = model_name
                    else:
                        self.current_base_model = model_name
                    
                    logging.info(f"Successfully loaded model: {model_name}")
                    return True
                    
                except Exception as e:
                    logging.error(f"Model {model_name} not available: {e}")
                    return False
                    
        except Exception as e:
            logging.error(f"Error loading model {model_name}: {e}")
            return False

    async def unload_model(self, model_name):
        """Mark model as unloaded in our tracking"""
        try:
            if self.current_base_model == model_name:
                self.current_base_model = None
            if self.current_vision_model == model_name:
                self.current_vision_model = None
            
            if model_name in self.model_info:
                del self.model_info[model_name]
                
            logging.info(f"Model unloaded from tracking: {model_name}")
            return True
            
        except Exception as e:
            logging.error(f"Error unloading model {model_name}: {e}")
            return False

# Create global model manager instance
model_manager = ModelManager()

# Update get_ollama_response to use model manager
async def get_ollama_response(prompt, with_context=True, use_groq=False, conversation_history=None, timeout=None):
    """Gets a response from the Ollama or Groq model."""
    if use_groq:
        # Groq handling remains unchanged
        try:
            if not GROQ_AVAILABLE:
                return "Groq API not available. Please install the Groq package with: pip install groq"
                
            groq_api_key = os.getenv('GROQ_API_KEY')
            groq_model = os.getenv('GROQ_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')
            
            if not groq_api_key:
                return "Groq API key not set. Please set GROQ_API_KEY in your environment variables."
                
            # Initialize Groq client
            client = AsyncGroq(api_key=groq_api_key)
            
            # Format messages for the model
            if with_context and conversation_history:
                messages_to_send = conversation_history
            else:
                messages_to_send = [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
            # Log the Groq model being used
            logging.info(f"Using Groq model: {groq_model}")
            
            # Make request to Groq API
            chat_completion = await client.chat.completions.create(
                model=groq_model,
                messages=messages_to_send,
                temperature=TEMPERATURE,
                max_tokens=1024,
            )
            
            return chat_completion.choices[0].message.content
            
        except Exception as e:
            logging.error(f"Error using Groq API: {e}")
            return f"Error with Groq API: {str(e)}"
    else:
        try:
            # Get selected model from environment
            model_name = os.getenv('OLLAMA_MODEL')
            if not model_name:
                raise Exception("No model selected. Please select a model in the UI.")
            
            # Try loading the model
            if not await model_manager.load_model(model_name):
                raise Exception(f"Could not load model: {model_name}")

            # Format messages for the model
            if with_context and conversation_history:
                messages_to_send = conversation_history
            else:
                messages_to_send = [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]

            # Using the streaming approach with AsyncClient
            response_text = ""
            # Use the timeout parameter if provided, otherwise use the default TIMEOUT value
            actual_timeout = timeout if timeout is not None else TIMEOUT
            
            try:
                # Create client with the correct timeout
                client = ollama.AsyncClient(timeout=actual_timeout)
                
                # Get the stream of responses
                stream_generator = await client.chat(
                    model=model_name,
                    messages=messages_to_send,
                    options={
                        'temperature': TEMPERATURE,
                        'num_predict': 512,
                        'stop': ['User:', 'Human:', '###']
                    },
                    stream=True
                )
                
                # Process the streaming response
                async for chunk in stream_generator:
                    if 'message' in chunk and 'content' in chunk['message']:
                        response_text += chunk['message']['content']
                
                if response_text:
                    return response_text
                else:
                    return "I'm sorry, I couldn't generate a response. Please try rephrasing your question. If the issue persists, please contact @BORCH the developer of Ollama Teacher & OARC."
            except TypeError as te:
                # Handle the case where timeout might be passed incorrectly
                if "unexpected keyword argument 'timeout'" in str(te):
                    logging.warning(f"Timeout parameter not supported by AsyncClient. Trying again without timeout...")
                    # Try again without timeout parameter
                    client = ollama.AsyncClient()
                    stream_generator = await client.chat(
                        model=model_name,
                        messages=messages_to_send,
                        options={
                            'temperature': TEMPERATURE,
                            'num_predict': 512,
                            'stop': ['User:', 'Human:', '###']
                        },
                        stream=True
                    )
                    
                    # Process the streaming response
                    async for chunk in stream_generator:
                        if 'message' in chunk and 'content' in chunk['message']:
                            response_text += chunk['message']['content']
                    
                    if response_text:
                        return response_text
                    else:
                        return "I'm sorry, I couldn't generate a response. Please try rephrasing your question."
                else:
                    raise
    
        except Exception as e:
            logging.error(f"Error in get_ollama_response: {e}")
            return f"Error: {str(e)}. Please make sure a model is selected in the UI."

# Update process_image_with_llava similarly
async def process_image_with_llava(image_data, prompt, model_name=None):
    """Process image data with a vision model."""
    try:
        vision_model = model_name or os.getenv('OLLAMA_VISION_MODEL')
        
        # Try loading the vision model
        if not await model_manager.load_model(vision_model, is_vision=True):
            raise Exception("Could not load vision model")

        # Format messages for vision model
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [image_data]
            }
        ]

        # Call vision model
        logging.info(f"Using vision model: {vision_model}")
        client = ollama.AsyncClient()
        response_text = ""
        
        stream = await client.chat(
            model=vision_model,
            messages=messages,
            stream=True
        )

        async for chunk in stream:
            if 'message' in chunk and 'content' in chunk['message']:
                response_text += chunk['message']['content']

        return response_text

    except Exception as e:
        logging.error(f"Vision model error: {e}")
        return f"Error processing image: {str(e)}"

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
            logging.error(f"DuckDuckGo search error: {e}")
            return f"An error occurred during the search: {str(e)}"

# ---------- Pandas Query Engine Integration ----------

class PandasQueryEngine:
    def __init__(self, conversation_memory=None):
        self.conversation_memory = conversation_memory or []
        self.last_query_context = None
    
    async def query(self, query_str, df, with_memory=False):
        """Process a natural language query against a pandas DataFrame"""
        try:
            # Build context from memory if enabled
            context = ""
            if with_memory and self.conversation_memory:
                context = "Previous relevant queries:\n"
                for mem in self.conversation_memory[-3:]:  # Last 3 queries
                    context += f"Q: {mem['query']}\nA: {mem['result']}\n"
            
            # Format prompt with context
            prompt = f"""
            {context}
            DataFrame Info:
            {df.info()}
            
            Query: {query_str}
            
            Generate Python code using pandas to answer this query.
            """
            
            # Get LLM response
            response = await get_ollama_response(prompt)
            
            # Execute generated code safely
            result = self._safe_execute(response, df)
            
            # Store in memory
            if with_memory:
                self.conversation_memory.append({
                    'query': query_str,
                    'result': str(result),
                    'timestamp': datetime.now(UTC).isoformat()
                })
                
            return result
            
        except Exception as e:
            logging.error(f"Query engine error: {e}")
            return f"Error processing query: {str(e)}"
            
    def _safe_execute(self, code, df):
        """Safely execute generated pandas code"""
        # Add code safety checks here
        restricted_terms = ['eval', 'exec', 'import', 'os', 'system']
        if any(term in code for term in restricted_terms):
            raise ValueError("Unsafe code detected")
            
        try:
            # Execute in restricted environment
            local_vars = {'df': df, 'pd': pd}
            return eval(code, {"__builtins__": {}}, local_vars)
        except Exception as e:
            raise ValueError(f"Code execution failed: {e}")