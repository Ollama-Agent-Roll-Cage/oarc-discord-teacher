#!/usr/bin/env python3
"""
Test script for command handling in the OARC Discord Teacher Bot
Tests both mention-based and prefix-based command handling
"""

import os
import sys
import asyncio
import logging
import re
from unittest.mock import MagicMock, patch

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CommandTest")

async def test_command_parsing():
    """Test the command parsing logic"""
    # Mock bot and message objects
    bot = MagicMock()
    bot.user.id = 1234567890
    bot.all_commands = {
        "help": MagicMock(),
        "links": MagicMock(),
        "reset": MagicMock()
    }
    
    # Test cases - various command formats
    test_messages = [
        {
            "content": "<@1234567890> help",
            "expected_valid": True,
            "expected_command": "help"
        },
        {
            "content": "!help",
            "expected_valid": True,
            "expected_command": "help" 
        },
        {
            "content": "<@1234567890> /help",
            "expected_valid": True,
            "expected_command": "help"
        },
        {
            "content": "<@1234567890> links 100",
            "expected_valid": True,
            "expected_command": "links"
        },
        {
            "content": "!links 100",
            "expected_valid": True,
            "expected_command": "links"
        },
        {
            "content": "<@1234567890> What is Python?",
            "expected_valid": False,
            "expected_command": None
        }
    ]
    
    # Import the command parsing logic from main.py
    from splitBot.main import on_message
    
    print("\n=== Testing Command Parsing ===\n")
    
    for i, test_case in enumerate(test_messages):
        print(f"Test Case {i+1}: {test_case['content']}")
        
        # Create mock message
        message = MagicMock()
        message.content = test_case["content"]
        message.author.bot = False
        
        # Check if this is a mention
        mention_pattern = f'<@!?{bot.user.id}>'
        is_mention = bool(re.search(f'^{mention_pattern}\\s*', test_case["content"]))
        message._state = MagicMock()
        
        # Set up bot.mentioned_in to return True for mentions
        bot.user.mentioned_in = lambda msg: is_mention
        
        # Test if this would be a valid command
        content_without_mention = re.sub(f'^{mention_pattern}\\s*', '', test_case["content"])
        is_command = content_without_mention.startswith('!') or content_without_mention.startswith('/')
        is_valid_command = is_command and content_without_mention[1:].split(' ')[0].lower() in bot.all_commands
        
        # Print analysis
        print(f"  Is mention: {is_mention}")
        print(f"  Content without mention: '{content_without_mention}'")
        print(f"  Is command format: {is_command}")
        print(f"  Is valid command: {is_valid_command}")
        print(f"  Expected result: {test_case['expected_valid']}, Command: {test_case['expected_command']}")
        print("")
    
    print("Testing complete! Review the analysis to ensure command parsing works correctly.")

if __name__ == "__main__":
    asyncio.run(test_command_parsing())
