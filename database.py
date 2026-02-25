from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, func, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sqlite3
import time
from datetime import datetime, timedelta
import secrets
import string

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///cocobot.db')
ADMIN_ID = 'Your User ID'

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    premium_until = Column(DateTime, nullable=True)
    credits = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    last_command_time = Column(Integer, default=lambda: int(time.time() - 60))

    @property
    def is_admin(self):
        return str(self.telegram_id) == str(ADMIN_ID)

    @property
    def is_premium(self):
        return self.premium_until is not None and self.premium_until > datetime.utcnow()

class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True, index=True)
    telegram_group_id = Column(Integer, unique=True, index=True)
    is_authorized = Column(Boolean, default=False)
    added_by = Column(Integer)
    added_date = Column(DateTime, default=datetime.utcnow)

class DailyCredits(Base):
    __tablename__ = 'daily_credits'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    last_redeem = Column(DateTime, default=datetime.utcnow)
    credits = Column(Integer, default=0)

class PremiumCode(Base):
    __tablename__ = 'premium_codes'
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    days = Column(Integer)
    used_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)

class CreditCode(Base):
    __tablename__ = 'credit_codes'
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    credits = Column(Integer)
    used_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)

class Cards(Base):
    __tablename__ = 'cards'
    id = Column(Integer, primary_key=True, index=True)
    card_number = Column(String)
    expiry_month = Column(String)
    expiry_year = Column(String)
    cvv = Column(String)
    bin = Column(String, index=True)
    checked_by = Column(Integer)
    checked_at = Column(DateTime, default=datetime.utcnow)
    gateway = Column(String)
    status = Column(Boolean)
    result = Column(String)

class ShopifySite(Base):
    __tablename__ = 'shopify_sites'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    url = Column(String)
    variant_id = Column(String, default='')
    added_at = Column(DateTime, default=datetime.utcnow)
    deleted = Column(Boolean, default=False)

class Proxy(Base):
    __tablename__ = 'proxies'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    proxy = Column(String)
    added_at = Column(DateTime, default=datetime.utcnow)
    deleted = Column(Boolean, default=False)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Error initializing database: {e}")

def add_user(telegram_id):
    try:
        session = SessionLocal()
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
        return user
    except Exception as e:
        print(f"Error adding user: {e}")
    finally:
        session.close()

def get_user(telegram_id):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        return user
    except Exception as e:
        print(f"Error getting user: {e}")
    finally:
        session.close()

def update_user(telegram_id, premium_until=None, credits=None, is_banned=None):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if premium_until is not None:
            user.premium_until = premium_until
        if credits is not None:
            user.credits = credits
        if is_banned is not None:
            user.is_banned = is_banned
        session.commit()
    except Exception as e:
        print(f"Error updating user: {e}")
    finally:
        session.close()

def update_user_last_command_time(user_id, last_command_time):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == user_id).first()
        print(user)
        if user:
            user.last_command_time = last_command_time
            session.commit()
            return True
    except Exception as e:
        print(f"Error updating last command time: {e}")
    finally:
        session.close()

def update_user_credits(user_id, credits_change):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.credits += credits_change
            user.last_command_time = time.time()
            session.commit()
    except Exception as e:
        print(f"Error updating user credits: {e}")
    finally:
        session.close()

def update_daily_credits(user_id, credits_change):
    try:
        session = SessionLocal()
        daily = session.query(DailyCredits).filter(DailyCredits.user_id == user_id).first()
        if not daily:
            daily = DailyCredits(user_id=user_id, credits=credits_change)
            session.add(daily)
        else:
            daily.credits += credits_change
        session.commit()
    except Exception as e:
        print(f"Error updating daily credits: {e}")
    finally:
        session.close()


def add_group(telegram_group_id, added_by):
    try:
        session = SessionLocal()
        group = Group(telegram_group_id=telegram_group_id, added_by=added_by)
        session.add(group)
        session.commit()
        return group
    except Exception as e:
        print(f"Error adding group: {e}")
    finally:
        session.close()

def get_group(telegram_group_id):
    try:
        session = SessionLocal()
        group = session.query(Group).filter(Group.telegram_group_id == telegram_group_id).first()
        return group
    except Exception as e:
        print(f"Error getting group: {e}")
    finally:
        session.close()

