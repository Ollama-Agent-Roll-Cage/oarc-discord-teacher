import os
import re
import logging
import json
from datetime import datetime, timezone, UTC
from pathlib import Path
from collections import defaultdict
import pandas as pd
from discord import File

from utils import (
    send_in_chunks, get_user_key, store_user_conversation,
    ParquetStorage, PandasQueryEngine, DEFAULT_RESOURCES, SYSTEM_PROMPT
)
from services import (
    get_ollama_response, ArxivSearcher, DuckDuckGoSearcher, WebCrawler
)

# Initialize logging
logger = logging.getLogger(__name__)

# Configure data directory
DATA_DIR = os.getenv('DATA_DIR', 'data')

def register_commands(bot, USER_CONVERSATIONS, COMMAND_MEMORY, conversation_logs, USER_PROFILES_DIR):
    """Register all bot commands."""

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
- `!crawl <url1> [url2 url3...] <question>` - Learn from web pages
- `!pandas <query>` - Query stored data
- `!links [limit]` - Collect and organize links from channel history

## Admin Commands
- `!globalReset` - Reset all conversations (admin only)

## Download and build your own custom OllamaDiscordTeacher from the github repo
https://github.com/Leoleojames1/OllamaDiscordTeacher/tree/master

## Chat Mode
- Mention the bot without commands to start a conversation
- Example: @Ollama Teacher What is machine learning?

## Memory Feature
The `--memory` flag saves context between queries:
- Add `--memory` before your question to enable persistent memory
- Great for follow-up questions about the same topic
- Use `!reset` to clear saved memory when you're done

