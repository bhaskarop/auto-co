from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user, add_user

def register_start_command(bot: AsyncTeleBot):
    @bot.message_handler(func=lambda message: message.text and message.text[0] in ['/', '?', '.'] and message.text[1:].split('@')[0] == 'start')
    async def handle_start(message):
        user_id = message.from_user.id
        user = get_user(user_id)
        if not user:
            add_user(user_id)
            user = get_user(user_id)
        
        user_first_name = message.from_user.first_name if message.from_user.first_name else user_id
        user_link = f'<a href="tg://user?id={user_id}">{user_first_name}</a>'
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("👤 Buy", url="https://t.me/SajagOG"),
            InlineKeyboardButton("💬 Official Group", url="https://t.me/+IreuwCegIxs3MzM9")
        )
        
        await bot.reply_to(message, f"<b>Welcome {user_link}! \nUse /cmds to see available commands.</b>", reply_markup=markup, parse_mode='HTML')