def authorize_group(telegram_group_id, authorized_by, days=7):
    try:
        session = SessionLocal()
        group = session.query(Group).filter(Group.telegram_group_id == telegram_group_id).first()
        if not group:
            group = add_group(telegram_group_id, authorized_by)
        try:
            group.is_authorized = True
            group.added_by = authorized_by
            group.added_date = datetime.utcnow()
            group.expiry_date = datetime.utcnow() + timedelta(days=days)
            session.commit()
            return True
        except Exception as e:
            print(f"Error authorizing group: {e}")
            return False
    except Exception as e:
        print(f"Error authorizing group: {e}")
        return False
    finally:
        session.close()

def unauthorize_group(telegram_group_id):
    try:
        session = SessionLocal()
        group = session.query(Group).filter(Group.telegram_group_id == telegram_group_id).first()
        if group:
            group.is_authorized = False
            group.expiry_date = None
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error unauthorizing group: {e}")
        return False
    finally:
        session.close()

def is_group_authorized(telegram_group_id):
    try:
        session = SessionLocal()
        group = session.query(Group).filter(
            Group.telegram_group_id == telegram_group_id,
            Group.is_authorized == True
        ).first()

        if group and hasattr(group, 'expiry_date'):
            return bool(group and group.expiry_date > datetime.utcnow())
        return bool(group)
    except Exception as e:
        print(f"Error checking group authorization: {e}")
        return False
    finally:
        session.close()

def can_redeem_daily(user_id):
    try:
        session = SessionLocal()
        daily = session.query(DailyCredits).filter(DailyCredits.user_id == user_id).first()
        if not daily:
            return True

        next_redeem = daily.last_redeem + timedelta(days=1)
        return datetime.utcnow() >= next_redeem
    except Exception as e:
        print(f"Error checking daily credits: {e}")
        return False
    finally:
        session.close()

def redeem_daily_credits(user_id, amount=10):
    try:
        session = SessionLocal()
        daily = session.query(DailyCredits).filter(DailyCredits.user_id == user_id).first()

        if not daily:
            daily = DailyCredits(user_id=user_id, credits=amount)
            session.add(daily)
        else:
            daily.last_redeem = datetime.utcnow()
            daily.credits = amount

        session.commit()
        return True, amount
    except Exception as e:
        print(f"Error redeeming daily credits: {e}")
        return False, 0
    finally:
        session.close()

def get_user_credits(user_id):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == user_id).first()
        return user.credits if user else 0
    except Exception as e:
        print(f"Error getting user credits: {e}")
        return 0
    finally:
        session.close()

def get_daily_user_credits(user_id):
    try:
        session = SessionLocal()
        daily = session.query(DailyCredits).filter(DailyCredits.user_id == user_id).first()
        return daily.credits if daily else 0
    except Exception as e:
        print(f"Error getting daily user credits: {e}")
        return 0
    finally:
        session.close()

def deduct_credits(user_id, amount):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.credits < amount:
            return False

        user.credits -= amount
        session.commit()
        return True
    except Exception as e:
        print(f"Error deducting credits: {e}")
        return False
    finally:
        session.close()

def get_daily_credits_info(user_id):
    try:
        session = SessionLocal()
        daily = session.query(DailyCredits).filter(DailyCredits.user_id == user_id).first()
        if daily:
            next_redeem = daily.last_redeem + timedelta(days=1)
            time_left = next_redeem - datetime.utcnow()
            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            can_redeem = time_left.total_seconds() <= 0
            return {
                'credits': daily.credits,
                'can_redeem': can_redeem,
                'time_left': f"{hours}h {minutes}m" if not can_redeem else "Available now!"
            }
        return {'credits': 0, 'can_redeem': True, 'time_left': "Available now!"}
    except Exception as e:
        print(f"Error getting daily credits info: {e}")
        return None
    finally:
        session.close()

def generate_unique_code():
    session = SessionLocal()
    while True:
        code = 'COCO' + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
        premium_exists = session.query(PremiumCode).filter(PremiumCode.code == code).first()
        credit_exists = session.query(CreditCode).filter(CreditCode.code == code).first()
        if not premium_exists and not credit_exists:
            session.close()
        return code

def create_premium_code(days):
    try:
        session = SessionLocal()
        code = generate_unique_code()
        premium_code = PremiumCode(code=code, days=days)
        session.add(premium_code)
        session.commit()
        return code
    except Exception as e:
        print(f"Error creating premium code: {e}")
        return None
    finally:
        session.close()

def create_credit_code(credits):
    try:
        session = SessionLocal()
        code = generate_unique_code()
        credit_code = CreditCode(code=code, credits=credits)
        session.add(credit_code)
        session.commit()
        return code
    except Exception as e:
        print(f"Error creating credit code: {e}")
        return None
    finally:
        session.close()

