import os
import re
import logging
import json
from datetime import datetime, timezone, UTC
from pathlib import Path
from collections import defaultdict
import pandas as pd
from discord import File
import asyncio
from io import BytesIO
import re

from utils import (
    send_in_chunks, get_user_key, store_user_conversation,
    ParquetStorage, PandasQueryEngine, DEFAULT_RESOURCES, SYSTEM_PROMPT
)
from services import (
    get_ollama_response, ArxivSearcher, DuckDuckGoSearcher, WebCrawler
)
from image_queue import ImageGenerationQueue

# Initialize logging
logger = logging.getLogger(__name__)

# Configure data directory
DATA_DIR = os.getenv('DATA_DIR', 'data')

def register_commands(bot, USER_CONVERSATIONS, COMMAND_MEMORY, conversation_logs, USER_PROFILES_DIR):
    """Register all bot commands."""
    
    # Create a global image queue for the bot
    image_queue = ImageGenerationQueue(rate_limit_count=3, rate_limit_period=3600)  # 3 images per hour

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

    # Update the help_command function in commands.py
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

## Image Generation
- `!sdxl <prompt> [--width <pixels>] [--height <pixels>] [--steps <count>] [--guidance <value>]` - Generate AI images with SDXL
- `!sdxl_queue` - Check the status of the image generation queue and your usage

## Admin Commands
- `!globalReset` - Reset all conversations (admin only)

## Special Features
- Add `--groq` flag to use Groq's API for potentially improved responses
- Add `--llava` flag with an attached image to use vision models
- Add `--memory` with arxiv command to enable persistent memory
- Simply mention the bot to start a conversation without commands

## Examples

- `!profile`  
  View your profile  
- `!profile What topics have I been learning?`  
  Ask about your progress  
- `!arxiv --memory 1706.03762 Tell me about attention mechanisms`  
  Learn from a specific paper  
- `!arxiv 1706.03762 2104.05704 Compare these two papers`  
  Analyze multiple papers  
- `!ddg "python asyncio" How to use async/await?`  
  Search DuckDuckGo with a query  
- `!ddg --llava "neural network" How does this type match the image?`  
  Use vision models with an image  
- `!crawl https://pypi.org/project/ollama/ https://github.com/ollama/ollama Compare these`  
  Crawl and compare web pages  
- `!links 500`  
  Collect links from the last 500 messages  
- `!sdxl A beautiful sunset over mountains --width 1024 --height 768`  
  Generate an image  

## Technical Features
- 🧠 Personal memory system that maintains conversation context
- 🔍 Multiple information sources with intelligent extraction
- 📊 Data analysis capabilities for structured information
- 👁️ Vision processing for images with `--llava` flag
- 🖼️ Image generation with Stable Diffusion XL
- 💬 Natural language interactions with personalized responses

