# Use environment variables instead
# Create a .env file with:
# BOT_TOKEN=your_bot_token_here
# ADMIN_ID=your_admin_id_here

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))