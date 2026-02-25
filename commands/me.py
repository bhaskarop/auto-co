from telebot.async_telebot import AsyncTeleBot
from database import get_user, add_user
import os
from datetime import datetime

ADMIN_ID = 5750284541

def register_me_command(bot: AsyncTeleBot):
    @bot.message_handler(commands=['info'])
    async def handle_me(message):
        user = get_user(message.from_user.id)
        chat_id = message.chat.id
        if not user:
            add_user(message.from_user.id)
            user = get_user(message.from_user.id)

        user_first_name = message.from_user.first_name
        user_id = message.from_user.id

        user_link = f'<a href="tg://user?id={user_id}">{user_first_name}</a>'
        role = "Owner ✌️" if user_id == ADMIN_ID else "🌟 Premium" if user.premium_until and user.premium_until > datetime.now() else "Free"
        if user.is_banned:
            role = "🚫 Banned"
        credits = user.credits

        premium_time_left = ""
        if user.premium_until and user.premium_until > datetime.now():
            time_diff = user.premium_until - datetime.now()
            years = time_diff.days // 365
            months = (time_diff.days % 365) // 30
            days = (time_diff.days % 365) % 30
            hours = time_diff.seconds // 3600
            minutes = time_diff.seconds % 3600 // 60

            if years > 0:
                premium_time_left = f"{years}y {months}m {days}d"
            elif months > 0:
                premium_time_left = f"{months}m {days}d"
            elif days > 0:
                if hours > 0:
                    premium_time_left = f"{days}d {hours}h"
                else:
                    premium_time_left = f"{days}d"
            elif hours > 0:
                premium_time_left = f"{hours}h {minutes}m"
            else:
                if minutes > 0:
                    premium_time_left = f"{minutes}m"
                else:
                    premium_time_left = f"{time_diff.seconds % 60}s"

        response = (
            f"<b>UserID:</b> <code>{user_id}</code>\n"
            f"<b>Username:</b> {message.from_user.username or 'Does not have!'}\n"
            f"<b>User:</b> {user_link}\n"
            f"<b>Credits:</b> <code>{credits}</code>\n"
            f"<b>Status:</b> {role}\n"
            + (f"<b>Premium Till:</b> {premium_time_left}\n" if premium_time_left else "")
            + (f"<b>ChatID:</b> <code>{chat_id}</code>\n" if chat_id != user_id else "")
        )

        await bot.reply_to(message, response, parse_mode='HTML')
