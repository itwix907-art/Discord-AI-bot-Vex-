"""
embeds.py
----------
دوال مساعدة لإنشاء Embeds احترافية وموحدة الشكل بكل أوامر البوت.
"""

import discord
from datetime import datetime, timezone
from bot.utils.data_manager import load_settings


def _hex_to_int(hex_color: str) -> int:
    try:
        return int(hex_color.replace("#", ""), 16)
    except Exception:
        return 0xF5A623


def base_embed(title: str = None, description: str = None, color_key: str = "embed_color") -> discord.Embed:
    settings = load_settings()
    bot_cfg = settings.get("bot", {})
    color_hex = bot_cfg.get(color_key, "#F5A623")
    embed = discord.Embed(
        title=title,
        description=description,
        color=_hex_to_int(color_hex),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=bot_cfg.get("name", "Vixen EDR"))
    return embed


def success_embed(title: str, description: str) -> discord.Embed:
    return base_embed(f"✅ {title}", description, color_key="success_color")


def error_embed(title: str, description: str) -> discord.Embed:
    return base_embed(f"❌ {title}", description, color_key="error_color")


def currency(amount: int) -> str:
    settings = load_settings()
    symbol = settings.get("bot", {}).get("currency_symbol", "🪙")
    return f"{amount:,} {symbol}"