## Examples
```
!profile                                    # View your profile
!profile What topics have I been learning?  # Ask about your progress
!arxiv --memory 1706.03762 Tell me about attention mechanisms
!arxiv 1706.03762 2104.05704 Compare these two papers  # Multiple papers
!ddg "python asyncio" How to use async/await?
!crawl https://pypi.org/project/ollama/ https://github.com/ollama/ollama Compare these
!links 500                                  # Collect links from last 500 messages
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
                    ctx.message,
                    f"Asked about ArXiv papers: {arxiv_ids}" + (f" with question: {question}" if question else "")
                )
                
                if question and 'ai_response' in locals():
                    await store_user_conversation(
                        ctx.message,
                        ai_response,
                        is_bot=True
                    )
                    
        except ValueError as e:
            logging.error(f"Error fetching URL {arxiv_ids}: {e}")
            await ctx.send(f"⚠️ Error with URL: {str(e)}")
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

                # Add debugging
                logging.info(f"Processing pandas query: '{query}'")
                logging.info(f"DATA_DIR: {DATA_DIR}")

                if 'arxiv' in query_lower or 'paper' in query_lower:
                    # Logging for arxiv data loading
                    papers_dir = Path(f"{DATA_DIR}/papers")
                    logging.info(f"Checking papers directory: {papers_dir}, exists={papers_dir.exists()}")
                    
                    if papers_dir.exists():
                        papers_files = list(papers_dir.glob("*.parquet"))
                        logging.info(f"Found {len(papers_files)} paper files: {[p.name for p in papers_files]}")
                    
                elif 'crawl' in query_lower or 'web' in query_lower:
                    # Logging for crawls data loading
                    crawls_dir = Path(f"{DATA_DIR}/crawls")
                    logging.info(f"Checking crawls directory: {crawls_dir}, exists={crawls_dir.exists()}")
                    
                    if crawls_dir.exists():
                        crawl_files = list(crawls_dir.glob("*.parquet"))
                        logging.info(f"Found {len(crawl_files)} crawl files: {[c.name for c in crawl_files]}")
                    
                elif 'link' in query_lower:
                    # Handle links query
                    links_dir = Path(f"{DATA_DIR}/links")
                    if not links_dir.exists():
                        await ctx.send("No links data directory found.")
                        return
                        
                    link_files = list(links_dir.glob("*.parquet"))
                    if not link_files:
                        await ctx.send("No link collection data has been saved yet.")
                        return
                        
                    dfs = []
                    for file in link_files:
                        try:
                            df_temp = ParquetStorage.load_from_parquet(str(file))
                            if df_temp is not None and not df_temp.empty:
                                dfs.append(df_temp)
                        except Exception as e:
                            logging.error(f"Error loading link file {file}: {e}")
                            
                    if not dfs:
                        await ctx.send("No valid link data found in the files.")
                        return
                        
                    df = pd.concat(dfs, ignore_index=True)
                    data_desc = "Links Collection"

                elif 'search' in query_lower or 'duck' in query_lower or 'ddg' in query_lower:
                    # Logging for searches data loading
                    searches_dir = Path(f"{DATA_DIR}/searches")
                    logging.info(f"Checking searches directory: {searches_dir}, exists={searches_dir.exists()}")
                    
                    if searches_dir.exists():
                        search_files = list(searches_dir.glob("*.parquet"))
                        logging.info(f"Found {len(search_files)} search files: {[s.name for s in search_files]}")
                    
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
                            logging.info(f"Loading search file: {file}")
                            df_temp = ParquetStorage.load_from_parquet(str(file))
                            if df_temp is not None and not df_temp.empty:
                                logging.info(f"File loaded successfully: {file.name}, shape: {df_temp.shape}")
                                # Log sample data from first row
                                if not df_temp.empty:
                                    logging.info(f"First row timestamp: {df_temp['timestamp'].iloc[0]}")
                                dfs.append(df_temp)
                            else:
                                logging.warning(f"File loaded but empty or None: {file}")
                        except Exception as e:
                            logging.error(f"Error loading search file {file}: {e}")

                    if not dfs:
                        await ctx.send("No valid search data found in the files.")
                        return

                    df = pd.concat(dfs, ignore_index=True)
                    logging.info(f"Combined DataFrame shape: {df.shape}")
                    data_desc = "DuckDuckGo searches"

                # Create df_info string with dataset information
                if df is None:
                    await ctx.send("⚠️ No data found matching your query criteria.")
                    return
                
                df_info = f"Total entries: {len(df)}\nColumns: {', '.join(df.columns)}\nDate range: {df['timestamp'].min()} to {df['timestamp'].max()}"
                
                # Execute the pandas query with the enhanced error logging
                logging.info(f"Executing query on DataFrame with columns: {df.columns.tolist()}")
                result = await PandasQueryEngine.execute_query(df, query)
                
                # Format response
                response_text = f"""# 📊 Data Query Results: {data_desc}

**Your query:** `{query}`

{result.get('result', 'No results available.')}

{result.get('explanation', '')}

## Tips
- Try `!pandas show searches from today`
- Try `!pandas count searches by date`
- Try `!pandas show most recent 5 searches`
"""
                await send_in_chunks(ctx, response_text, reference=ctx.message)
                    
        except Exception as e:
            logging.error(f"Error in pandas_query: {e}", exc_info=True)  # Added exc_info=True for full traceback
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

    @bot.command(name='links')
    async def collect_links(ctx, limit: int = None):
        """Collect all links from the channel and format them as markdown lists."""
        try:
            async with ctx.typing():
                # Default to 1000 messages if no limit specified
                message_limit = limit or 1000
                
                def create_markdown_chunk(chunk_num, total_chunks, links_data, items_to_show=None):
                    """Create a markdown chunk with detailed link information."""
                    markdown = f"""# 🔗 Links from #{links_data['channel_name']} (Part {chunk_num}/{total_chunks})

## Channel Information
- **Channel:** #{links_data['channel_name']}
- **Server:** {links_data['guild_name']}
- **Last Updated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC
- **Messages Searched:** {len(messages)}

## Statistics
- **Total Links Found:** {sum(len(items) for items in links_data['categories'].values())}
- **Categories Found:** {', '.join(cat.title() for cat, items in links_data['categories'].items() if items)}

## Links by Category
"""
                    if items_to_show:
                        for category, items in items_to_show.items():
                            if items:
                                markdown += f"\n### {category.title()} Links\n"
                                markdown += f"Found {len(items)} links in this category\n\n"
                                
                                for item in sorted(items, key=lambda x: x['timestamp'], reverse=True):
                                    ts = datetime.fromisoformat(item['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                                    domain = re.search(r'https?://(?:www\.)?([^/]+)', item['url'])
                                    domain = domain.group(1) if domain else 'unknown'
                                    
                                    markdown += f"#### [{domain}]({item['url']})\n"
                                    markdown += f"- **Shared by:** {item['author_name']}\n"
                                    markdown += f"- **Date:** {ts}\n"
                                    if item.get('context'):
                                        markdown += f"- **Context:** {item['context'][:100]}...\n"
                                    markdown += "\n"
                    
                    return markdown

                # Initialize link storage
                links_data = {
                    'channel_name': ctx.channel.name,
                    'channel_id': ctx.channel.id,
                    'guild_name': ctx.guild.name,
                    'guild_id': ctx.guild.id,
                    'timestamp': datetime.now(UTC).isoformat(),
                    'categories': {
                        'ollama_models': [],
                        'huggingface': [],
                        'model_repos': [],
                        'github': [],
                        'documentation': [],
                        'research': [],
                        'social': [],
                        'other': []
                    }
                }

                # Fetch and process messages
                messages = [msg async for msg in ctx.channel.history(limit=message_limit)]
                link_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+|\b\w+\.(?:com|org|net|edu|io|ai|dev)\b/[^\s<>"]*'
                
                # Extract and categorize links
                df_data = []
                for message in messages:
                    found_links = re.finditer(link_pattern, message.content)
                    for match in found_links:
                        link = match.group()
                        if not link.startswith(('http://', 'https://')):
                            link = 'https://' + link
                            
                        link_data = {
                            'url': link,
                            'timestamp': message.created_at.isoformat(),
                            'author_name': message.author.display_name,
                            'author_id': message.author.id,
                            'message_id': message.id,
                            'context': message.content[:200]
                        }
                        
                        # Categorize the link
                        if 'ollama.com' in link.lower():
                            if any(term in link.lower() for term in ['/library/', '/models/']):
                                links_data['categories']['ollama_models'].append(link_data)
                                category = 'ollama_models'
                            else:
                                links_data['categories']['documentation'].append(link_data)
                                category = 'documentation'
                        elif 'huggingface.co' in link.lower():
                            links_data['categories']['huggingface'].append(link_data)
                            category = 'huggingface'
                        elif 'github.com' in link.lower():
                            links_data['categories']['github'].append(link_data)
                            category = 'github'
                        elif any(doc in link.lower() for doc in ['docs.', 'documentation', 'readthedocs', 'wiki']):
                            links_data['categories']['documentation'].append(link_data)
                            category = 'documentation'
                        elif any(model in link.lower() for model in ['/models/', 'modelscope', 'modelzoo']):
                            links_data['categories']['model_repos'].append(link_data)
                            category = 'model_repos'
                        elif any(research in link.lower() for research in ['arxiv.org', 'research', 'paper', 'journal']):
                            links_data['categories']['research'].append(link_data)
                            category = 'research'
                        elif any(social in link.lower() for social in ['twitter.com', 'linkedin.com', 'discord.com']):
                            links_data['categories']['social'].append(link_data)
                            category = 'social'
                        else:
                            links_data['categories']['other'].append(link_data)
                            category = 'other'
                            
                        df_data.append({
                            'category': category,
                            **link_data,
                            **{k: v for k, v in links_data.items() if k != 'categories'}
                        })

                # Save to Parquet
                channel_name = re.sub(r'[^\w\-_]', '_', ctx.channel.name)
                parquet_filename = f"links_{channel_name}_{datetime.now(UTC).strftime('%Y%m%d')}.parquet"
                parquet_path = Path(DATA_DIR) / 'links' / parquet_filename
                Path(DATA_DIR).joinpath('links').mkdir(exist_ok=True)
                
                if df_data:
                    df = pd.DataFrame(df_data)
                    ParquetStorage.save_to_parquet(df, parquet_path)

                # Process links into markdown chunks
                markdown_chunks = []
                current_chunk_items = defaultdict(list)
                current_size = 0
                chunk_number = 1

                # Process each category
                for category, items in links_data['categories'].items():
                    if not items:
                        continue
                        
                    for item in items:
                        item_text = f"#### [{item['url']}]\n- Shared by {item['author_name']}\n"
                        
                        if current_size + len(item_text) > 1500:
                            chunk_content = create_markdown_chunk(chunk_number, 0, links_data, current_chunk_items)
                            markdown_chunks.append(chunk_content)
                            current_chunk_items = defaultdict(list)
                            current_size = 0
                            chunk_number += 1
                        
                        current_chunk_items[category].append(item)
                        current_size += len(item_text)

                # Add the final chunk if there's any content left
                if current_size > 0:
                    chunk_content = create_markdown_chunk(chunk_number, 0, links_data, current_chunk_items)
                    markdown_chunks.append(chunk_content)
                
                # Update total chunks count in all chunks
                total_chunks = len(markdown_chunks)
                for i in range(total_chunks):
                    markdown_chunks[i] = markdown_chunks[i].replace(f"(Part {i+1}/0)", f"(Part {i+1}/{total_chunks})")

                # Send the results
                if not markdown_chunks:
                    await ctx.send("No links found in the specified message range.")
                    return
                    
                for chunk in markdown_chunks:
                    await send_in_chunks(ctx, chunk, reference=ctx.message)
                    
                # Provide a summary
                summary = f"Found {sum(len(items) for items in links_data['categories'].values())} links across {len(markdown_chunks)} categories."
                await ctx.send(summary)
                    
        except Exception as e:
            logging.error(f"Error collecting links: {e}")
            await ctx.send(f"⚠️ Error collecting links: {str(e)}")