import os
import asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from database import init_db
from commands.start import register_start_command
from commands.cmds import register_cmds_command
from commands.admin import register_admin_commands
from commands.me import register_me_command
from commands.bin_command import register_bin_command
from commands.credits_command import register_credits_commands
from commands.redeem_command import register_redeem_commands
from commands.plans import register_plans_command
from commands.shopify import register_resource_commands
import os

from dotenv import load_dotenv
import os

load_dotenv()


from gateways import register_gateways
from utils import Utils
from utils_fo.logger import Logger
BotCache = {}

TOKEN = 'YOUR BOT TOKEN HERE'

FREE_USER_LIMIT = int(os.environ.get('FREE_USER_LIMIT', '60'))
PREMIUM_USER_LIMIT = int(os.environ.get('PREMIUM_USER_LIMIT', '20'))
bot = AsyncTeleBot(TOKEN, parse_mode='HTML')

async def init():
    try:
        init_db()
        Utils.load_resources()
        register_start_command(bot)
        register_cmds_command(bot)
        register_admin_commands(bot)
        register_me_command(bot)
        register_bin_command(bot)
        register_credits_commands(bot)
        register_redeem_commands(bot)
        register_plans_command(bot)
        register_resource_commands(bot)
        await register_gateways(bot)
    except Exception as e:
        print(f"Error initializing bot: {e}")

async def clear_previous_updates():
    # Get the latest update id
    updates = await bot.get_updates()
    if updates:
        latest_update_id = max(update.update_id for update in updates)
        await bot.get_updates(offset=latest_update_id + 1)


async def main():
    # print("Stopping bot...")
    # try:
    #     await clear_previous_updates()
    # except Exception as e:
    #     print(f"Error stopping bot: {e}")

    print("Bot stopped. Starting again...")
    try:
        await init()
        await bot.polling()
    except Exception as e:
        print(f"Error running bot: {e}")

if __name__ == '__main__':
    asyncio.run(main())

