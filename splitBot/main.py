from datetime import datetime, timezone, UTC
from pathlib import Path
from collections import defaultdict
from io import BytesIO
import os
import sys
import logging
import asyncio
import aiohttp
import re  # Add regex import for command parsing

from dotenv import load_dotenv
from discord import Intents, Message, Game, Status, File, app_commands, Interaction
from discord.ext import commands, tasks

# Set up proper path to find modules regardless of where script is launched from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import bot modules - use explicit imports to avoid circular dependencies
from splitBot.utils import ParquetStorage, SYSTEM_PROMPT, send_in_chunks, get_user_key, store_user_conversation
from splitBot.config import DATA_DIR, MODEL_NAME, VISION_MODEL_NAME, TEMPERATURE, TIMEOUT, CHANGE_NICKNAME
from splitBot.commands import register_commands
from splitBot.services import get_ollama_response, process_image_with_llava
from splitBot.slash_commands import register_slash_commands  # Import slash commands

# Initialize these variables to be accessed from other modules
USER_CONVERSATIONS = defaultdict(lambda: [{'role': 'system', 'content': SYSTEM_PROMPT}])
COMMAND_MEMORY = defaultdict(dict)  # Add missing COMMAND_MEMORY initialization
USER_PROFILES_DIR = os.path.join(os.getenv('DATA_DIR', 'data'), 'user_profiles')

# Load environment variables from .env file
load_dotenv()

# Add this after loading environment variables - log configuration for debugging
logging.info(f"Environment configuration: OLLAMA_MODEL={os.getenv('OLLAMA_MODEL')}")
logging.info(f"Using MODEL_NAME from config.py: {MODEL_NAME}")
logging.info(f"Using VISION_MODEL_NAME from config.py: {VISION_MODEL_NAME}")

