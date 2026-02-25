import os
import time
from utils import Utils
from database import get_user, add_user, update_user_credits, update_user_last_command_time, is_group_authorized
from telebot.types import Message
from .bin_command import fetch_bin_info, format_bin_info
from utils_fo.logger import Logger

FREE_USER_LIMIT = int(os.getenv('FREE_USER_LIMIT', '60'))
PREMIUM_USER_LIMIT = int(os.getenv('PREMIUM_USER_LIMIT', '10'))

class CommandType:
    AUTH = "Auth"
    CHARGE = "Charge"
    CCN = "CCN"
    LOOKUP = "Lookup"

def is_valid_user(message: Message) -> bool:
    if message.chat.type not in ['private', 'group', 'supergroup'] or message.from_user.is_bot:
        return False
    if message.chat.type in ['group', 'supergroup']:
        return is_group_authorized(message.chat.id)
    return True

class BaseCommand:
    _commands = {}
    def __init__(self, bot, name, cmd, handler, cmd_type, amount=0.00, amountType = '$',deduct_credits=0, premium=True, status=True):
        self.bot = bot
        self.name = name
        self.cmd = cmd
        self.handler = handler
        self.cmd_type = cmd_type
        self.amount = int(amount) if amount.is_integer() else amount
        self.deduct_credits = deduct_credits
        self.amountType = amountType
        self.premium = premium
        self.status = status
        self.logger = Logger.get_logger()
        self.gate = None
        if self.cmd_type == CommandType.CHARGE:
            self.gate = f'{self.name.upper()}_CH'
        elif self.cmd_type == CommandType.CCN:
            self.gate = f'{self.name.upper()}_CCN'
        elif self.cmd_type == CommandType.AUTH:
            self.gate = self.name.upper()

    def register_command(self):
        BaseCommand._commands[self.cmd] = {
            'name': self.name,
            'type': self.cmd_type,
            'amount': self.amount,
            'amountType': self.amountType,
            'status': self.status,
            'premium': self.premium
        }

        @self.bot.message_handler(commands=[self.cmd])
        async def command_handler(message):
            try:
                current_time = time.time()
                if not is_valid_user(message):
                    if message.chat.type in ['group', 'supergroup']:
                        if message.chat.id and not is_group_authorized(message.chat.id):
                            await self.bot.reply_to(message, "This group is not authorized to use the bot.")
                    else:
                        await self.bot.reply_to(message, "Invalid user or chat type.")
                    return
                
                user_id = message.from_user.id
                user = get_user(user_id)
                if not user:
                    user = add_user(user_id)
                    if not user:
                        await self.bot.reply_to(message, "Failed to register user.")
                        return
                    
                is_valid, error_msg, card_details = Utils.extract_and_validate_card(message)
                if not is_valid:
                    if 'Invalid format' in error_msg:
                        error_msg = f"<b>{self.gate.upper()} {' ' + str(self.amount) + self.amountType if self.amount > 0 else ''}\nFormat: </b><code>/{self.cmd} cc|mm|yy|cvv</code>"
                        await self.bot.reply_to(message, error_msg)
                    return
                
                if user.is_admin:
                    time_limit = 0
                elif user.is_premium:
                    time_limit = PREMIUM_USER_LIMIT
                else:
                    time_limit = FREE_USER_LIMIT
                
                if user.last_command_time and current_time - user.last_command_time < time_limit:
                    await self.bot.reply_to(message, f"<b>[ϟ] Antispam Wait {time_limit - (current_time - user.last_command_time):.0f} seconds</b>")
                    return
                
                # self.logger.info(f"Command received: /{self.cmd} from user {message.from_user.id}")
                
                user_link = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
                user_type = "Owner" if user.is_admin else "Premium User" if user.is_premium else "Free User"

                if self.status == False:
                    await self.bot.reply_to(message, f"<b>❌ {self.name.upper()} {self.cmd_type.upper()} - (/{self.cmd}) is currently disabled.\n-Try other /cmds</b>")
                    return
                
                if self.premium and not user.is_premium:
                    await self.bot.reply_to(message, "<b>This command is only available to premium users.\nHit /plans for more info!.</b>")
                    return
                
                cc, mes, ano, cvv = card_details
                
                if Utils.is_banned_bin(cc):
                    await self.bot.reply_to(message, f"<b>❌ {cc[:6]} - Bin Banned</b>")
                    # self.logger.warning(f"Banned BIN attempt - Full card: {cc}|{mes}|{ano}|{cvv} - User: {message.from_user.id}")
                    return
                
                response_msg = await self.bot.reply_to(message, "<b>Checking card...</b>")
                try:
                    res0 = await self.handler(cc, mes, ano, cvv)
                    if isinstance(res0, tuple):
                        if len(res0) == 2:
                            success, result = res0
                            price = self.amount
                        else:
                            success, result, price = res0
                    else:
                        success = bool(res0)
                        result = str(res0)
                        price = self.amount
                    
                    if self.cmd_type == CommandType.LOOKUP:
                        timeTaken = time.time() - current_time
                        res = f"<b>{self.name.upper()} VBV (/{self.cmd}) - {'NON VBV ✅' if success else '3D SECURE ❌'}</b>"
                        res += '\n━━━━━━━━━━━━━━━━━━'
                        res += f'\n<b>CC:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>'
                        res += f'\n<b>Result: {result}</b>'
                        res += f"\nTime: <b>{timeTaken:.2f} seconds</b>"
                        res += f"\nChecked by {user_link} <b>[{user_type}]</b>"
                    else:
                        bin_response = fetch_bin_info(cc[:6])
                        if 'prepaid' in bin_response['Category'].lower():
                            await self.bot.edit_message_text(
                                '<b>❌ Prepaid bins are banned!</b>',
                                chat_id=message.chat.id,
                                message_id=response_msg.message_id
                            )
                            return
                        
                        bin_info = format_bin_info(bin_response, cc[:6]) if bin_response else "BIN info not available"
                        timeTaken = time.time() - current_time
                        if success and (self.cmd_type == CommandType.CHARGE or self.cmd_type == CommandType.CCN) and ('charge' in result.lower() or 'success' in result.lower()):
                            result = f'Charged {price}{self.amountType}'

                        res = f"<b>{self.gate} (/{self.cmd}) - {'LIVE ✅' if success else 'DEAD ❌'}</b>"
                        res += '\n━━━━━━━━━━━━━━━━━━'
                        res += f'\n<b>CC:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>'
                        res += f'\nResult: <b>{result.strip()}</b>' if result else "<b>None</b>"
                        res += f"\n{bin_info}" if bin_info else ""
                        res += f"\nTime: <b>{timeTaken:.2f} seconds</b>"
                        res += f"\nChecked by {user_link} <b>[{user_type}]</b>"
                    await self.bot.edit_message_text(
                        res,
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id
                    )
                    self.logger.info(f"CARD: {cc}|{mes}|{ano}|{cvv} | GATE {self.name} - CMD: /{self.cmd} | USER: {message.from_user.id} [{user_type}] | STATUS: {'✅' if success else '❌'} | RESULT: {result} | TIME: {time.time() - current_time:.2f}s")
                    
                    if self.premium == False and user.is_premium == False:
                        update_user_credits(user_id, -1)
                        self.logger.info(f"Free user deducted {self.deduct_credits} credits for {self.name} command")

                except Exception as e:
                    self.logger.error(f"Error processing card: {str(e)}", exc_info=True)
                    await self.bot.edit_message_text(
                        f"❌ Error processing card: {str(e)}",
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id
                    )
            except Exception as e:
                await self.bot.reply_to(message, f"Error: {str(e)}")
    
    @staticmethod
    def get_commands_by_type():
        """Get all registered commands grouped by type"""
        grouped = {}
        for cmd, info in BaseCommand._commands.items():
            cmd_type = info['type']
            if cmd_type not in grouped:
                grouped[cmd_type] = []
            grouped[cmd_type].append({
                'cmd': cmd,
                'name': info['name'],
                'amount': info['amount'],
                'amountType': info['amountType'],
                'status': info['status'],
                'premium': info.get('premium', True)
            })
        return grouped

    @staticmethod
    def get_all_commands():
        """Get all registered commands as a list"""
        return [
            {
                'cmd': cmd,
                'name': info['name'],
                'amount': info['amount'],
                'amountType': info['amountType'],
                'status': info['status'],
                'type': info['type']
            } 
            for cmd, info in BaseCommand._commands.items()
        ]