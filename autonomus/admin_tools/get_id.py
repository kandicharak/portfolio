#!/usr/bin/env python3
"""
Telegram Admin Tool - Get Chat ID
Fetches Telegram updates and displays the Chat ID when a message is received.
"""

import os
import sys
import time
from pathlib import Path


def load_env_file(env_path):
    """Load environment variables from .env file."""
    env_vars = {}
    
    if not os.path.exists(env_path):
        print(f"ERROR: Environment file not found at {env_path}")
        return env_vars
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE pairs
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    return env_vars


def get_telegram_token(env_path):
    """Get Telegram token from environment file."""
    env_vars = load_env_file(env_path)
    return env_vars.get('TELEGRAM_TOKEN')


def get_chat_id(token):
    """Fetch Chat ID by waiting for a message from the bot."""
    print("WAITING FOR MESSAGE")
    
    while True:
        try:
            # Make request to Telegram Bot API
            response = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates"
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if there are any updates
                if 'result' in data and len(data['result']) > 0:
                    update = data['result'][0]
                    
                    # Check if the update contains a message
                    if 'message' in update:
                        message = update['message']
                        
                        # Extract chat ID
                        chat_id = message.get('chat', {}).get('id')
                        
                        if chat_id:
                            print(f"Your Chat ID: {chat_id}")
                            return str(chat_id)
            
            time.sleep(2)  # Wait 2 seconds before next check
            
        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
            time.sleep(2)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(2)


def main():
    """Main function to run the Chat ID fetcher."""
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.parent
    
    # Define paths
    env_path = script_dir / "generated_project" / ".env"
    
    # Check if .env file exists
    if not env_path.exists():
        print(f"ERROR: Environment file not found at {env_path}")
        print("Please create the .env file with TELEGRAM_TOKEN")
        sys.exit(1)
    
    # Get Telegram token
    token = get_telegram_token(str(env_path))
    
    if not token:
        print("ERROR: TELEGRAM_TOKEN not found in .env file")
        print("Please add TELEGRAM_TOKEN=your_token_here to the .env file")
        sys.exit(1)
    
    # Get Chat ID
    chat_id = get_chat_id(token)
    
    if chat_id:
        print(f"\n✅ Chat ID retrieved successfully!")
        print(f"   You can now use this ID for bot commands.")


if __name__ == "__main__":
    main()
