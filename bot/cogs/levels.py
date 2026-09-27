"""
levels.py
----------
نظام الخبرة والمستويات (XP / Level) مع رتب تلقائية حسب النشاط:
  - العضو ياخذ خبرة كل ما يتكلم (مع كولداون لمنع السبام)
  - كل ما يوصل مستوى جديد → إعلان + إعطاء رتبة تلقائية لو محددة بالإعدادات
  - /rank لعرض مستواك و /levels لقائمة الأعلى مستوى

الرتب التلقائية تُضبط من لوحة التحكم: settings.levels.level_roles
مثال: [{"level": 5, "role_id": "123..."}, {"level": 10, "role_id": "456..."}]
"""

import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.data_manager import (
    get_user, update_user, load_settings, load_users, get_levels_leaderboard, now_ts
)
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


def xp_needed(level: int) -> int:
    """الخبرة المطلوبة للانتقال من مستوى `level` إلى المستوى التالي."""
    return 100 + 50 * level


def progress_bar(current: int, needed: int, length: int = 10) -> str:
    filled = int(length * min(1.0, current / max(1, needed)))
    return "█" * filled + "░" * (length - filled)


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.level_up_queue = {}  # (guild_id, user_id, new_level) → channel_id للتأخير

    # ------------------------------------------------------------- خبرة الكلام
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        cfg = load_settings().get("levels", {})
        if not cfg.get("enabled", True):
            return

        user = get_user(message.author.id, 100)
        now = now_ts()
        cooldown = int(cfg.get("xp_cooldown", 60))
        if now - user.get("last_xp", 0) < cooldown:
            return

        xp_gain = random.randint(int(cfg.get("xp_min", 3)), int(cfg.get("xp_max", 8)))
        old_level = int(user.get("level", 0))
        xp = int(user.get("xp", 0)) + xp_gain
        level = old_level
        xp_in_level = xp

        # حساب المستويات التراكمية
        total_needed = 0
        while True:
            total_needed += xp_needed(level)
            if xp_in_level >= total_needed:
                level += 1
                xp_in_level -= total_needed
                total_needed = 0
            else:
                break

        # نحفظ الخبرة كخبرة داخل المستوى الحالي (أبسط للعرض)
        updates = {"xp": xp_in_level, "level": level, "last_xp": now,
                   "messages": int(user.get("messages", 0)) + 1}
        update_user(message.author.id, updates)

        if level > old_level:
            await self._handle_level_up(message, level)

    # ------------------------------------------------------------- ترقية مستوى
    async def _handle_level_up(self, message: discord.Message, new_level: int):
        cfg = load_settings().get("levels", {})

        # مكافأة فلوس عند الترقية (اختيارية)
        reward = int(cfg.get("level_up_reward", 100))
        if reward > 0:
            from bot.utils.data_manager import add_wallet
            settings = load_settings()["economy"]
            add_wallet(message.author.id, reward, settings["max_wallet"])

        if cfg.get("announce", True):
            try:
                await message.channel.send(
                    embed=success_embed(
                        f"🎉 مستوى جديد!",
                        f"مبروك {message.author.mention}! وصلت للمستوى **{new_level}**"
                        + (f" وجائزة {currency(reward)} 🪙" if reward > 0 else "")
                    ),
                    delete_after=10
                )
            except discord.HTTPException:
                pass

        # رتب تلقائية
        role_entries = cfg.get("level_roles", []) or []
        for entry in sorted(role_entries, key=lambda e: e.get("level", 0), reverse=True):
            if new_level >= int(entry.get("level", 0)) and entry.get("role_id"):
                role = message.guild.get_role(int(entry["role_id"]))
                if role and role not in message.author.roles:
                    try:
                        await message.author.add_roles(role, reason=f"وصل المستوى {new_level}")
                    except discord.HTTPException:
                        pass
                break

    # ------------------------------------------------------------- بطاقة المستوى
    @commands.hybrid_command(name="rank", aliases=["مستواي", "level"], description="عرض مستواك وخبرتك")
    @app_commands.describe(member="العضو اللي تبي تشوف مستواه")
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        settings = load_settings()
        user = get_user(member.id, settings["economy"]["starting_balance"])

        level = int(user.get("level", 0))
        xp = int(user.get("xp", 0))
        needed = xp_needed(level)

        # ترتيب العضو
        users = load_users()
        sorted_users = sorted(users.items(), key=lambda kv: (kv[1].get("level", 0), kv[1].get("xp", 0)), reverse=True)
        position = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == str(member.id)), len(sorted_users))

        embed = base_embed(f"📊 مستوى {member.display_name}")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🏅 المستوى", value=str(level), inline=True)
        embed.add_field(name="⭐ الخبرة", value=f"{xp} / {needed}", inline=True)
        embed.add_field(name="📈 الترتيب", value=f"#{position} من {len(users)}", inline=True)
        embed.add_field(
            name="التقدم للمستوى القادم",
            value=f"`{progress_bar(xp, needed)}`",
            inline=False
        )
        embed.add_field(name="💬 الرسائل", value=f"{user.get('messages', 0)}", inline=True)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- لوحة المستويات
    @commands.hybrid_command(name="levels", aliases=["toplevels"], description="أعلى الأعضاء مستوى")
    async def levels(self, ctx: commands.Context):
        top = get_levels_leaderboard(10)
        if not top:
            await ctx.send(embed=error_embed("لا توجد بيانات", "ما فيه أي نشاط بعد."))
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, data) in enumerate(top):
            member = ctx.guild.get_member(int(uid)) if ctx.guild else None
            name = member.display_name if member else f"عضو {uid[-4:]}"
            medal = medals[i] if i < 3 else f"`#{i + 1}`"
            lines.append(f"{medal} **{name}** — مستوى {data.get('level', 0)} ({data.get('xp', 0)} XP)")

        embed = base_embed("📊 أعلى الأعضاء مستوى")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Levels(bot))
