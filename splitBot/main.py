import os
import asyncio
import logging
import re
from datetime import datetime, timezone, UTC
import json
from pathlib import Path
from collections import defaultdict
import signal
from io import BytesIO

from dotenv import load_dotenv
from discord import Intents, Message, Game, Status, File, app_commands
from discord.ext import commands, tasks

# Import our modules
from utils import (
    send_in_chunks, get_user_key, store_user_conversation, 
    process_file_attachment, process_image_attachment, SYSTEM_PROMPT
)
from services import get_ollama_response, process_image_with_llava
from commands import register_commands

# Load environment variables from .env file
load_dotenv()

# Add this after loading environment variables:
logging.info(f"Environment configuration: OLLAMA_MODEL={os.getenv('OLLAMA_MODEL')}")
CONFIG_MODEL_NAME = os.getenv('CONFIG_MODEL_NAME', 'default_model_name')  # Define a default value if not set
logging.info(f"Config.py MODEL_NAME: {CONFIG_MODEL_NAME}")

# Update the logging configuration
logging.basicConfig(
    level=logging.ERROR,  # Change from WARNING to ERROR to reduce verbosity further
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set specific loggers to higher levels
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('diffusers').setLevel(logging.ERROR)
logging.getLogger('transformers').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('asyncio').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

# Configuration variables
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_DIR = os.getenv('DATA_DIR', 'data')
CHANGE_NICKNAME = True  # Set to True to change nickname, False to keep the default

# Create data directories
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/searches").mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/papers").mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/crawls").mkdir(parents=True, exist_ok=True)
Path(f"{DATA_DIR}/links").mkdir(parents=True, exist_ok=True)

# User profile directory
USER_PROFILES_DIR = os.path.join(DATA_DIR, 'user_profiles')
Path(USER_PROFILES_DIR).mkdir(parents=True, exist_ok=True)

# Global conversation tracking
conversation_logs = [{'role': 'system', 'content': SYSTEM_PROMPT}]
USER_CONVERSATIONS = defaultdict(lambda: [{'role': 'system', 'content': SYSTEM_PROMPT}])
COMMAND_MEMORY = defaultdict(dict)  # Stores persistent memory for commands

def get_prefix(bot, message):
    """Get the command prefix for the bot."""
    # Only respond to commands if the bot is mentioned
    if bot.user and bot.user.mentioned_in(message):
        content = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
        if content.startswith('!'):
            return '!'
    return commands.when_mentioned(bot, message)

# Initialize the bot
intents = Intents.default()
intents.message_content = True  # Explicitly enable message content intent
bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.remove_command('help')  # Remove the default help command

# Register all command handlers
register_commands(bot, USER_CONVERSATIONS, COMMAND_MEMORY, conversation_logs, USER_PROFILES_DIR)

async def setup_slash_commands():
    """Set up Discord slash commands."""
    logging.info("Setting up slash commands...")
    
    @bot.tree.command(name="help", description="Display help information")
    async def slash_help(interaction):
        """Display help information."""
        help_text = """# 🤖 Ollama Teacher Bot Commands

## Personal Commands
- `/profile` - View your learning profile
- `/reset` - Clear your conversation history

## AI-Powered Commands
- `/arxiv` - Learn from ArXiv papers
- `/search` - Search DuckDuckGo and learn
- `/crawl` - Learn from web pages
- `/query` - Query stored data using natural language
- `/links` - Collect and organize links from channel history

## Image Generation
- `/sdxl` - Generate AI images with SDXL
- `/queue` - Check status of the image generation queue

## Special Features
- Add `--groq` flag to use Groq's API for potentially improved responses
- Add `--llava` flag with an attached image to use vision models
- Simply mention the bot to start a conversation without commands

## Download and build your own custom OllamaDiscordTeacher from the GitHub repo:
https://github.com/Leoleojames1/OllamaDiscordTeacher/tree/master
"""
        await interaction.response.send_message(help_text, ephemeral=True)
    
    @bot.tree.command(name="reset", description="Reset your conversation history")
    async def slash_reset(interaction):
        """Reset the user's conversation log."""
        user_key = f"{interaction.guild_id}_{interaction.user.id}"
        USER_CONVERSATIONS[user_key] = [{'role': 'system', 'content': SYSTEM_PROMPT}]
        COMMAND_MEMORY[user_key].clear()
        await interaction.response.send_message("✅ Your conversation context has been reset.", ephemeral=True)
    
    @bot.tree.command(name="profile", description="View your learning profile")
    async def slash_profile(interaction):
        """View your user profile."""
        user_key = f"{interaction.guild_id}_{interaction.user.id}"
        user_name = interaction.user.display_name or interaction.user.name
        profile_path = os.path.join(USER_PROFILES_DIR, f"{user_key}_profile.json")
        
        # Check if profile exists
        if not os.path.exists(profile_path):
            await interaction.response.send_message("No profile found. Interact with me more to build your profile!", ephemeral=True)
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
        await interaction.response.send_message(profile_text, ephemeral=True)
    
    @bot.tree.command(name="links", description="Collect links from recent messages")
    @app_commands.describe(limit="Number of messages to search (default: 100)")
    async def slash_links(interaction, limit: int = 100):
        """Collect all links from the channel and format them as markdown lists."""
        await interaction.response.defer()
        
        try:
            # Fetch messages
            messages = await interaction.channel.history(limit=limit).flatten()
            
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
                await interaction.followup.send(f"No links found in the last {limit} messages.")
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
                file_path = links_dir / f"links_{interaction.guild_id}_{timestamp}_part{i+1}.md"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(chunk)
                
                # Send the file
                await interaction.followup.send(
                    f"Links collection part {i+1} of {len(markdown_chunks)}", 
                    file=File(file_path)
                )
            
            # Also save to parquet for database access
            links_file = links_dir / f"links_{interaction.guild_id}_{timestamp}.parquet"
            all_links = []
            for category, items in links_data.items():
                for item in items:
                    item['category'] = category
                    all_links.append(item)
                    
            if all_links:
                ParquetStorage.save_to_parquet(all_links, str(links_file))
                logging.info(f"Links saved to {links_file}")
                
        except Exception as e:
            logging.error(f"Error collecting links: {e}")
            await interaction.followup.send(f"⚠️ Error collecting links: {str(e)}")

