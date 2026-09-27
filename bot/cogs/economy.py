"""
economy.py
-----------
الأوامر الأساسية لنظام العملات: الرصيد، اليومي، العمل، التحويل.
"""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.data_manager import (
    get_user, add_wallet, update_user, load_settings, now_ts
)
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


def fmt_time(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} ساعة")
    if m:
        parts.append(f"{m} دقيقة")
    if s and not h:
        parts.append(f"{s} ثانية")
    return " و ".join(parts) if parts else "أقل من ثانية"


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------- رصيد
    @commands.hybrid_command(name="balance", aliases=["bal", "رصيد"], description="عرض رصيدك أو رصيد عضو آخر")
    @app_commands.describe(member="العضو اللي تبي تشوف رصيده")
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        settings = load_settings()
        user = get_user(member.id, settings["economy"]["starting_balance"])

        embed = base_embed(f"محفظة {member.display_name}")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="💵 المحفظة", value=currency(user["wallet"]), inline=True)
        embed.add_field(name="🏦 البنك", value=currency(user["bank"]), inline=True)
        embed.add_field(name="💰 الإجمالي", value=currency(user["wallet"] + user["bank"]), inline=True)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------------- يومي
    @commands.hybrid_command(name="daily", aliases=["يومي"], description="احصل على مكافأتك اليومية")
    async def daily(self, ctx: commands.Context):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])

        now = now_ts()
        last_daily = user.get("last_daily", 0)
        cooldown = 24 * 3600
        elapsed = now - last_daily

        if elapsed < cooldown:
            remaining = cooldown - elapsed
            embed = error_embed("لسا مو وقتها!", f"لازم تنتظر **{fmt_time(remaining)}** عشان تقدر تاخذ يوميتك مرة ثانية.")
            await ctx.send(embed=embed)
            return

        # سلسلة الأيام المتتالية (Streak)
        streak = user.get("daily_streak", 0)
        if elapsed <= cooldown * 2:  # جدد باليوم التالي مباشرة = يكمل السلسلة
            streak += 1
        else:
            streak = 1

        base_amount = random.randint(settings["daily_min"], settings["daily_max"])
        bonus = min(streak * settings["daily_streak_bonus"], settings["daily_streak_cap"])
        total = base_amount + bonus

        add_wallet(ctx.author.id, total, settings["max_wallet"])
        update_user(ctx.author.id, {"last_daily": now, "daily_streak": streak})

        embed = success_embed("مكافأة يومية!", f"حصلت على {currency(total)}")
        embed.add_field(name="🔥 سلسلة الأيام", value=f"{streak} يوم متواصل", inline=True)
        embed.add_field(name="🎁 بونص السلسلة", value=currency(bonus), inline=True)
        await ctx.send(embed=embed)

    # ---------------------------------------------------------------- عمل
    @commands.hybrid_command(name="work", aliases=["عمل"], description="اعمل واكسب فلوس")
    async def work(self, ctx: commands.Context):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])

        now = now_ts()
        last_work = user.get("last_work", 0)
        cooldown = settings["work_cooldown_minutes"] * 60
        elapsed = now - last_work

        if elapsed < cooldown:
            remaining = cooldown - elapsed
            embed = error_embed("لسا متعب!", f"لازم تستريح **{fmt_time(remaining)}** قبل ما تشتغل مرة ثانية.")
            await ctx.send(embed=embed)
            return

        jobs = [
            "دليفري", "برمجة موقع", "تصميم شعار", "تعليم طالب",
            "تصوير مناسبة", "كتابة مقال", "إصلاح جهاز", "بيع بسطة"
        ]
        job = random.choice(jobs)
        amount = random.randint(settings["work_min"], settings["work_max"])

        add_wallet(ctx.author.id, amount, settings["max_wallet"])
        update_user(ctx.author.id, {"last_work": now})

        embed = success_embed("شغل زين!", f"اشتغلت **{job}** وكسبت {currency(amount)}")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- تحويل
    @commands.hybrid_command(name="transfer", aliases=["pay", "تحويل"], description="حول فلوس لعضو آخر")
    @app_commands.describe(member="العضو المستلم", amount="المبلغ")
    async def transfer(self, ctx: commands.Context, member: discord.Member, amount: int):
        settings = load_settings()["economy"]

        if member.bot:
            await ctx.send(embed=error_embed("خطأ", "ما تقدر تحول فلوس لبوت."))
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("خطأ", "ما تقدر تحول لنفسك."))
            return
        if amount < settings["transfer_min_amount"]:
            await ctx.send(embed=error_embed("خطأ", f"أقل مبلغ للتحويل هو {currency(settings['transfer_min_amount'])}"))
            return

        sender = get_user(ctx.author.id, settings["starting_balance"])
        if sender["wallet"] < amount:
            await ctx.send(embed=error_embed("رصيد غير كافي", "ما عندك فلوس كافية بالمحفظة لهذا التحويل."))
            return

        tax = int(amount * settings["transfer_tax_percent"] / 100)
        received = amount - tax

        add_wallet(ctx.author.id, -amount, settings["max_wallet"])
        add_wallet(member.id, received, settings["max_wallet"])
        get_user(member.id, settings["starting_balance"])  # يضمن إنشاء المستلم لو ما كان موجود

        embed = success_embed(
            "تم التحويل",
            f"حولت {currency(amount)} إلى {member.mention}\n"
            f"💸 ضريبة التحويل ({settings['transfer_tax_percent']}%): {currency(tax)}\n"
            f"📥 استلم {member.display_name}: {currency(received)}"
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
