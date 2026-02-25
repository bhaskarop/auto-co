from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from database import get_user, add_user
from .base_command import BaseCommand, CommandType

def register_cmds_command(bot: AsyncTeleBot):
    COMMANDS_PER_PAGE = 5
    
    def create_commands_page(commands_list, page=0, category=""):
        if not commands_list:
            return "<b>No commands available in this category.</b>", InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Back", callback_data="back_cmds")
            )
        
        start_idx = page * COMMANDS_PER_PAGE
        end_idx = start_idx + COMMANDS_PER_PAGE
        total_pages = (len(commands_list) + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE

        commands_text = ""
        for cmd in commands_list[start_idx:end_idx]:
            status_text = "\n<b> - Status: ON ✅</b>" if cmd['status'] else "\n<b> - Status: OFF ❌</b>"
            if 'amount' in cmd:
                if isinstance(cmd['amount'], str):
                    if 'custom' in cmd['amount'].lower():
                        amount_text = f"{cmd['amount']}"
                    else:
                        amount_text = f"{cmd['amount']} {cmd['amountType']}"
                else:
                    amount_text = f"{cmd['amount']}{cmd['amountType']}"
            else:
                amount_text = ""
            commands_text += f"<b>{cmd['name'].upper()} {amount_text}</b>: <code>/{cmd['cmd']}</code>{status_text}\n━━━━━━━━━━━━\n"
        
        markup = InlineKeyboardMarkup(row_width=3)
        nav_buttons = []
        
        if total_pages > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{category}|{page-1}"))
            nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{category}|{page+1}"))
            
        markup.add(*nav_buttons)
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_cmds"))
        
        return commands_text, markup

    @bot.message_handler(func=lambda message: message.text and message.text[0] in ['/', '?', '.'] and message.text[1:].split('@')[0] == 'cmds')
    async def handle_cmds(message: Message):
        user = get_user(message.from_user.id)
        if not user:
            add_user(message.from_user.id)
            user = get_user(message.from_user.id)
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("💳 Charge", callback_data="charge_cmds"),
            InlineKeyboardButton("Mass Charge", callback_data="mass_cmds"),
            InlineKeyboardButton("⭐ CCN Charge", callback_data="ccn_cmds"),
            InlineKeyboardButton("🔒 Auth", callback_data="auth_cmds"),
            InlineKeyboardButton("3D Lookup", callback_data="lookup_cmds"),
            # InlineKeyboardButton("⭐ Premium", callback_data="premium_cmds"),
            # InlineKeyboardButton("🆓 Free", callback_data="free_cmds"),
            InlineKeyboardButton("📋 Others", callback_data="general_cmds")
        )
        
        if user.is_admin:
            markup.add(InlineKeyboardButton("🔧 Admin", callback_data="admin_cmds"))
        
        total_gates = len(BaseCommand.get_all_commands())
        working_gates = len([cmd for cmd in BaseCommand.get_all_commands() if cmd['status'] == True])
        auth_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.AUTH, [])])
        working_auth_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.AUTH, []) if cmd['status']])
        lookup_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.LOOKUP, [])])
        working_lookup_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.LOOKUP, []) if cmd['status']])
        charge_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.CHARGE, [])])
        working_charge_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.CHARGE, []) if cmd['status']])
        
        ccn_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.CCN, [])])
        working_ccn_gates = len([cmd for cmd in BaseCommand.get_commands_by_type().get(CommandType.CCN, []) if cmd['status']])
        
        f"""Charge Gates: {charge_gates} - Working: {working_charge_gates}
CCN Charge Gates: {ccn_gates} - Working: {working_ccn_gates}
3D Lookup Gates: {lookup_gates} - Working: {working_lookup_gates}
Auth Gates: {auth_gates} - Working: {working_auth_gates}</b>
"""
        
        await bot.reply_to(message, f"""<i>Hey, {message.from_user.first_name}!

[ϟ] Explore commands by pressing below buttons!

📊Gates Status

Total Gates: {total_gates}
✅ On: {working_gates}
❌ Off: {total_gates - working_gates}
</i>
""", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: True)
    async def handle_callback_query(call):
        if call.data == "ignore":
            return
        
        page = 0
        category = call.data
        
        # Simpler navigation handling
        if "|" in call.data:
            try:
                category, page_str = call.data.split("|")
                page = int(page_str)
            except (ValueError, IndexError):
                await bot.answer_callback_query(call.id, "Invalid navigation")
                return
        
        commands = ""
        grouped_commands = BaseCommand.get_commands_by_type()
        
        # Handle different categories
        if category in ["auth_cmds", "charge_cmds", "ccn_cmds", "lookup_cmds", "premium_cmds", "free_cmds", "mass_cmds"]:
            category_titles = {
                "auth_cmds": ("AUTH", CommandType.AUTH),
                "charge_cmds": ("CHARGE", CommandType.CHARGE),
                "ccn_cmds": ("CCN", CommandType.CCN),
                "lookup_cmds": ("3D LOOKUP", CommandType.LOOKUP),
                "mass_cmds" : ("Mass", CommandType.MASS),
                # "premium_cmds": ("PREMIUM", None),
                # "free_cmds": ("FREE", None)
            }
            
            title, cmd_type = category_titles[category]
            commands = f"<b>[ϟ] {title} GATES</b>\n━━━━━━━━━━━━\n"
            
            if category in ["premium_cmds", "free_cmds"]:
                # Get all commands and filter by premium status
                all_commands = []
                for cmd_type in [CommandType.AUTH, CommandType.CHARGE, CommandType.CCN, CommandType.LOOKUP]:
                    if cmd_type in grouped_commands:
                        all_commands.extend(grouped_commands[cmd_type])
                
                # Filter commands based on premium status
                is_premium = category == "premium_cmds"
                sorted_cmds = sorted(
                    [cmd for cmd in all_commands if cmd.get('premium', True) == is_premium],
                    key=lambda x: x['name']
                )
                
                if page >= (len(sorted_cmds) + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE:
                    await bot.answer_callback_query(call.id, "Already on last page")
                    return
                
                commands_text, markup = create_commands_page(sorted_cmds, page, category)
                commands += commands_text
            else:
                if cmd_type in grouped_commands:
                    sorted_cmds = sorted(grouped_commands[cmd_type], key=lambda x: x['name'])
                    if page >= (len(sorted_cmds) + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE:
                        await bot.answer_callback_query(call.id, "Already on last page")
                        return
                        
                    commands_text, markup = create_commands_page(sorted_cmds, page, category)
                    commands += commands_text
                else:
                    commands_text, markup = create_commands_page([], page, category)
                    commands += commands_text

        elif category == "general_cmds":
            commands = """
<b>[ϟ] GENERAL COMMANDS</b>
━━━━━━━━━━━━
<b>Credits</b>: <code>/credits</code>
<b>Redeem</b>: <code>/redeem</code>
<b>Daily Credits</b>: <code>/daily</code>
<b>Bin</b>: <code>/bin</code>
<b>Info</b>: <code>/info</code>
<b>Commands</b>: <code>/cmds</code>

<b>Shopify Mass Configuration</b>: <code>/shopify</code>
━━━━━━━━━━━━
"""
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_cmds"))

        elif category == "admin_cmds":
            commands = """
<b>[ϟ] ADMIN COMMANDS</b>
━━━━━━━━━━━━
<b>Credits Gen</b>: <code>/cgen</code>
<b>Premium Gen</b>: <code>/pgen</code>

<b>Authorize Group</b>: <code>/authg</code>
<b>UnAuthorize Group</b>: <code>/unauthg</code>

<b>Get Database</b>: <code>/senddb</code>
<b>Gates Configurtation</b>: <code>/gate</code>

<b>Ban</b>: <code>/ban</code>
<b>UnBan</b>: <code>/unban</code>

<i>Query Purpose: query, get</i>
━━━━━━━━━━━━
"""
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_cmds"))

        elif category == "back_cmds":
            commands = "<b>📋 Choose a category:</b>"
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("💳 Charge", callback_data="charge_cmds"),
                InlineKeyboardButton("Mass Charge", callback_data="mass_cmds"),
                InlineKeyboardButton("CCN Charge", callback_data="ccn_cmds"),
                InlineKeyboardButton("🔒 Auth", callback_data="auth_cmds"),
                InlineKeyboardButton("3D Lookup", callback_data="lookup_cmds"),
                # InlineKeyboardButton("⭐ Premium", callback_data="premium_cmds"),
                # InlineKeyboardButton("🆓 Free", callback_data="free_cmds"),
                InlineKeyboardButton("📋 Others", callback_data="general_cmds")
            )

            if get_user(call.from_user.id).is_admin:
                markup.add(InlineKeyboardButton("🔧 Admin", callback_data="admin_cmds"))
            await bot.edit_message_text(commands, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return

        await bot.edit_message_text(commands, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.message_handler(commands=['gcmds'])
    async def handle_gcmds(message: Message):
        user = get_user(message.from_user.id)
        if not user.is_admin:
            return
        if not user:
            add_user(message.from_user.id)
            user = get_user(message.from_user.id)
        
        grouped_commands = BaseCommand.get_commands_by_type()
        
        def get_commands_text(commands_list):
            commands_text = ""
            for cmd in commands_list:
                cmd, cmd_type = cmd
                amount_text = f"{cmd['amount']}{cmd['amountType']}"
                if cmd_type == CommandType.CHARGE:
                    commands_text += f"<b>{cmd['name'].upper()} {amount_text}</b>: <code>/{cmd['cmd']}</code>\n"
                else:
                    commands_text += f"<b>{cmd['name'].upper()} - {cmd_type} - {amount_text}</b>: <code>/{cmd['cmd']}</code>\n"
            return commands_text
        
        free_commands = []
        premium_commands = []

        for cmd_type in [CommandType.AUTH, CommandType.CHARGE, CommandType.CCN, CommandType.MASS, CommandType.LOOKUP]:
            if cmd_type in grouped_commands:
                for cmd in grouped_commands[cmd_type]:
                    if cmd.get('status'):
                        if cmd.get('premium', True):
                            premium_commands.append((cmd, cmd_type))
                        else:
                            free_commands.append((cmd, cmd_type))
        
        free_commands_text = get_commands_text(free_commands)
        premium_commands_text = get_commands_text(premium_commands)

        await bot.reply_to(message, f"""<i>Hey, {message.from_user.first_name}!
We have a total of {len(free_commands) + len(premium_commands)} commands available.
Free Commands - {len(free_commands)}
Premium Commands - {len(premium_commands)}

<b>[ϟ] FREE COMMANDS</b>
━━━━━━━━━━━━
{free_commands_text}

<b>[ϟ] PREMIUM COMMANDS</b>
━━━━━━━━━━━━
{premium_commands_text}
</i>""")