@bot.event
async def on_message(message: Message):
    """Handles incoming messages."""
    global conversation_logs
    if message.author == bot.user:
        return

    user_name = message.author.display_name or message.author.name
    user_key = get_user_key(message)
    
    if bot.user and bot.user.mentioned_in(message):
        content = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
        use_llava = '--llava' in content
        
        # Handle vision model if --llava flag is present and there's an image
        if use_llava and message.attachments:
            try:
                content = content.replace('--llava', '').strip()
                image_data = await process_image_attachment(message.attachments[0])
                
                async with message.channel.typing():
                    # Get selected vision model name
                    vision_model = os.getenv('OLLAMA_VISION_MODEL', 'llava')
                    
                    # Get description from vision model
                    vision_response = await process_image_with_llava(
                        image_data, 
                        f"Describe this image in detail, addressing this query: {content}"
                    )
                    
                    await send_in_chunks(message.channel, 
                        f"# 🖼️ Vision Analysis (using {vision_model})\n\n{vision_response}", message)
                    
                    # Store in conversation history
                    await store_user_conversation(
                        message,
                        f"Asked about image with query: {content}"
                    )
                    await store_user_conversation(
                        message,
                        vision_response,
                        is_bot=True
                    )
                return
                
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing image: {str(e)}")
                return

        # Continue with regular message processing
        # Store user information
        await store_user_conversation(message, content)
        
        # Process commands if starts with !
        if content.startswith('!'):
            message.content = content
            await bot.process_commands(message)
            return  # This return is critical to prevent double processing
            
        # Handle conversation for non-command mentions
        else:
            try:
                # Get selected model name
                model_name = os.getenv('OLLAMA_MODEL', 'Unknown model')
                
                # Ensure we pass the correct conversation history to the model
                # Create messages for the current conversation
                messages_for_model = conversation_logs.copy()
                messages_for_model.append({'role': 'user', 'content': f"{user_name} asks: {content}"})
                
                # Get a response from the model with conversation history
                async with message.channel.typing():
                    # Increase timeout for complex requests
                    response = await get_ollama_response(
                        content,
                        with_context=True,
                        conversation_history=messages_for_model,
                        timeout=180.0  # Increase timeout for complex requests
                    )
                
                # Only continue if we got a valid response
                if response and isinstance(response, str) and len(response.strip()) > 0:
                    # Check for any weird content insertions by limiting to a reasonable response length
                    if len(response) > 10000:  # Increase max length
                        response = response[:10000] + "\n\n[Response truncated due to length]"
                    
                    # Add model name as a footer
                    response += f"\n\n---\n*Response generated using {model_name}*"
                    
                    # Add to conversation logs
                    conversation_logs.append({'role': 'user', 'content': f"{user_name} asks: {content}"})
                    conversation_logs.append({'role': 'assistant', 'content': response})
                    
                    # Store in user history
                    await store_user_conversation(message, response, is_bot=True)
                    
                    # Use improved chunking for sending messages
                    await send_in_chunks(message.channel, response, message, chunk_size=1950)  # Smaller chunks for safety
                    
                    # Also update the per-user conversation history
                    USER_CONVERSATIONS[user_key].append({'role': 'user', 'content': content, 'timestamp': datetime.now(UTC).isoformat()})
                    USER_CONVERSATIONS[user_key].append({'role': 'assistant', 'content': response, 'timestamp': datetime.now(UTC).isoformat()})
            
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
        
        # Set up slash commands
        await setup_slash_commands()
        await bot.tree.sync()  # Sync commands with Discord
        
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
                        'joined_at': member.joined_at.isoformat() if member.joined_at else None
                    }
            
            # Save member data
            member_file = guild_dir / 'members.json'
            with open(member_file, 'w', encoding='utf-8') as f:
                json.dump(member_data, f, indent=2)
        
        # Change nicknames if enabled
        if (CHANGE_NICKNAME):
            for guild in bot.guilds:
                try:
                    await change_nickname(guild)
                except Exception as e:
                    logging.error(f"Failed to change nickname in guild {guild.name}: {str(e)}")
        
        # Set custom status with help command info
        status_text = "/help | Mention me with questions!"
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
            # Skip if doesn't match expected format
            if '_' not in user_key:
                continue
                
            try:
                guild_id, user_id = user_key.split('_')
                user_id = int(user_id)
            except ValueError:
                continue
            
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
            username = bot.get_user(user_id).name if bot.get_user(user_id) else 'Unknown'
            profile_data = {
                'timestamp': datetime.now(UTC).isoformat(),
                'analysis': analysis,
                'username': username
            }
            
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2)
                
    except Exception as e:
        logging.error(f"Error in analyze_user_profiles: {e}")

def signal_handler(sig, frame):
    """Handle interrupt signals to shut down gracefully."""
    logging.info("Interrupt received, shutting down...")
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    # Run cleanup code if needed
    logging.info("Bot shutdown complete.")
    # Exit cleanly
    asyncio.get_event_loop().stop()

def main():
    """Main function to run the bot."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot.run(TOKEN)

if __name__ == '__main__':
    main()