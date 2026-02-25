from database import (
    get_user, add_user, update_user, update_user_credits,
    SessionLocal, PremiumCode, CreditCode
)
from datetime import datetime, timedelta

def register_redeem_commands(bot):
    @bot.message_handler(commands=['redeem'])
    async def redeem_command(message):
        try:
            user_id = message.from_user.id
            user = get_user(user_id)
            if not user:
                user = add_user(user_id)

            # Get code from message
            args = message.text.split()
            if len(args) != 2:
                await bot.reply_to(message, "<b>⚠️ Usage: /redeem [code]</b>")
                return
            
            code = args[1].upper()
            session = SessionLocal()

            # Try premium code first
            premium_code = session.query(PremiumCode).filter(
                PremiumCode.code == code,
                PremiumCode.used_by == None
            ).first()

            if premium_code:
                # Apply premium
                premium_code.used_by = user_id
                premium_code.used_at = datetime.utcnow()
                premium_until = datetime.utcnow() + timedelta(days=premium_code.days)
                update_user(user_id, premium_until=premium_until)
                session.commit()
                # If user is already premium, add time to existing subscription
                if user.premium_until and user.premium_until > datetime.utcnow():
                    premium_until = user.premium_until + timedelta(days=premium_code.days)
                else:
                    premium_until = datetime.utcnow() + timedelta(days=premium_code.days)
                remaining_time = premium_until - datetime.utcnow()
                days, seconds = remaining_time.days, remaining_time.seconds
                hours = seconds // 3600
                if days > 0:
                    time_str = f"{days} days"
                else:
                    time_str = f"{hours} hours"

                await bot.reply_to(message, 
                    f"<b>✨ Premium code redeemed successfully!\n"
                    # f"Premium activated for {premium_code.days} days\n"
                    f"Expires: {premium_until.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Remaining time: {time_str}</b>")
                return
            
            credit_code = session.query(CreditCode).filter(
                CreditCode.code == code,
                CreditCode.used_by == None
            ).first()

            if credit_code:
                # Apply credits
                credit_code.used_by = user_id
                credit_code.used_at = datetime.utcnow()
                update_user_credits(user_id, credit_code.credits)
                session.commit()

                await bot.reply_to(message,
                    f"<b>💰 Credit code redeemed successfully!\n"
                    f"Added {credit_code.credits} credits to your account!</b>")
                return
            
            await bot.reply_to(message, "<b>❌ Invalid or already used code.</b>")

        except Exception as e:
            await bot.reply_to(message, f"<b>⚠️ Error: {str(e)}</b>")
        finally:
            session.close()
