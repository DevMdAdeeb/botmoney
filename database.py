import sqlite3
import threading
from typing import Optional, List, Dict, Any, Tuple
from config import DATABASE_PATH

local_db = threading.local()

def get_connection(db_path: str = DATABASE_PATH) -> sqlite3.Connection:
    if not hasattr(local_db, "connection") or local_db.connection is None:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        local_db.connection = conn
    return local_db.connection

def init_db(db_path: str = DATABASE_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            balance REAL DEFAULT 0.0,
            total_earned REAL DEFAULT 0.0,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Mandatory Channels table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT UNIQUE NOT NULL,
            title TEXT,
            invite_link TEXT NOT NULL
        )
    """)

    # Payment Methods table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            instructions TEXT
        )
    """)

    # Custom Inline Buttons table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT NOT NULL, -- 'url' or 'text'
            value TEXT NOT NULL
        )
    """)

    # Withdrawals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            payment_method TEXT NOT NULL,
            account_details TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Set default settings if not exist
    default_settings = {
        "referral_reward": "0.5",
        "min_withdrawal": "5.0",
        "welcome_message": (
            "مرحباً بك يا {name} في بوت الربح! 🚀\n\n"
            "🆔 معرفك: `{id}`\n"
            "💰 رصيدك: `${balance}`\n\n"
            "🔗 رابط الإحالة الخاص بك:\n`{ref_link}`\n\n"
            "قم بمشاركة رابطك مع أصدقائك واكسب لكل شخص يقوم بالانضمام!"
        )
    }

    for key, val in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()


# --- User Functions ---
def get_user(user_id: int, db_path: str = DATABASE_PATH) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def register_user(user_id: int, first_name: str, username: Optional[str], referred_by: Optional[int] = None, db_path: str = DATABASE_PATH) -> bool:
    """Registers a user if not exists. Returns True if new user registered."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        return False

    # Prevent self-referral or invalid referrer
    if referred_by == user_id:
        referred_by = None
    elif referred_by:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referred_by,))
        if not cursor.fetchone():
            referred_by = None

    cursor.execute(
        "INSERT INTO users (user_id, first_name, username, referred_by) VALUES (?, ?, ?, ?)",
        (user_id, first_name, username, referred_by)
    )
    conn.commit()
    conn.close()
    return True

def reward_referrer_if_pending(user_id: int, db_path: str = DATABASE_PATH) -> Optional[Tuple[int, float]]:
    """
    Rewards the referrer once the new user completes subscription checks.
    Returns (referrer_id, reward_amount) if reward was given, else None.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        conn.close()
        return None

    referrer_id = row[0]

    # Check if reward setting is present
    cursor.execute("SELECT value FROM settings WHERE key = 'referral_reward'")
    sett = cursor.fetchone()
    reward = float(sett[0]) if sett else 0.5

    # Reward referrer
    cursor.execute(
        "UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, referrals_count = referrals_count + 1 WHERE user_id = ?",
        (reward, reward, referrer_id)
    )

    # Clear referred_by so reward is only given once upon verification
    cursor.execute("UPDATE users SET referred_by = NULL WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()
    return (referrer_id, reward)

def update_user_balance(user_id: int, amount: float, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def set_user_ban_status(user_id: int, is_banned: bool, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def get_all_users(db_path: str = DATABASE_PATH) -> List[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_total_users_count(db_path: str = DATABASE_PATH) -> int:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


# --- Settings Functions ---
def get_setting(key: str, default: str = "", db_path: str = DATABASE_PATH) -> str:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str, db_path: str = DATABASE_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# --- Channels Functions ---
def add_channel(chat_id: str, title: str, invite_link: str, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?)", (chat_id, title, invite_link))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_channel(channel_id: int, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def get_all_channels(db_path: str = DATABASE_PATH) -> List[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Custom Buttons Functions ---
def add_custom_button(title: str, btn_type: str, value: str, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO custom_buttons (title, type, value) VALUES (?, ?, ?)", (title, btn_type, value))
    conn.commit()
    conn.close()
    return True

def remove_custom_button(button_id: int, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM custom_buttons WHERE id = ?", (button_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def get_all_custom_buttons(db_path: str = DATABASE_PATH) -> List[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM custom_buttons")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_custom_button(button_id: int, db_path: str = DATABASE_PATH) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM custom_buttons WHERE id = ?", (button_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# --- Payment Methods Functions ---
def add_payment_method(name: str, instructions: str = "", db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO payment_methods (name, instructions) VALUES (?, ?)", (name, instructions))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_payment_method(method_id: int, db_path: str = DATABASE_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM payment_methods WHERE id = ?", (method_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def get_all_payment_methods(db_path: str = DATABASE_PATH) -> List[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payment_methods")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Withdrawal Functions ---
def create_withdrawal_request(user_id: int, payment_method: str, account_details: str, amount: float, db_path: str = DATABASE_PATH) -> Optional[int]:
    """Creates withdrawal request and deducts user balance atomically."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row[0] < amount:
            conn.close()
            return None

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cursor.execute(
            "INSERT INTO withdrawals (user_id, payment_method, account_details, amount, status) VALUES (?, ?, ?, ?, 'pending')",
            (user_id, payment_method, account_details, amount)
        )
        withdrawal_id = cursor.lastrowid
        conn.commit()
        return withdrawal_id
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()

def process_withdrawal_request(withdrawal_id: int, approve: bool, db_path: str = DATABASE_PATH) -> Optional[dict]:
    """
    Approves or rejects withdrawal. If rejected, refunds user balance.
    Returns the withdrawal record.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
        row = cursor.fetchone()
        if not row or row["status"] != "pending":
            conn.close()
            return None

        w_dict = dict(row)
        new_status = "approved" if approve else "rejected"
        cursor.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (new_status, withdrawal_id))

        if not approve:
            # Refund user balance
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (w_dict["amount"], w_dict["user_id"]))

        conn.commit()
        w_dict["status"] = new_status
        return w_dict
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()

def get_withdrawal(withdrawal_id: int, db_path: str = DATABASE_PATH) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_stats(db_path: str = DATABASE_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(referrals_count) FROM users")
    total_referrals = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'approved'")
    total_withdrawn = cursor.fetchone()[0] or 0.0

    cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
    pending_withdrawals = cursor.fetchone()[0]

    conn.close()
    return {
        "total_users": total_users,
        "total_referrals": total_referrals,
        "total_withdrawn": total_withdrawn,
        "pending_withdrawals": pending_withdrawals
    }
