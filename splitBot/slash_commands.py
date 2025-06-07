"""
Module for handling Discord slash commands.
This provides helpers to register and manage slash commands properly.
"""

import logging
import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from discord import Interaction

# Import necessary modules
from splitBot.utils import get_user_key, SYSTEM_PROMPT
from splitBot.commands import reset_internal, view_profile_internal, collect_links_internal

logger = logging.getLogger(__name__)

async def register_slash_commands(bot):
    """Register all slash commands with Discord"""
    try:
        # Register reset command
        @bot.tree.command(name="reset", description="Reset your conversation history")
        async def reset_command(interaction: Interaction):
            """Reset the user's conversation history"""
            await interaction.response.defer(ephemeral=True)
            result = await reset_internal(interaction)
            await interaction.followup.send(result, ephemeral=True)

        # Register profile command
        @bot.tree.command(name="profile", description="View your learning profile")
        @app_commands.describe(question="Optional question about your learning history")
        async def profile_command(interaction: Interaction, question: str = None):
            """View your learning profile or ask questions about it"""
            await interaction.response.defer(ephemeral=True)
            result = await view_profile_internal(interaction, question)
            
            # Split response if too long
            if len(result) > 1900:
                chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
                await interaction.followup.send(chunks[0], ephemeral=True)
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk, ephemeral=True)
            else:
                await interaction.followup.send(result, ephemeral=True)
        
        # Register links command
        @bot.tree.command(name="links", description="Collect links from channel history")
        @app_commands.describe(limit="Number of messages to scan (default: 100)")
        async def links_command(interaction: Interaction, limit: int = 100):
            """Collect links from channel history"""
            await interaction.response.defer(ephemeral=False)  # Visible to everyone
            result = await collect_links_internal(interaction.channel, limit)
            
            # Split response if too long
            if len(result) > 1900:
                chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
                await interaction.followup.send(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(result)
        
        # Register help command
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
- **@OllamaTeacher links [limit]** - Collect and organize links from channel history
- **@OllamaTeacher --llava** - Analyze an attached image

## Command Flags
- **--groq** - Use Groq API (more powerful but slower)
- **--memory** - Use persistent memory for follow-up questions
- **--llava** - Process attached images

## Examples
- @OllamaTeacher What is a transformer model?
- @OllamaTeacher arxiv 1706.03762 Explain this paper
- @OllamaTeacher ddg "Python async" How do I use asyncio?
- @OllamaTeacher links 500
- @OllamaTeacher --llava (with image attached) What's in this image?
"""
            # Use ephemeral message (only visible to the user who invoked the command)
            await interaction.response.send_message(help_text, ephemeral=True)
        
        # Sync the commands with Discord
        await bot.tree.sync()
        logger.info("Slash commands registered and synced successfully")
        
    except Exception as e:
        logger.error(f"Error registering slash commands: {e}")
        raise e
