"""Step 0 gate: verify Telegram and Google Sheets credentials work.

Run from the repo root:  python scripts/check_setup.py

Checks, in order:
  1. .env loads and required values are present
  2. Telegram bot token is valid (getMe)
  3. Service account can open the spreadsheet (reads its title)

If ALLOWED_CHAT_ID is blank, also prints any recent updates the bot has seen
so you can grab the group's chat ID (post a message in the group first).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gspread
from telegram import Bot

from bot.config import load_config


async def main() -> None:
    config = load_config()
    print("[ok] .env loaded")

    bot = Bot(config.telegram_bot_token)
    async with bot:
        me = await bot.get_me()
        print(f"[ok] Telegram: connected as @{me.username} (id {me.id})")

        if config.allowed_chat_id is None:
            updates = await bot.get_updates(timeout=1)
            chats = {
                (u.message or u.edited_message).chat
                for u in updates
                if u.message or u.edited_message
            }
            if chats:
                print("[..] ALLOWED_CHAT_ID is blank. Chats seen recently:")
                for chat in chats:
                    print(f"     {chat.id}  ({chat.type}: {chat.title or chat.username})")
            else:
                print(
                    "[..] ALLOWED_CHAT_ID is blank and no updates seen. "
                    "Post any message in the group, then rerun."
                )

    client = gspread.service_account(filename=config.google_service_account_file)
    spreadsheet = client.open_by_key(config.spreadsheet_id)
    print(f'[ok] Google Sheets: opened "{spreadsheet.title}"')
    print("\nSetup gate passed." if config.allowed_chat_id else "\nSet ALLOWED_CHAT_ID, then rerun to pass the gate.")


if __name__ == "__main__":
    asyncio.run(main())
