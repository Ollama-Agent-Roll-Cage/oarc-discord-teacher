#!/usr/bin/env python3
"""
Test script to verify the command parsing logic for handling slash commands with mentions
"""
import re

def test_command_parsing():
    """Test command parsing with various inputs"""
    bot_id = "1234567890"
    all_commands = {"help", "reset", "links", "arxiv", "ddg", "crawl"}
    
    test_cases = [
        {"input": "<@1234567890> /links", "expected": "!links"},
        {"input": "<@1234567890> /links 500", "expected": "!links 500"},
        {"input": "<@1234567890> /help", "expected": "!help"},
        {"input": "<@1234567890> /reset", "expected": "!reset"},
        {"input": "<@1234567890> /unknown", "expected": None},
        {"input": "<@1234567890> Tell me about Python", "expected": None}
    ]
    
    print("\nTesting Command Parsing Logic:")
    print("==============================\n")
    
    for i, case in enumerate(test_cases, 1):
        print(f"Test {i}: '{case['input']}'")
        
        # Parse the input
        content = case['input'].strip()
        mention_pattern = f'<@!?{bot_id}>'
        content_without_mention = re.sub(f'^{mention_pattern}\\s*', '', content)
        
        # Check if it starts with a slash command
        cmd_output = None
        if content_without_mention.startswith('/'):
            command_name = content_without_mention[1:].split(' ')[0].lower()
            
            if command_name in all_commands:
                cmd_output = f"!{content_without_mention[1:]}"
        
        # Verify result
        success = cmd_output == case['expected']
        print(f"  Content without mention: '{content_without_mention}'")
        print(f"  Command extracted: '{command_name if 'command_name' in locals() else None}'")
        print(f"  Output: '{cmd_output}'")
        print(f"  Expected: '{case['expected']}'")
        print(f"  Result: {'✓ PASS' if success else '✗ FAIL'}")
        print()
    
if __name__ == "__main__":
    test_command_parsing()