def ban_user(user_id):
    try:
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.is_banned = True
            user.credits = 0
            user.premium_until = None
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error banning user: {e}")
        return False
    finally:
        session.close()

def save_card(card_number, expiry_month, expiry_year, cvv, checked_by, gateway, status, result):
    try:
        session = SessionLocal()
        card = Cards(
            card_number=card_number,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            cvv=cvv,
            bin=card_number[:6],
            checked_by=checked_by,
            gateway=gateway,
            status=status,
            result=result
        )
        session.add(card)
        session.commit()
        return True
    except Exception as e:
        print(f"Error saving card: {e}")
        return False
    finally:
        session.close()

def validate_and_save_card(card_number, expiry_month, expiry_year, cvv, checked_by, gateway, status, result):
    """Validate and save card with improved checks"""
    try:
        session = SessionLocal()

        if not (13 <= len(card_number) <= 19 and card_number.isdigit()):
            return False, "Invalid card number length"

        if not (1 <= int(expiry_month) <= 12):
            return False, "Invalid expiry month"

        year = int(expiry_year)
        if len(expiry_year) == 2:
            year = 2000 + year
        if not (2025 <= year <= 2050):
            return False, "Invalid expiry year"

        if len(cvv) not in [3, 4]:
            return False, "Invalid CVV length"

        card = Cards(
            card_number=card_number,
            expiry_month=expiry_month,
            expiry_year=str(year),
            cvv=cvv,
            bin=card_number[:6],
            checked_by=checked_by,
            gateway=gateway,
            status=status,
            result=result,
            checked_at=datetime.utcnow()
        )
        session.add(card)
        session.commit()
        return True, "Card saved successfully"

    except Exception as e:
        print(f"Error saving card: {e}")
        return False, str(e)
    finally:
        session.close()

def get_live_cards(limit=1000, bin_filter=None):
    try:
        session = SessionLocal()
        query = session.query(Cards).filter(Cards.status == True)
        if bin_filter:
            query = query.filter(Cards.bin == bin_filter)
        cards = query.order_by(Cards.checked_at.desc()).limit(limit).all()
        return cards
    except Exception as e:
        print(f"Error getting live cards: {e}")
        return []
    finally:
        session.close()

def query_cards(filters=None, limit=2000):
    """
    Query cards with flexible filters
    filters: dict of field:value pairs
    """
    try:
        session = SessionLocal()
        query = session.query(Cards)

        if filters:
            for key, value in filters.items():
                if key == 'bin':
                    query = query.filter(Cards.bin.startswith(value.lower()))
                elif key == 'result':
                    query = query.filter(Cards.result.ilike(f'%{value.lower()}%'))
                elif key == 'status':
                    status_val = value.lower() == 'live'
                    query = query.filter(Cards.status == status_val)
                elif key == 'gate':
                    query = query.filter(Cards.gateway.ilike(f'%{value.lower()}%'))
                elif key == 'user':
                    query = query.filter(Cards.checked_by == int(value))

        return query.order_by(Cards.checked_at.desc()).limit(limit).all()
    except Exception as e:
        print(f"Error querying cards: {e}")
        return []
    finally:
        session.close()

def get_user_stats(user_id, card=None):
    """Get statistics for a user"""
    try:
        session = SessionLocal()
        total_checks = session.query(Cards).filter(Cards.checked_by == user_id).count()
        live_cards = session.query(Cards).filter(
            Cards.checked_by == user_id,
            Cards.status == True
        ).count()
        recent_cards = session.query(Cards).filter(
            Cards.checked_by == user_id
        ).order_by(Cards.checked_at.desc()).limit(5).all()
        if not card:
            return {
                "total_checks": total_checks,
                "live_cards": live_cards,
                "recent_cards": recent_cards,
            }
        if card:
            current = session.query(Cards).filter(
                Cards.card_number == card,
                Cards.checked_by == user_id
            ).count()

            other = session.query(Cards).filter(
                Cards.card_number == card
            ).count()

        return {
            "total_checks": total_checks,
            "live_cards": live_cards,
            "recent_cards": recent_cards,
            "current": current,
            "other": other - current
        }
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return None
    finally:
        session.close()

def get_premium_users():
    """Get all premium users"""
    try:
        session = SessionLocal()
        users = session.query(User).filter(
            User.premium_until != None,
            User.premium_until > datetime.utcnow()
        ).all()
        return users
    except Exception as e:
        print(f"Error getting premium users: {e}")
        return []
    finally:
        session.close()

