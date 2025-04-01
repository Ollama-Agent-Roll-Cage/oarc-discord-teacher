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

import ollama

from utils import ParquetStorage

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

# Configuration variables from environment
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3')  # Model name for the Ollama API
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))  # Temperature setting for the AI model
TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))  # Timeout setting for the API call
DATA_DIR = os.getenv('DATA_DIR', 'data')

# ---------- Ollama Integration ----------

async def get_ollama_response(prompt, with_context=True):
    """Gets a response from the Ollama model."""
    try:
        # Import from main.py to avoid circular imports
        from main import conversation_logs
        
        if with_context:
            messages_to_send = conversation_logs.copy()
        else:
            from utils import SYSTEM_PROMPT
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