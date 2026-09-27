"""
data_manager.py
----------------
مدير البيانات المركزي للبوت.
يتكفل بقراءة وكتابة ملفات JSON (المستخدمين + الإعدادات) بطريقة آمنة
(Thread-safe / Atomic Write) حتى لا تتلف البيانات إذا حدثت كتابة متزامنة
من البوت ولوحة التحكم بنفس الوقت.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent.parent / "data"
USERS_FILE = BASE_DIR / "users.json"
SETTINGS_FILE = BASE_DIR / "settings.json"
MARKET_FILE = BASE_DIR / "market.json"
LOANS_FILE = BASE_DIR / "loans.json"

_lock = threading.RLock()


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    """يكتب الملف بطريقة ذرية: يكتب بملف مؤقت ثم يستبدل الأصلي.
    هذا يمنع تلف الملف لو انقطع البرنامج أثناء الكتابة."""
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        _atomic_write(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # ملف تالف أو فارغ -> رجّع القيمة الافتراضية بدل ما يطيح البوت
        _atomic_write(path, default)
        return default


# ---------------------------------------------------------------------------
# إدارة المستخدمين
# ---------------------------------------------------------------------------

DEFAULT_USER = {
    "wallet": 0,
    "bank": 0,
    "last_daily": 0,
    "daily_streak": 0,
    "last_work": 0,
    "total_earned": 0,
    "inventory": [],
    "buffs": {},
    # --- نظام الخبرة والمستويات ---
    "xp": 0,
    "level": 0,
    "last_xp": 0,
    "messages": 0,
    # --- الأسهم والاستثمار ---
    "stocks": {},            # {"GOLD": {"qty": 2, "avg_cost": 100}}
    "last_interest": 0,      # آخر سحب فايدة بنكية
    "interest_total": 0,     # إجمالي الفوايد المسحوبة
    # --- السرقة ---
    "last_rob": 0,
    "rob_success": 0,
    "rob_fail": 0,
    "rob_profits": 0,
    # --- الوظائف والبزنس ---
    "job": "",               # id الوظيفة الحالية
    "job_seniority": 1,      # مستوى الأقدمية داخل نفس الوظيفة
    "job_works": 0,          # عدد مرات العمل بعد آخر ترقية
    "total_works": 0,
    "last_job_work": 0,
    "business": None         # {"level": 1, "last_collect": 0} أو None
}


def load_users() -> Dict[str, Any]:
    with _lock:
        return _read_json(USERS_FILE, {})


def save_users(data: Dict[str, Any]) -> None:
    with _lock:
        _atomic_write(USERS_FILE, data)


def get_user(user_id: int, starting_balance: int = 100) -> Dict[str, Any]:
    """يرجع بيانات مستخدم، وينشئها لو ما كانت موجودة."""
    with _lock:
        users = load_users()
        uid = str(user_id)
        if uid not in users:
            new_user = DEFAULT_USER.copy()
            new_user["wallet"] = starting_balance
            users[uid] = new_user
            save_users(users)
        else:
            # يضمن إن أي حقول جديدة تضاف بالتحديثات المستقبلية تنضاف تلقائيًا
            for key, value in DEFAULT_USER.items():
                if key not in users[uid]:
                    users[uid][key] = value
        return users[uid]


def update_user(user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """يحدث حقول معينة لمستخدم ويحفظ الملف."""
    with _lock:
        users = load_users()
        uid = str(user_id)
        if uid not in users:
            users[uid] = DEFAULT_USER.copy()
        users[uid].update(updates)
        save_users(users)
        return users[uid]


def add_wallet(user_id: int, amount: int, max_wallet: int = 1_000_000) -> int:
    """يضيف (أو يطرح إذا كان الرقم سالب) من محفظة المستخدم، مع احترام الحد الأقصى."""
    with _lock:
        users = load_users()
        uid = str(user_id)
        if uid not in users:
            users[uid] = DEFAULT_USER.copy()
        new_balance = users[uid].get("wallet", 0) + amount
        new_balance = max(0, min(new_balance, max_wallet))
        users[uid]["wallet"] = new_balance
        if amount > 0:
            users[uid]["total_earned"] = users[uid].get("total_earned", 0) + amount
        save_users(users)
        return new_balance


def add_bank(user_id: int, amount: int, max_bank: int = 5_000_000) -> int:
    with _lock:
        users = load_users()
        uid = str(user_id)
        if uid not in users:
            users[uid] = DEFAULT_USER.copy()
        new_balance = users[uid].get("bank", 0) + amount
        new_balance = max(0, min(new_balance, max_bank))
        users[uid]["bank"] = new_balance
        save_users(users)
        return new_balance


def get_leaderboard(limit: int = 10):
    """يرجع أغنى المستخدمين مرتبين حسب (محفظة + بنك)."""
    with _lock:
        users = load_users()
        ranked = sorted(
            users.items(),
            key=lambda kv: kv[1].get("wallet", 0) + kv[1].get("bank", 0),
            reverse=True
        )
        return ranked[:limit]


def get_levels_leaderboard(limit: int = 10):
    """يرجع أعلى المستخدمين مستوى وخبرة."""
    with _lock:
        users = load_users()
        ranked = sorted(
            users.items(),
            key=lambda kv: (kv[1].get("level", 0), kv[1].get("xp", 0)),
            reverse=True
        )
        return ranked[:limit]


# ---------------------------------------------------------------------------
# السوق (الأسهم)
# ---------------------------------------------------------------------------

def load_market() -> Dict[str, Any]:
    with _lock:
        return _read_json(MARKET_FILE, {"prices": {}, "last_update": 0})


def save_market(data: Dict[str, Any]) -> None:
    with _lock:
        _atomic_write(MARKET_FILE, data)


# ---------------------------------------------------------------------------
# القروض
# ---------------------------------------------------------------------------

def load_loans() -> Dict[str, Any]:
    with _lock:
        return _read_json(LOANS_FILE, {"next_id": 1, "loans": []})


def save_loans(data: Dict[str, Any]) -> None:
    with _lock:
        _atomic_write(LOANS_FILE, data)


# ---------------------------------------------------------------------------
# إدارة الإعدادات (تُقرأ من لوحة التحكم أيضًا)
# ---------------------------------------------------------------------------

def load_settings() -> Dict[str, Any]:
    """يقرأ الإعدادات ويدمجها مع الافتراضيات — لو الملف ناقص أو تالف
    البوت يستمر شغال بالقيم الافتراضية بدل ما يطيح."""
    with _lock:
        data = _read_json(SETTINGS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    for key, val in DEFAULT_SETTINGS.items():
        if key not in data:
            data[key] = val
        elif isinstance(val, dict) and isinstance(data[key], dict):
            for k2, v2 in val.items():
                data[key].setdefault(k2, v2)
    return data


def save_settings(data: Dict[str, Any]) -> None:
    with _lock:
        _atomic_write(SETTINGS_FILE, data)


# الإعدادات الافتراضية (تُدمج تلقائيًا لو نقص أي قسم من الملف)
DEFAULT_SETTINGS: Dict[str, Any] = {
    "bot": {
        "name": "Vixen EDR",
        "prefix": "!",
        "currency_name": "عملة",
        "currency_symbol": "🪙",
        "embed_color": "#F5A623",
        "success_color": "#2ECC71",
        "error_color": "#E74C3C",
    },
    "economy": {
        "starting_balance": 100,
        "max_wallet": 1000000,
        "max_bank": 5000000,
        "daily_min": 200,
        "daily_max": 500,
        "daily_streak_bonus": 25,
        "daily_streak_cap": 500,
        "work_min": 50,
        "work_max": 300,
        "work_cooldown_minutes": 60,
        "transfer_tax_percent": 2,
        "transfer_min_amount": 10,
    },
    "gambling": {
        "slots_min_bet": 10,
        "slots_max_bet": 5000,
        "slots_win_multiplier": 3,
        "slots_jackpot_multiplier": 10,
        "blackjack_min_bet": 10,
        "blackjack_max_bet": 10000,
        "coinflip_min_bet": 10,
        "coinflip_max_bet": 5000,
        "gambling_enabled": True,
    },
    "shop": {
        "items": [
            {"id": "vip_role", "name": "VIP", "description": "رتبة VIP مميزة داخل السيرفر", "price": 5000, "type": "role", "role_id": "", "emoji": "👑"},
            {"id": "color_role", "name": "لون مخصص", "description": "رتبة لون خاص باسمك", "price": 2000, "type": "role", "role_id": "", "emoji": "🎨"},
            {"id": "lucky_charm", "name": "تعويذة الحظ", "description": "تزيد فرصة الربح في القمار لمدة ساعة", "price": 1500, "type": "item", "role_id": "", "emoji": "🍀"},
        ]
    },
    "roles": {"level_roles": [], "autorole_enabled": False, "autorole_id": ""},
    "channels": {"log_channel_id": "", "welcome_channel_id": ""},
    "leaderboard": {"show_top": 10},
    "atria": {"enabled": True, "moderation_enabled": False, "moderation_prefixes": ["[mod]", "!modcheck"]},
    "dashboard": {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8080,
        
    },
    "ranks": {
        "owner_id": "",
        "permissions": {},
        "daily_limits": {},
    },
    "levels": {
        "enabled": True,
        "xp_min": 3,
        "xp_max": 8,
        "xp_cooldown": 60,
        "level_up_reward": 100,
        "announce": True,
        "level_roles": [],
    },
    "bank_interest": {
        "enabled": True,
        "daily_rate": 2.0,
        "max_interest": 5000,
        "min_bank": 100,
    },
    "stocks": {
        "enabled": True,
        "update_interval_min": 5,
        "volatility": 12,
        "symbols": [
            {"symbol": "GOLD", "name": "الذهب", "emoji": "🥇", "base_price": 150},
            {"symbol": "OIL", "name": "النفط", "emoji": "🛢️", "base_price": 90},
            {"symbol": "TECH", "name": "التكنولوجيا", "emoji": "💻", "base_price": 250},
            {"symbol": "MEME", "name": "ميم كوين", "emoji": "🐸", "base_price": 25},
            {"symbol": "ROCKET", "name": "صاروخ للاستثمار", "emoji": "🚀", "base_price": 500},
        ]
    },
    "loans": {
        "enabled": True,
        "min_amount": 100,
        "max_amount": 50000,
        "default_interest": 10,
        "max_duration_days": 7,
        "max_active": 2,
    },
    "rob": {
        "enabled": True,
        "success_chance": 45,
        "fine_percent": 25,
        "cooldown_minutes": 30,
        "min_victim_wallet": 100,
        "max_steal_percent": 40,
        "fine_to_victim": True,
    },
    "career": {
        "enabled": True,
        "work_cooldown_minutes": 45,
        "promote_after": 10,
        "salary_seniority_bonus": 10,
        "jobs": [
            {"id": "delivery", "name": "موظف توصيل", "emoji": "🛵", "tier": 1, "salary": [80, 150], "req_level": 0},
            {"id": "cashier", "name": "كاشير", "emoji": "🧾", "tier": 2, "salary": [150, 260], "req_level": 3},
            {"id": "agent", "name": "موظف مبيعات", "emoji": "📊", "tier": 3, "salary": [280, 450], "req_level": 6},
            {"id": "manager", "name": "مدير فرع", "emoji": "💼", "tier": 4, "salary": [500, 800], "req_level": 10},
            {"id": "ceo", "name": "المدير التنفيذي", "emoji": "👔", "tier": 5, "salary": [900, 1500], "req_level": 15},
        ],
        "business": {
            "start_cost": 10000,
            "daily_min": 100,
            "daily_max": 400,
            "upgrade_cost": 5000,
            "upgrade_multiplier": 1.3,
            "max_level": 10,
        },
    },
}


def get_setting(path: str, default: Any = None) -> Any:
    """يقرأ إعداد باستخدام مسار منقط، مثال: get_setting('economy.daily_min')"""
    settings = load_settings()
    node = settings
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def now_ts() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# إحصائيات عامة (تستخدمها لوحة التحكم مباشرة)
# ---------------------------------------------------------------------------

def get_economy_stats() -> Dict[str, Any]:
    """إحصائيات مالية شاملة لكل السيرفر."""
    with _lock:
        users = load_users()
        total_users = len(users)
        total_wallet = sum(u.get("wallet", 0) for u in users.values())
        total_bank = sum(u.get("bank", 0) for u in users.values())
        total_earned = sum(u.get("total_earned", 0) for u in users.values())
        total_xp = sum(u.get("xp", 0) for u in users.values())
        return {
            "total_users": total_users,
            "total_wallet": total_wallet,
            "total_bank": total_bank,
            "total_money": total_wallet + total_bank,
            "total_earned": total_earned,
            "total_xp": total_xp,
        }
