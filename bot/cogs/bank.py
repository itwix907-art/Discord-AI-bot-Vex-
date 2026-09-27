"""
bank.py
--------
أوامر البنك: إيداع، سحب، وسحب الفايدة اليومية /interest.

الفايدة البنكية: كل يوم تقدر تسحب فايدة على رصيد بنكك (نسبة مئوية
تُضبط من لوحة التحكم settings.bank_interest) — كافئة للادخار!
"""

from discord import app_commands
from discord.ext import commands

from bot.utils.data_manager import get_user, load_settings, update_user, now_ts
from bot.utils.embeds import success_embed, error_embed, currency


class Bank(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="deposit", aliases=["dep", "ايداع"], description="أودع فلوس من محفظتك للبنك")
    @app_commands.describe(amount="المبلغ أو اكتب all للكل")
    async def deposit(self, ctx: commands.Context, amount: str):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])

        if amount.lower() in ("all", "الكل", "كل"):
            value = user["wallet"]
        else:
            try:
                value = int(amount)
            except ValueError:
                await ctx.send(embed=error_embed("خطأ", "اكتب رقم صحيح أو `all`."))
                return

        if value <= 0:
            await ctx.send(embed=error_embed("خطأ", "المبلغ لازم يكون أكبر من صفر."))
            return
        if user["wallet"] < value:
            await ctx.send(embed=error_embed("رصيد غير كافي", "ما عندك فلوس كافية بالمحفظة."))
            return
        if user["bank"] + value > settings["max_bank"]:
            await ctx.send(embed=error_embed("تجاوزت الحد", f"أقصى رصيد بالبنك هو {currency(settings['max_bank'])}"))
            return

        update_user(ctx.author.id, {
            "wallet": user["wallet"] - value,
            "bank": user["bank"] + value
        })
        await ctx.send(embed=success_embed("تم الإيداع", f"أودعت {currency(value)} بالبنك."))

    @commands.hybrid_command(name="withdraw", aliases=["with", "سحب"], description="اسحب فلوس من البنك لمحفظتك")
    @app_commands.describe(amount="المبلغ أو اكتب all للكل")
    async def withdraw(self, ctx: commands.Context, amount: str):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])

        if amount.lower() in ("all", "الكل", "كل"):
            value = user["bank"]
        else:
            try:
                value = int(amount)
            except ValueError:
                await ctx.send(embed=error_embed("خطأ", "اكتب رقم صحيح أو `all`."))
                return

        if value <= 0:
            await ctx.send(embed=error_embed("خطأ", "المبلغ لازم يكون أكبر من صفر."))
            return
        if user["bank"] < value:
            await ctx.send(embed=error_embed("رصيد غير كافي", "ما عندك فلوس كافية بالبنك."))
            return
        if user["wallet"] + value > settings["max_wallet"]:
            await ctx.send(embed=error_embed("تجاوزت الحد", f"أقصى رصيد بالمحفظة هو {currency(settings['max_wallet'])}"))
            return

        update_user(ctx.author.id, {
            "wallet": user["wallet"] + value,
            "bank": user["bank"] - value
        })
        await ctx.send(embed=success_embed("تم السحب", f"سحبت {currency(value)} من البنك."))

    # ------------------------------------------------------------- فايدة يومية
    @commands.hybrid_command(name="interest", aliases=["فايدة"], description="اسحب فايدتك اليومية على رصيد البنك")
    async def interest(self, ctx: commands.Context):
        cfg = load_settings().get("bank_interest", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام الفايدة معطل من الإدارة."))
            return

        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        now = now_ts()
        cooldown = 24 * 3600
        elapsed = now - user.get("last_interest", 0)

        if elapsed < cooldown:
            remaining = cooldown - elapsed
            h, rem = divmod(remaining, 3600)
            m, _ = divmod(rem, 60)
            await ctx.send(embed=error_embed("لسا بدري!", f"فايدتك القادمة بعد **{h} ساعة و {m} دقيقة**."))
            return

        bank_balance = user["bank"]
        min_bank = int(cfg.get("min_bank", 100))
        if bank_balance < min_bank:
            await ctx.send(embed=error_embed(
                "رصيد البنك ما يكفي",
                f"لازم يكون ببنكك على الأقل {currency(min_bank)} عشان تحسب فايدة."
                "\nادّخر بأمر `/deposit` وارجع لك!"
            ))
            return

        rate = float(cfg.get("daily_rate", 2.0))
        gain = int(bank_balance * rate / 100)
        gain = min(gain, int(cfg.get("max_interest", 5000)))

        update_user(ctx.author.id, {
            "bank": bank_balance + gain,
            "last_interest": now,
            "interest_total": user.get("interest_total", 0) + gain
        })

        embed = success_embed(
            "🏦 فايدة بنكية!",
            f"رصيد بنكك {currency(bank_balance)} × {rate}% = **{currency(gain)}** أضافت لبنكك!"
        )
        embed.add_field(name="🏦 رصيد البنك الجديد", value=currency(bank_balance + gain), inline=True)
        embed.add_field(name="💰 إجمالي فوايدك", value=currency(user.get("interest_total", 0) + gain), inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Bank(bot))