## Download and build your own custom OllamaDiscordTeacher from the GitHub repo:
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
                if limit is None:
                    limit = 100  # Default limit
                
                # Fetch messages
                messages = await ctx.channel.history(limit=limit).flatten()
                
                # Extract links with metadata
                links_data = defaultdict(list)
                
                for msg in messages:
                    if msg.author.bot:
                        continue
                        
                    # Extract URLs from message content
                    urls = re.findall(r'(https?://\S+)', msg.content)
                    
                    for url in urls:
                        # Clean URL (remove trailing punctuation)
                        url = url.rstrip(',.!?;:\'\"')
                        
                        # Categorize based on domain
                        domain = urllib.parse.urlparse(url).netloc
                        category = "Other"
                        
                        if "github" in domain:
                            category = "GitHub"
                        elif "arxiv" in domain:
                            category = "Research Papers"
                        elif "huggingface" in domain or "hf.co" in domain:
                            category = "Hugging Face"
                        elif "youtube" in domain or "youtu.be" in domain:
                            category = "Videos"
                        elif "docs" in domain or "documentation" in domain:
                            category = "Documentation"
                        elif "pypi" in domain:
                            category = "Python Packages"
                        
                        links_data[category].append({
                            'url': url,
                            'timestamp': msg.created_at.isoformat(),
                            'author_name': msg.author.display_name or msg.author.name,
                            'author_id': msg.author.id
                        })
                
                # Create markdown chunks
                if not any(links_data.values()):
                    await ctx.send(f"No links found in the last {limit} messages.")
                    return
                    
                # Format as Markdown chunks
                markdown_chunks = []
                current_chunk = "# Links Collection\n\n"
                current_chunk += f"*Collected from the last {limit} messages*\n\n"
                
                for category, links in links_data.items():
                    if not links:
                        continue
                        
                    current_chunk += f"## {category}\n\n"
                    
                    for link in links:
                        link_entry = f"- [{link['url']}]({link['url']})\n  - Shared by {link['author_name']}\n  - {link['timestamp'][:10]}\n\n"
                        
                        # If chunk gets too large, start a new one
                        if len(current_chunk) + len(link_entry) > 1900:
                            markdown_chunks.append(current_chunk)
                            current_chunk = f"# Links Collection (Continued)\n\n"
                        
                        current_chunk += link_entry
                
                # Add the last chunk if there's any content left
                if current_chunk and len(current_chunk) > 50:  # Not just the header
                    markdown_chunks.append(current_chunk)
                
                # Save links to storage
                timestamp = int(datetime.now(UTC).timestamp())
                links_dir = Path(f"{DATA_DIR}/links")
                links_dir.mkdir(parents=True, exist_ok=True)
                
                # Save to a file and send as attachment
                for i, chunk in enumerate(markdown_chunks):
                    file_path = links_dir / f"links_{ctx.guild.id}_{timestamp}_part{i+1}.md"
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(chunk)
                    
                    # Send the file
                    await ctx.send(f"Links collection part {i+1} of {len(markdown_chunks)}", file=File(file_path))
                
                # Also save to parquet for database access
                links_file = links_dir / f"links_{ctx.guild.id}_{timestamp}.parquet"
                all_links = []
                for category, items in links_data.items():
                    for item in items:
                        item['category'] = category
                        all_links.append(item)
                        
                if all_links:
                    ParquetStorage.save_to_parquet(all_links, str(links_file))
                    logging.info(f"Links saved to {links_file}")
                    
                # Schedule a background content extraction
                asyncio.create_task(extract_content_from_links(links_data, ctx.guild.id))
                    
        except Exception as e:
            logging.error(f"Error collecting links: {e}")
            await ctx.send(f"⚠️ Error collecting links: {str(e)}")

    # New function to extract content from links periodically
    async def extract_content_from_links(links_data, guild_id):
        """Extract content from collected links for the knowledge database."""
        try:
            from services import WebCrawler
            
            # Create knowledge directory
            knowledge_dir = Path(f"{DATA_DIR}/knowledge/{guild_id}")
            knowledge_dir.mkdir(parents=True, exist_ok=True)
            
            # Process links by category
            for category, links in links_data.items():
                for link in links:
                    url = link['url']
                    domain = urllib.parse.urlparse(url).netloc
                    
                    # Skip videos for now (will be handled separately)
                    if "youtube" in domain or "youtu.be" in domain:
                        continue
                    
                    try:
                        # Get content
                        html = await WebCrawler.fetch_url_content(url)
                        if not html:
                            continue
                            
                        # Extract text from HTML
                        content = await WebCrawler.extract_text_from_html(html)
                        
                        # Create a document with metadata
                        document = {
                            'url': url,
                            'domain': domain,
                            'category': category,
                            'content': content,
                            'timestamp': link['timestamp'],
                            'author_name': link['author_name'],
                            'author_id': link['author_id'],
                            'extraction_time': datetime.now(UTC).isoformat()
                        }
                        
                        # Save to knowledge database
                        filename = f"{domain.replace('.', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.parquet"
                        ParquetStorage.save_to_parquet(document, str(knowledge_dir / filename))
                        
                    except Exception as e:
                        logging.error(f"Error processing link {url}: {e}")
                        continue
                        
            logging.info(f"Content extraction completed for {sum(len(links) for links in links_data.values())} links")
            
        except Exception as e:
            logging.error(f"Error in background content extraction: {e}")

    @bot.command(name='sdxl')
    async def sdxl_generate(ctx, *, prompt: str = None):
        """Generate an image with Stable Diffusion XL with content moderation."""
        if not prompt:
            await ctx.send("⚠️ Please provide a prompt for image generation.\nExample: `!sdxl A beautiful sunset over mountains --width 768 --height 768 --steps 20 --guidance 7.5`")
            return
        
        try:
            # Parse arguments with more conservative defaults
            width = 768  # Smaller default size
            height = 768  # Smaller default size
            steps = 20   # Fewer steps
            guidance = 7.5
            negative_prompt = "low quality, blurry, distorted, deformed, ugly, bad anatomy"
        
            # Extract parameters from prompt if provided
            if "--width" in prompt:
                width_match = re.search(r'--width\s+(\d+)', prompt)
                if width_match:
                    width = min(int(width_match.group(1)), 1024)  # Cap at 1024
                    prompt = prompt.replace(width_match.group(0), '')
            
            if "--height" in prompt:
                height_match = re.search(r'--height\s+(\d+)', prompt)
                if height_match:
                    height = min(int(height_match.group(1)), 1024)  # Cap at 1024
                    prompt = prompt.replace(height_match.group(0), '')
            
            if "--steps" in prompt:
                steps_match = re.search(r'--steps\s+(\d+)', prompt)
                if steps_match:
                    steps = min(int(steps_match.group(1)), 30)  # Cap at 30 steps
                    prompt = prompt.replace(steps_match.group(0), '')
            
            if "--guidance" in prompt:
                guidance_match = re.search(r'--guidance\s+([\d\.]+)', prompt)
                if guidance_match:
                    guidance = float(guidance_match.group(1))
                    guidance = max(1.0, min(guidance, 10.0))  # Clamp between 1.0 and 10.0
                    prompt = prompt.replace(guidance_match.group(0), '')
                    
            if "--negative" in prompt:
                negative_match = re.search(r'--negative\s+"([^"]+)"', prompt)
                if negative_match:
                    negative_prompt = negative_match.group(1)
                    prompt = prompt.replace(negative_match.group(0), '')
            
            # Clean up the prompt
            prompt = prompt.strip()
            
            # Get user key for queue management
            user_key = get_user_key(ctx)
            
            # Generate a unique filename
            timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
            output_dir = os.path.join(DATA_DIR, "generated_images")
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{output_dir}/sdxl_{user_key}_{timestamp}.png"
            
            # Define the async generator function to pass to the queue
            async def generate_image_task():
                from sdxl_access import SDXLGenerator
                from io import BytesIO
                
                # Create generator and ensure it loads the model
                generator = SDXLGenerator()
                if not generator.load_model():
                    raise Exception("Failed to load SDXL model")
                    
                # Generate the image
                image_data = generator.generate_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    steps=steps,
                    guidance_scale=guidance,
                    output_path=filename
                )
                
                # Unload the model when done to free memory
                generator.unload_model()
                
                return image_data
            
            # Define status update callback
            async def status_update(message):
                await ctx.send(message)
                
            # Define callback for when image is complete
            async def image_complete(image_data):
                if image_data:
                    # Send the file to Discord
                    await ctx.send(f"✅ Generated image for '{prompt}' (w:{width}, h:{height}, steps:{steps}, guidance:{guidance:.1f})", 
                                file=File(image_data, filename=f"sdxl_image_{timestamp}.png"))
                else:
                    await ctx.send(f"❌ Failed to generate image")
                    
            # Define error callback
            async def error_callback(error_message):
                await ctx.send(f"⚠️ Error generating image: {error_message}")
            
            # Add the task to the queue
            result = await image_queue.add_to_queue({
                'user_key': user_key,
                'prompt': prompt,
                'generator_func': generate_image_task,
                'callback': image_complete,
                'error_callback': error_callback,
                'width': width,
                'height': height,
                'steps': steps,
                'guidance': guidance
            })
            
            # Register for status updates
            image_queue.register_status_update(user_key, status_update)
            
            # Inform the user about queue status
            if not result['success']:
                await ctx.send(result['message'])
            else:
                message = f"✅ Your image request has been {result['message'].lower()}"
                if result['position'] > 0:
                    message += f" at position {result['position']}"
                await ctx.send(message)
                
        except Exception as e:
            logging.error(f"Error in sdxl_generate: {e}", exc_info=True)
            await ctx.send(f"⚠️ Error: {str(e)}")
    
    # Add a queue status command
    @bot.command(name='sdxl_queue')
    async def sdxl_queue_status(ctx):
        """Check the status of the image generation queue."""
        status = image_queue.get_queue_status()
        user_key = get_user_key(ctx)
        user_usage = image_queue.get_user_usage(user_key)
        
        status_text = f"""# 🖼️ SDXL Queue Status

## Current Queue
- Queue size: {status['queue_size']} pending requests
- Active generation: {"Yes" if status['active_generation'] else "No"}

## Your Usage
- Generated: {user_usage}/3 images this hour
- Rate limit: 3 images per hour per user

## Model Information
- Model: randommaxxArtMerge_v10
- Default settings: 1024x1024, 28 steps, 7.5 guidance
"""
        
        await ctx.send(status_text)