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
    - `!arxiv <arxiv_url_or_id> [--memory] [--groq] <question>` - Learn from ArXiv papers
    - `!ddg <query> [--groq] [--llava] <question>` - Search DuckDuckGo and learn
    - `!crawl <url1> [url2 url3...] [--groq] <question>` - Learn from web pages
    - `!pandas <query>` - Query stored data using natural language
    - `!links [limit]` - Collect and organize links from channel history

    ## Admin Commands
    - `!globalReset` - Reset all conversations (admin only)

    ## Special Features
    - Add `--groq` flag to use Groq's API for potentially improved responses
    - Add `--llava` flag with an attached image to use vision models
    - Add `--memory` with arxiv command to enable persistent memory
    - Simply mention the bot to start a conversation without commands

    ## Examples
    ```
    !profile                                    # View your profile
    !profile What topics have I been learning?  # Ask about your progress
    !arxiv --memory 1706.03762 Tell me about attention mechanisms
    !arxiv 1706.03762 2104.05704 Compare these two papers  # Multiple papers
    !ddg "python asyncio" How to use async/await?
    !ddg --llava "neural network" How does this type match the image?  # With image
    !crawl https://pypi.org/project/ollama/ https://github.com/ollama/ollama Compare these
    !links 500                                  # Collect links from last 500 messages
    ```

    ## Technical Features
    - 🧠 Personal memory system that maintains conversation context
    - 🔍 Multiple information sources with intelligent extraction
    - 📊 Data analysis capabilities for structured information
    - 👁️ Vision processing for images with --llava flag
    - 💬 Natural language interactions with personalized responses

    ## Download and build your own custom OllamaDiscordTeacher from the github repo
    https://github.com/Leoleojames1/OllamaDiscordTeacher/tree/master
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
            # Check for flags
            user_key = get_user_key(ctx)
            use_memory = '--memory' in arxiv_ids
            use_groq = '--groq' in arxiv_ids
            
            # Remove flags from the arxiv_ids string
            arxiv_ids = arxiv_ids.replace('--memory', '').replace('--groq', '').strip()
            
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
                        
                        if (existing_paper is not None and len(existing_paper) > 0):
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
                    if use_memory and previous_context:
                        combined_prompt = "Previous conversation context:\n" + previous_context + "\n\n"
                        combined_prompt += "New information to consider:\n"
                    else:
                        combined_prompt = ""

                    combined_prompt += "I want to learn from these research papers:\n\n"
                    for paper in all_papers:
                        combined_prompt += f"--- Paper: {paper['id']} ---\n{paper['content']}\n\n"

                    combined_prompt += f"\nMy question is: {question}\n\nPlease provide a detailed answer using information from all papers."

                    ai_response = await get_ollama_response(combined_prompt, with_context=False, use_groq=use_groq)
                    
                    # Save context for future use if memory flag is enabled
                    if use_memory:
                        # Store both the question and response for better continuity
                        memory_context = f"Question: {question}\n\nResponse: {ai_response}\n\n"
                        
                        # Append to existing memory, but limit to prevent excessive token usage
                        if previous_context:
                            # Only keep the most recent part if getting too long
                            if len(previous_context) > 2000:
                                previous_context = previous_context[-2000:]
                            COMMAND_MEMORY[user_key]['arxiv'] = previous_context + memory_context
                        else:
                            COMMAND_MEMORY[user_key]['arxiv'] = memory_context
                    
                    # Format response with appropriate indicators
                    model_indicator = "🤖 Using Groq API" if use_groq else ""
                    memory_indicator = "🧠 Using Memory: Previous context incorporated" if use_memory and previous_context else ""
                    
                    # Combine indicators with newlines if they exist
                    indicators = "\n\n".join(filter(None, [model_indicator, memory_indicator]))
                    
                    # Start building the response text without the memory and flags parts
                    response_text = ""
                    if indicators:
                        response_text += indicators + "\n\n"
                    
                    response_text += f"# ArXiv Paper Analysis\n\n"
                    response_text += f"**Papers analyzed:** {', '.join(p['id'] for p in all_papers)}\n"
                    
                    # Add memory active info if relevant
                    if use_memory and previous_context:
                        response_text += f"**Memory active:** Previous context from {len(previous_context.split()) // 100} discussions\n"
                    
                    response_text += f"\n{ai_response}\n\n"
                    
                    # Add these separately, not in the f-string
                    if use_memory:
                        response_text += "Use !reset to clear your memory context\n"
                    else:
                        response_text += "Add --memory flag to enable persistent memory\n"
                    
                    if not use_groq:
                        response_text += "Add --groq flag to use Groq API"
                    
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
            # Check for flags
            use_groq = '--groq' in query
            use_llava = '--llava' in query
            
            # Clean flags from query
            query = query.replace('--groq', '').replace('--llava', '').strip()
            
            # Handle image input for llava
            image_data = None
            if use_llava and ctx.message.attachments:
                try:
                    image_data = await process_image_attachment(ctx.message.attachments[0])
                    # Get image description from llava
                    vision_prompt = f"Describe this image in detail and extract key searchable concepts that would be relevant to the query: {query}"
                    image_description = await process_image_with_llava(image_data, vision_prompt)
                    
                    # Combine image insights with original query
                    query = f"{query} {image_description}"
                    logging.info(f"Enhanced search query with vision: {query[:100]}...")
                    
                except Exception as e:
                    await ctx.send(f"⚠️ Error processing image: {str(e)}")
                    return
                    
            async with ctx.typing():
                # Log the search query
                logging.info(f"DuckDuckGo search: {query}")
                
                # Make sure to use quote marks around the query for better results
                if not (query.startswith('"') and query.endswith('"')):
                    actual_query = f'"{query}"'
                else:
                    actual_query = query
                    
                # Perform the search
                search_results = await DuckDuckGoSearcher.text_search(actual_query)
                
                # If the search didn't return useful results, try a more general query
                if "No results found" in search_results or len(search_results) < 100:
                    logging.info(f"Retrying search with more general query: {query}")
                    search_results = await DuckDuckGoSearcher.text_search(query.strip('"'))
                
                # If there's a question, use the AI to answer it based on the search results
                if question:
                    prompt = f"""I searched for information about "{query}" and got these results:

{search_results}

My question is: {question}

Please provide a concise, accurate response based on the search results.
If the search results don't contain relevant information about {query}, please explain what {query} is based on your knowledge.
"""
                    ai_response = await get_ollama_response(prompt, with_context=False, use_groq=use_groq)
                    
                    # Add Groq indicator if used
                    if use_groq:
                        ai_response = f"🤖 Using Groq API\n\n{ai_response}"
                        
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
            # Check for groq flag
            use_groq = False
            if '--groq' in urls:
                use_groq = True
                urls = urls.replace('--groq', '').strip()
                
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
                            package_data = await WebCrawler.extract_pypi_content(html_content, package_name)
                            if package_data:
                                content_text = package_data.get('documentation', 'No documentation available')
                                all_content.append({'url': url, 'content': content_text})
                    else:
                        # Handle regular URL
                        html_content = await WebCrawler.fetch_url_content(url)
                        if html_content:
                            content_text = await WebCrawler.extract_text_from_html(html_content)
                            all_content.append({'url': url, 'content': content_text})
                
                if not all_content:
                    await ctx.send("⚠️ Could not fetch content from any of the provided URLs")
                    return
                    
                # Combine all content for the question
                if question:
                    combined_prompt = "I've gathered information from multiple sources:\n\n"
                    for item in all_content:
                        combined_prompt += f"From {item['url']}:\n{item['content'][:5000]}...\n\n"
                    combined_prompt += f"\nMy question is: {question}\n\nPlease provide a detailed answer using information from all sources."
                    
                    ai_response = await get_ollama_response(combined_prompt, with_context=False, use_groq=use_groq)
                    
                    # Add Groq indicator if used
                    if use_groq:
                        response_text = f"🤖 Using Groq API\n\n{ai_response}"
                    else:
                        response_text = ai_response
                        
                    await send_in_chunks(ctx, response_text, reference=ctx.message)
                else:
                    # Send summaries of each source
                    for item in all_content:
                        header = f"# 🌐 Summary: {item['url']}\n\n"
                        summary = await get_ollama_response(f"Summarize this content:\n{item['content'][:7000]}", with_context=False, use_groq=use_groq)
                        
                        if use_groq:
                            response_text = f"🤖 Using Groq API\n\n{summary}"
                        else:
                            response_text = summary
                        
                        await send_in_chunks(ctx, header + response_text, reference=ctx.message)
                
        except Exception as e:
            logging.error(f"Error in crawl_url: {e}")
            await ctx.send(f"⚠️ Error: {str(e)}")

    @bot.command(name='pandas')
    async def pandas_query(ctx, *, query: str):
        """Query stored data using natural language and the Pandas Query Engine."""
        try:
            async with ctx.typing():
                user_key = get_user_key(ctx)
                
                # Load all relevant data
                dfs = []
                
                # Load conversation history
                if os.path.exists(f"{DATA_DIR}/conversations/{user_key}.parquet"):
                    conv_df = ParquetStorage.load_from_parquet(f"{DATA_DIR}/conversations/{user_key}.parquet")
                    if conv_df is not None:
                        dfs.append(conv_df)

                # Load search history  
                searches_dir = Path(f"{DATA_DIR}/searches")
                if searches_dir.exists():
                    for file in searches_dir.glob("*.parquet"):
                        search_df = ParquetStorage.load_from_parquet(str(file))
                        if search_df is not None:
                            dfs.append(search_df)

                # Combine all data
                if not dfs:
                    await ctx.send("No data found to query")
                    return
                    
                df = pd.concat(dfs, ignore_index=True)

                # Execute query
                result = await PandasQueryEngine.execute_query(df, query)

                if result["success"]:
                    response = f"""# Query Results
Your query: `{query}`

{result["result"]}

Found {result.get("count", "N/A")} matching records.
"""
                else:
                    response = f"""# Query Error
Sorry, I couldn't process that query: {result["error"]}

Try queries like:
- "show my recent conversations"
- "what topics have I searched for today"
- "count messages by date"
"""

                await send_in_chunks(ctx, response)

        except Exception as e:
            logging.error(f"Error in pandas_query: {e}", exc_info=True)
            await ctx.send(f"⚠️ Error querying data: {str(e)}")

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