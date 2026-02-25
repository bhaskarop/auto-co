from telebot.async_telebot import AsyncTeleBot
from database import (
    get_user, update_user, authorize_group, get_group, is_group_authorized,
    create_premium_code, create_credit_code, ban_user, unauthorize_group, get_live_cards,
    query_cards, get_user_stats, get_premium_users, get_all_users, get_all_groups, get_db_stats, get_users_with_credits, get_banned_users
)

from datetime import datetime, timedelta
import os

from .base_command import BaseCommand

ADMIN_ID = 'Your Chat Id'

def register_admin_commands(bot: AsyncTeleBot):
    @bot.message_handler(func=lambda message: message.text and message.text[0] in ['/', '?', '.'] and
                        message.text[1:].split()[0].split('@')[0] in ['pgen', 'cgen', 'ban', 'unban', 'authg', 'lives', 'senddb', 'gate', 'broadcast'])
    
    async def handle_admin_commands(message):
        try:
            if str(message.from_user.id) != str(ADMIN_ID):
                await bot.reply_to(message, "🚫 You are not authorized to use this command.")
                return
            
            command, *args = message.text[1:].split()
            command = command.split('@')[0]

            if command == 'senddb':
                db_path = 'cocobot.db'
                if os.path.exists(db_path):
                    with open(db_path, 'rb') as f:
                        await bot.send_document(message.chat.id, f, caption="📂 Database File")
                else:
                    await bot.reply_to(message, "⚠️ Database file not found.")
                return
            
            if command == 'gate':
                if len(args) < 2:
                    await bot.reply_to(message, "**Invalid Format\n/gate [command] [enable/disable/premium/regular]**", parse_mode="MarkdownV2")
                    return
                
                cmd = args[0].lower()
                if cmd not in BaseCommand._commands:
                    await bot.reply_to(message, "⚠️ Error: Command not found.")
                    return
                
                toChange = args[1].lower()

                if BaseCommand._commands[cmd]:
                    if toChange == 'enable':
                        BaseCommand._commands[cmd]['status'] = True
                    elif toChange == 'disable':
                        BaseCommand._commands[cmd]['status'] = False
                    elif toChange == 'premium':
                        BaseCommand._commands[cmd]['premium'] = True
                    elif toChange == 'regular':
                        BaseCommand._commands[cmd]['premium'] = False
                    else:
                        await bot.reply_to(message, "⚠️ Error: Invalid status.")
                        return
                    await bot.reply_to(message, f"✅ Command {cmd} has been {'enabled' if toChange == 'enable' else 'disabled' if toChange == 'disable' else 'set to premium' if toChange == 'premium' else 'set to regular'}.")
                    return
                else:
                    await bot.reply_to(message, "⚠️ Error: Command not found.")
                    return
            
            # Add lives command handling
            if command == 'lives':
                limit = 10
                bin_filter = None

                if len(args) >= 1:
                    try:
                        if len(args[0]) == 6:
                            bin_filter = args[0]
                            if len(args) > 1:
                                limit = int(args[1])
                        else:
                            limit = int(args[0])
                    except ValueError:
                        await bot.reply_to(message, "⚠️ Error: Invalid format. Use /lives [bin] [limit] or /lives [limit]")
                        return

                cards = get_live_cards(limit, bin_filter)
                if not cards:
                    await bot.reply_to(message, "No live cards found.")
                    return

                # Create card list text file
                content = f"Live Cards Report {'for BIN: ' + bin_filter if bin_filter else ''}\n"
                content += "Generated at: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC") + "\n\n"

                for card in cards:
                    content += (
                        f"CC: {card.card_number}|{card.expiry_month}|{card.expiry_year}|{card.cvv}\n"
                        f"Gateway: {card.gateway}\n"
                        f"Result: {card.result}\n"
                        f"Checked At: {card.checked_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                        f"Checked By: {card.checked_by}\n"
                        f"{'=' * 40}\n"
                    )

                # Save content to file and send
                filename = f"lives_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)

                with open(filename, 'rb') as f:
                    await bot.send_document(message.chat.id, f, caption=f"📋 Live cards report {'for BIN: ' + bin_filter if bin_filter else ''}")

                os.remove(filename)  # Clean up
                return

            # Handle Auth

            if command == 'authg':
                if len(args) < 2:
                    await bot.reply_to(message, "⚠️ Error: Missing group ID / Days.")
                    return

                try:
                    group_id = int(args[0])
                    days = int(args[1])
                except ValueError:
                    await bot.reply_to(message, "⚠️ Error: Invalid format.")
                    return

                if is_group_authorized(group_id):
                    await bot.reply_to(message, f"⚠️ Group {group_id} is already authorized.")
                    return

                if authorize_group(group_id, message.from_user.id, days):
                    await bot.reply_to(message, f"🔒 Group {group_id} has been authorized for {days} days.")
                else:
                    print(authorize_group(group_id, message.from_user.id, days))
                    await bot.reply_to(message, f"⚠️ Error authorizing group {group_id}.")
                return

            if command == 'unauthg':
                if len(args) < 1:
                    await bot.reply_to(message, "⚠️ Error: Missing group ID.")
                    return

                try:
                    group_id = int(args[0])
                except ValueError:
                    await bot.reply_to(message, "⚠️ Error: Invalid format.")
                    return

                if not is_group_authorized(group_id):
                    await bot.reply_to(message, f"⚠️ Group {group_id} is not authorized.")
                    return

                if unauthorize_group(group_id):
                    await bot.reply_to(message, f"🔓 Group {group_id} has been unauthorized.")
                else:
                    await bot.reply_to(message, f"⚠️ Error unauthorizing group {group_id}.")
                return

            # Handle Gen
            if command in ['pgen', 'cgen']:
                if command == 'pgen':
                    if len(args) < 2:
                        await bot.reply_to(message, "⚠️ Error: Missing amount and unit (format: amount h/d).", parse_mode="Markdown")
                        return

                    try:
                        amount = int(args[0])
                        unit = args[1].lower()
                    except (ValueError, IndexError):
                        await bot.reply_to(message, "⚠️ Error: Invalid amount format.")
                        return

                    if unit not in ['h', 'd']:
                        await bot.reply_to(message, "⚠️ Error: Unit must be 'h' for hours or 'd' for days.")
                        return

                    hours = amount if unit == 'h' else amount * 24
                    code = create_premium_code(hours // 24 if unit == 'd' else hours / 24)
                    if code:
                        duration = f"{amount} {'hours' if unit == 'h' else 'days'}"
                        await bot.reply_to(message,
                            f"✨ *Premium Code Generated:*\n`{code}`\n*Duration:* _{duration}_", parse_mode="Markdown")
                    else:
                        await bot.reply_to(message, "⚠️ Failed to generate premium code.")
                else:
                    if len(args) != 1:
                        await bot.reply_to(message, "⚠️ Error: Missing amount.")
                        return
                    amount = int(args[0])
                    code = create_credit_code(amount)
                    if code:
                        await bot.reply_to(message, f"💰 *Credit Code Generated:*\n`{code}`\n*Amount:* _{amount} credits_", parse_mode="Markdown")
                    else:
                        await bot.reply_to(message, "⚠️ Failed to generate credit code.")
                return

            # Handle ban/unban commands
            if len(args) < 1:
                await bot.reply_to(message, "⚠️ Error: Missing user ID.")
                return
            if command == 'broadcast':
                if len(args) < 1:
                    await bot.reply_to(message, "⚠️ Error: Missing message text.")
                    return

                broadcast_message = ' '.join(args)
                users = get_all_users()
                for user in users:
                    try:
                        await bot.send_message(user.telegram_id, broadcast_message)
                    except Exception as e:
                        print(f"Error sending message to {user.telegram_id}: {e}")

                await bot.reply_to(message, "✅ Broadcast message sent to all users.")
                return
            
            try:
                user_id = int(args[0])
            except ValueError:
                await bot.reply_to(message, "⚠️ Error: Invalid user ID format.")
                return

            if user_id == ADMIN_ID:
                await bot.reply_to(message, "⚠️ Error: Cannot perform this action on admin.")
                return

            user = get_user(user_id)
            if not user:
                await bot.reply_to(message, f"⚠️ Error: User {user_id} not found.")
                return

            if command == 'ban':
                if ban_user(user_id):
                    await bot.reply_to(message, f"🚫 User {user_id} has been banned and all privileges removed.")
                else:
                    await bot.reply_to(message, f"⚠️ Failed to ban user {user_id}.")
            elif command == 'unban':
                update_user(user_id, is_banned=False)
                await bot.reply_to(message, f"✅ User {user_id} has been unbanned.")

        except Exception as e:
            await bot.reply_to(message, f"⚠️ Error: {e}")

    @bot.message_handler(commands=['get', 'premiums'])
    async def admin_query_handler(message):
        if str(message.from_user.id) != str(ADMIN_ID):
            return

        command = message.text.split()[0][1:]
        args = message.text.split()[1:]

        if command == 'premiums':
            users = get_premium_users()
            if not users:
                await bot.reply_to(message, "No premium users found")
                return

            content = "Premium Users Report\n"
            content += "Generated at: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC") + "\n\n"

            for user in users:
                remaining = user.premium_until - datetime.utcnow()
                stats = get_user_stats(user.telegram_id)
                content += f"User ID: {user.telegram_id}\n"
                content += f"Premium Until: {user.premium_until.strftime('%Y-%m-%d %H:%M:%S')}\n"
                content += f"Time Remaining: {remaining.days}d {remaining.seconds//3600}h\n"
                if stats:
                    content += f"Total Checks: {stats['total_checks']}\n"
                    content += f"Live Cards: {stats['live_cards']}\n"
                content += "=" * 40 + "\n"

            filename = f"premium_users_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)

            with open(filename, 'rb') as f:
                await bot.send_document(message.chat.id, f, caption="📊 Premium Users Report")
            os.remove(filename)
            return

        if command == 'get':
            if not args:
                await bot.reply_to(message, """
<b>Query Format:</b>
/get [field:value] [field:value] ...

Available fields:
• bin - Card BIN prefix
• result - Search in result text
• status - live/dead
• gate - Gateway name
• user - User ID

Examples:
/get bin:601100
/get result:live status:live
/get gate:stripe user:123456
                """)
                return

            filters = {}
            for arg in args:
                if ':' not in arg:
                    continue
                key, value = arg.split(':', 1)
                filters[key.lower()] = value
                
            cards = query_cards(filters)
            if not cards:
                await bot.reply_to(message, "No cards found matching criteria")
                return

            content = "Query Results\n"
            content += f"Filters: {filters}\n"
            content += "Generated at: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC") + "\n\n"

            for card in cards:
                content += f"CC: {card.card_number}|{card.expiry_month}|{card.expiry_year}|{card.cvv}\n"
                content += f"Gateway: {card.gateway}\n"
                content += f"Result: {card.result}\n"
                content += f"Status: {'LIVE' if card.status else 'DEAD'}\n"
                content += f"Checked At: {card.checked_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                content += f"Checked By: {card.checked_by}\n"
                content += "=" * 40 + "\n"

            filename = f"query_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)

            with open(filename, 'rb') as f:
                await bot.send_document(message.chat.id, f, caption="📋 Query Results")
            os.remove(filename)

    @bot.message_handler(commands=['query'])
    async def admin_query_handler(message):
        """Handle database query command"""
        if str(message.from_user.id) != str(ADMIN_ID):
            return

        args = message.text.split()[1:]
        if not args:
            await bot.reply_to(message, """
<b>Database Query Commands:</b>

    /query users - List all users
    /query premium - List premium users
    /query groups - List authorized groups
    /query stats - Show database statistics
    /query credits - Show users with credits
    /query banned - Show banned users
    """, parse_mode="HTML")
            return

        query_type = args[0].lower()
        content = f"Database Query Results - {query_type}\n"
        content += "Generated at: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC") + "\n\n"

        if query_type == "users":
            users = get_all_users()
            for user in users:
                content += f"ID: {user.telegram_id}\n"
                content += f"Premium: {'Yes' if user.is_premium else 'No'}\n"
                content += f"Credits: {user.credits}\n"
                content += f"Banned: {'Yes' if user.is_banned else 'No'}\n"
                content += "=" * 40 + "\n"

        elif query_type == "premium":
            users = get_premium_users()
            for user in users:
                remaining = user.premium_until - datetime.utcnow()
                content += f"ID: {user.telegram_id}\n"
                content += f"Until: {user.premium_until.strftime('%Y-%m-%d %H:%M:%S')}\n"
                content += f"Remaining: {remaining.days}d {remaining.seconds//3600}h\n"
                content += "=" * 40 + "\n"

        elif query_type == "groups":
            groups = get_all_groups()
            for group in groups:
                content += f"ID: {group.telegram_group_id}\n"
                content += f"Added By: {group.added_by}\n"
                content += f"Added Date: {group.added_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                content += "=" * 40 + "\n"

        elif query_type == "stats":
            stats = get_db_stats()
            content += "Database Statistics\n\n"
            content += f"Total Users: {stats.get('total_users', 0)}\n"
            content += f"Premium Users: {stats.get('premium_users', 0)}\n"
            content += f"Authorized Groups: {stats.get('authorized_groups', 0)}\n"
            content += f"Total Card Checks: {stats.get('total_checks', 0)}\n"
            content += f"Live Cards: {stats.get('live_cards', 0)}\n"
            content += f"Dead Cards: {stats.get('dead_cards', 0)}\n"
            content += f"Total Credits: {stats.get('total_credits', 0)}\n"

        elif query_type == "credits":
            users = get_users_with_credits()
            for user in users:
                content += f"ID: {user.telegram_id}\n"
                content += f"Credits: {user.credits}\n"
                content += "=" * 40 + "\n"

        elif query_type == "banned":
            users = get_banned_users()
            for user in users:
                content += f"ID: {user.telegram_id}\n"
                content += f"Credits: {user.credits}\n"
                content += "=" * 40 + "\n"

        else:
            await bot.reply_to(message, "⚠️ Invalid query type")
            return

        # Save results to file and send
        filename = f"query_{query_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

        with open(filename, 'rb') as f:
            await bot.send_document(message.chat.id, f, caption=f"📊 Database Query Results: {query_type}")
        os.remove(filename)
