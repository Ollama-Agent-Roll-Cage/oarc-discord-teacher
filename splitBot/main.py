import os
import asyncio
import logging
import re
from datetime import datetime, timezone, UTC
import json
from pathlib import Path
from collections import defaultdict
import signal

from dotenv import load_dotenv
from discord import Intents, Message, Game, Status, File
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

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
                    # Get description from vision model
                    vision_response = await process_image_with_llava(
                        image_data, 
                        f"Describe this image in detail, addressing this query: {content}"
                    )
                    
                    await send_in_chunks(message.channel, 
                        f"# 🖼️ Vision Analysis\n\n{vision_response}", message)
                    
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
                # Ensure we pass the correct conversation history to the model
                # Create messages for the current conversation
                messages_for_model = conversation_logs.copy()
                messages_for_model.append({'role': 'user', 'content': f"{user_name} asks: {content}"})
                
                # Get a response from the model with conversation history
                async with message.channel.typing():
                    response = await get_ollama_response(
                        content,
                        with_context=True,
                        conversation_history=messages_for_model  # Pass full conversation
                    )
                
                # Only continue if we got a valid response
                if response and isinstance(response, str) and len(response.strip()) > 0:
                    # Check for any weird content insertions by limiting to a reasonable response length
                    if len(response) > 2000:
                        response = response[:2000] + "..."
                    
                    # Add to conversation logs
                    conversation_logs.append({'role': 'user', 'content': f"{user_name} asks: {content}"})
                    conversation_logs.append({'role': 'assistant', 'content': response})
                    
                    # Store in user history
                    await store_user_conversation(message, response, is_bot=True)
                    await send_in_chunks(message.channel, response, message)
                    
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
        if (CHANGE_NICKNAME):
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