def get_all_users():
    """Get all users from database"""
    try:
        session = SessionLocal()
        return session.query(User).all()
    except Exception as e:
        print(f"Error getting users: {e}")
        return []
    finally:
        session.close()

def get_all_groups():
    """Get all authorized groups"""
    try:
        session = SessionLocal()
        return session.query(Group).filter(Group.is_authorized == True).all()
    except Exception as e:
        print(f"Error getting groups: {e}")
        return []
    finally:
        session.close()

def get_users_with_credits():
    """Get users with non-zero credits"""
    try:
        session = SessionLocal()
        return session.query(User).filter(User.credits > 0).all()
    except Exception as e:
        print(f"Error getting users with credits: {e}")
        return []
    finally:
        session.close()

def get_banned_users():
    """Get all banned users"""
    try:
        session = SessionLocal()
        return session.query(User).filter(User.is_banned == True).all()
    except Exception as e:
        print(f"Error getting banned users: {e}")
        return []
    finally:
        session.close()

def get_db_stats():
    """Get database statistics"""
    try:
        session = SessionLocal()
        return {
            'total_users': session.query(User).count(),
            'premium_users': session.query(User).filter(
                User.premium_until != None,
                User.premium_until > datetime.utcnow()
            ).count(),
            'authorized_groups': session.query(Group).filter(
                Group.is_authorized == True
            ).count(),
            'total_checks': session.query(Cards).count(),
            'live_cards': session.query(Cards).filter(Cards.status == True).count(),
            'dead_cards': session.query(Cards).filter(Cards.status == False).count(),
            'total_credits': session.query(User).with_entities(
                func.sum(User.credits)).scalar() or 0
        }
    except Exception as e:
        print(f"Error getting database stats: {e}")
        return {}
    finally:
        session.close()

def add_shopify_site(user_id, url, variant_id):
    """Add Shopify site for user"""
    try:
        session = SessionLocal()
        # Check if site already exists and is not deleted
        existing = session.query(ShopifySite).filter(
            ShopifySite.user_id == user_id,
            ShopifySite.url == url,
            ShopifySite.deleted == False
        ).first()
        if existing:
            return False
        site = ShopifySite(user_id=user_id, url=url, variant_id=variant_id)
        session.add(site)
        session.commit()
        return True
    except Exception as e:
        print(f"Error adding Shopify site: {e}")
        return False
    finally:
        session.close()

def remove_shopify_site(user_id, urls):
    """Mark Shopify sites as deleted. urls can be a single URL string or list of URLs"""
    try:
        session = SessionLocal()
        if isinstance(urls, str):
            urls = [urls]

        # Query for all matching sites
        sites = session.query(ShopifySite).filter(
            ShopifySite.user_id == user_id,
            ShopifySite.url.in_(urls),
            ShopifySite.deleted == False
        ).all()

        if sites:
            for site in sites:
                site.deleted = True
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error removing Shopify sites: {e}")
        return False
    finally:
        session.close()


def get_user_shopify_sites(user_id):
    """Get user's active Shopify sites"""
    try:
        session = SessionLocal()
        sites = session.query(ShopifySite).filter(
            ShopifySite.user_id == user_id,
            ShopifySite.deleted == False
        ).all()
        return sites
    except Exception as e:
        print(f"Error getting Shopify sites: {e}")
        return []
    finally:
        session.close()


def add_proxy(user_id, proxy):
    """Add proxy for user"""
    try:
        session = SessionLocal()
        proxy_obj = Proxy(user_id=user_id, proxy=proxy)
        session.add(proxy_obj)
        session.commit()
        return True
    except Exception as e:
        print(f"Error adding proxy: {e}")
        return False
    finally:
        session.close()

def remove_proxy(user_id, proxy):
    """Mark proxy as deleted"""
    try:
        session = SessionLocal()
        proxy_obj = session.query(Proxy).filter(
            Proxy.user_id == user_id,
            Proxy.proxy == proxy,
            Proxy.deleted == False
        ).first()
        if proxy_obj:
            proxy_obj.deleted = True
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error removing proxy: {e}")
        return False
    finally:
        session.close()

def get_user_proxies(user_id):
    """Get user's active proxies"""
    try:
        session = SessionLocal()
        proxies = session.query(Proxy).filter(
            Proxy.user_id == user_id,
            Proxy.deleted == False
        ).all()
        return proxies
    except Exception as e:
        print(f"Error getting proxies: {e}")
        return []
    finally:
        session.close()