# Update the logging configuration
logging.basicConfig(
    level=logging.ERROR,    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
COMMAND_MEMORY = defaultdict(dict)  # Stores persistent memory for commands

# Update the get_prefix function to handle mentions or ! prefix
def get_prefix(bot, message):
    """Allow commands with either ! prefix or mention prefix"""
    # Return both the mention and ! as valid prefixes
    return commands.when_mentioned_or('!')(bot, message)

# Initialize the bot with appropriate intents
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

# Maximum file size for uploads
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB maximum file size

@bot.event
async def on_ready():
    """When the bot is ready, set up the commands and status"""
    logging.info(f"Bot connected as {bot.user}")
    
    # Set up slash commands
    logging.info("Setting up slash commands...")
    await register_slash_commands(bot)  # Pass the bot instance to the register function
    
    # Set the bot's status
    await bot.change_presence(
        activity=Game(name=f"with {MODEL_NAME} | Mention me!"),
        status=Status.online
    )
    
    # Change nickname in each guild if configured
    if CHANGE_NICKNAME:
        for guild in bot.guilds:
            try:
                await guild.me.edit(nick=f"Ollama Teacher")
                logging.info(f"Changed nickname in {guild.name}")
            except Exception as e:
                logging.warning(f"Could not change nickname in {guild.name}: {e}")
    
    logging.info("Bot is ready!")

async def register_slash_commands(bot):
    """Register slash commands with Discord"""
    # Help command
    @bot.tree.command(name="help", description="Get help with using the bot")
    async def slash_help(interaction: Interaction):
        """Respond with help information"""
        help_text = """
# Ollama Teacher Bot - Help Guide

## Basic Commands
- **@OllamaTeacher help** - Show this help message
- **@OllamaTeacher <question>** - Ask any question
- **@OllamaTeacher reset** - Reset your conversation history

## Special Commands
- **@OllamaTeacher arxiv <paper_id> <question>** - Ask about an arXiv paper
- **@OllamaTeacher ddg <search_query> <question>** - Search DuckDuckGo and ask about results
- **@OllamaTeacher crawl <url> <question>** - Ask about content from a website
- **@OllamaTeacher --llava** - Analyze an attached image

## Command Flags
- **--groq** - Use Groq API (more powerful but slower)
- **--memory** - Use persistent memory for follow-up questions
- **--llava** - Process attached images

## Examples
- @OllamaTeacher What is a transformer model?
- @OllamaTeacher arxiv 1706.03762 Explain this paper
- @OllamaTeacher ddg "Python async" How do I use asyncio?
- @OllamaTeacher --llava (with image attached) What's in this image?
"""
        # Use ephemeral message (only visible to the user who invoked the command)
        # Split into chunks if too long
        if len(help_text) > 2000:
            # First acknowledge the interaction
            await interaction.response.defer(ephemeral=True)
            
            # Split the text into chunks of max 1900 characters (leaving some room for formatting)
            chunks = [help_text[i:i+1900] for i in range(0, len(help_text), 1900)]
            
            # Send first chunk as followup
            await interaction.followup.send(chunks[0], ephemeral=True)
            
            # Send remaining chunks as additional followups
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.response.send_message(help_text, ephemeral=True)
    
    # Sync commands with Discord
    await bot.tree.sync()
    
    # Register other commands
    register_commands(bot)

@bot.event
async def on_message(message: Message):
    """Handle incoming messages"""
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Process commands first (this includes both mention prefixed commands and ! prefixed commands)
    ctx = await bot.get_context(message)
    
    # Handle command processing
    if ctx.valid:
        await bot.invoke(ctx)
        return
    
    # Handle mentions that aren't commands
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        # Check if message starts with a mention and contains a command
        content = message.content.strip()
        mention_pattern = f'<@!?{bot.user.id}>'
        content_without_mention = re.sub(f'^{mention_pattern}\\s*', '', content)
        
        # Check if the remaining content is a command (starts with /)
        if content_without_mention.startswith('/'):
            # Extract the command name (without the /)
            command_name = content_without_mention[1:].split(' ')[0].lower()
            
            # Try to find the command in the bot's commands
            cmd = bot.get_command(command_name)
            
            if cmd is not None:
                # Instead of creating a new message object, just call the command directly
                # Extract any arguments after the command name
                args_str = content_without_mention[len(command_name)+1:].strip()
                
                # Create a new context with the command
                ctx = await bot.get_context(message)
                ctx.command = cmd
                ctx.invoked_with = command_name
                
                # Invoke the command directly
                await cmd.callback(ctx, *([int(args_str)] if args_str.isdigit() else []))
                return
        
        # If not a command, handle as a regular mention
        await handle_mention(message)

async def handle_mention(message):
    """Handle direct bot mentions that aren't commands"""
    # Remove the mention from the message content
    content = message.content.replace(f'<@{bot.user.id}>', '').strip()
    
    # Check for image processing request with --llava flag
    if '--llava' in content:
        await process_image(message, content)
        return
    
    # Otherwise, just process as a normal question
    if content:  # Only process if there's actually content after removing mention
        # Generate and send response
        response = await get_ollama_response(content)
        await store_user_conversation(message, response, is_bot=True)
        await send_in_chunks(message.channel, response, reference=message)

async def process_image(message, content):
    """Process an image with the vision model"""
    try:
        # Check for attached images
        if len(message.attachments) == 0:
            await message.channel.send("Please attach an image to use with --llava flag.", reference=message)
            return
        
        # Get the first image attachment
        image = message.attachments[0]
        
        # Check file size
        if image.size > MAX_FILE_SIZE:
            await message.channel.send(f"Image too large. Maximum file size: {MAX_FILE_SIZE/1024/1024}MB", reference=message)
            return
        
        # Check file type
        if not image.content_type or not image.content_type.startswith('image/'):
            await message.channel.send("The attached file is not a recognized image format.", reference=message)
            return
        
        # Download the image
        image_data = await image.read()
        
        # Process the prompt (remove --llava flag)
        prompt = content.replace('--llava', '').strip()
        if not prompt:
            prompt = "What's in this image?"
            
        # Send a typing indicator since image processing can take time
        async with message.channel.typing():
            # Process with vision model
            response = await process_image_with_llava(image_data, prompt)
            
            # Send the response
            await store_user_conversation(message, response, is_bot=True)
            await send_in_chunks(message.channel, response, reference=message)
            
    except Exception as e:
        logging.error(f"Error processing image: {e}", exc_info=True)
        await message.channel.send(f"⚠️ Error processing image: {str(e)}", reference=message)

# Update the register_slash_commands function
async def register_slash_commands(bot):
    """Register slash commands with Discord"""
    # Help command
    @bot.tree.command(name="help", description="Get help with using the bot")
    async def slash_help(interaction: Interaction):
        """Respond with help information"""
        help_text = """
# Ollama Teacher Bot - Help Guide

## Basic Commands
- **@OllamaTeacher help** - Show this help message
- **@OllamaTeacher <question>** - Ask any question
- **@OllamaTeacher reset** - Reset your conversation history

## Special Commands
- **@OllamaTeacher arxiv <paper_id> <question>** - Ask about an arXiv paper
- **@OllamaTeacher ddg <search_query> <question>** - Search DuckDuckGo and ask about results
- **@OllamaTeacher crawl <url> <question>** - Ask about content from a website
- **@OllamaTeacher --llava** - Analyze an attached image

## Command Flags
- **--groq** - Use Groq API (more powerful but slower)
- **--memory** - Use persistent memory for follow-up questions
- **--llava** - Process attached images

## Examples
- @OllamaTeacher What is a transformer model?
- @OllamaTeacher arxiv 1706.03762 Explain this paper
- @OllamaTeacher ddg "Python async" How do I use asyncio?
- @OllamaTeacher --llava (with image attached) What's in this image?
"""
        # Use ephemeral message (only visible to the user who invoked the command)
        # Split into chunks if too long
        if len(help_text) > 2000:
            # First acknowledge the interaction
            await interaction.response.defer(ephemeral=True)
            
            # Split the text into chunks of max 1900 characters (leaving some room for formatting)
            chunks = [help_text[i:i+1900] for i in range(0, len(help_text), 1900)]
            
            # Send first chunk as followup
            await interaction.followup.send(chunks[0], ephemeral=True)
            
            # Send remaining chunks as additional followups
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.response.send_message(help_text, ephemeral=True)
    
    # Sync commands with Discord
    await bot.tree.sync()
    
    # Register other commands
    register_commands(bot)

# Run the bot
def main():
    """Main function to run the bot"""
    try:
        bot.run(TOKEN)
    except Exception as e:
        logging.error(f"Error running bot: {e}")
        
if __name__ == "__main__":
    main()