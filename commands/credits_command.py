from database import (
    get_user, add_user, can_redeem_daily, 
    redeem_daily_credits, get_user_credits,
    get_daily_credits_info
)

def register_credits_commands(bot):
    @bot.message_handler(commands=['daily'])
    async def daily_command(message):
        try:
            user_id = message.from_user.id
            user = get_user(user_id)
            if not user:
                user = add_user(user_id)
            
            if not can_redeem_daily(user_id):
                await bot.reply_to(
                    message, 
                    "<b>❌ You have already redeemed your daily credits. Please try again in 24 hours.</b>"
                )
                return
            
            success, amount = redeem_daily_credits(user_id)
            if success:
                await bot.reply_to(
                    message,
                    f"<b>✅ Successfully redeemed {amount} daily credits!\nHit /credits to know more!</b>"
                )
            else:
                await bot.reply_to(message, "<b>❌ Failed to redeem daily credits. Please try again later.</b>")

        except Exception as e:
            await bot.reply_to(message, f"Error: {str(e)}")
    
    @bot.message_handler(commands=['credits'])
    async def credits_command(message):
        try:
            user_id = message.from_user.id
            total_credits = get_user_credits(user_id)
            daily_info = get_daily_credits_info(user_id)

            if not daily_info:
                await bot.reply_to(message, "<b>❌ Error fetching credits information.</b>")
                return
            
            credits_msg = f"""<b>📊 Credits Information:
💰 Original Credits: {total_credits}
🎁 Daily Credits: {daily_info['credits']}
⏰ Next Daily: {daily_info['time_left']}</b>"""
            if daily_info['can_redeem']:
                credits_msg += "\n\n<b>✨ Tip: Use /daily to claim your daily credits!</b>"
            
            await bot.reply_to(message, credits_msg)

        except Exception as e:
            await bot.reply_to(message, f"Error: {str(e)}")
