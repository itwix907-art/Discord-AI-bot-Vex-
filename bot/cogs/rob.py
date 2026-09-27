"""
rob.py
-------
نظام السرقة بين الأعضاء (Rob) بمخاطرة:
  - /rob @عضو → تحاول تسرق جزء من محفظته
  - نجاح → تاخذ نسبة من فلوس الضحية
  - فشل → تدفع غرامة (تروح للضحية) + كولداون أطول
  - /robstats → إحصائيات سرقاتك

كل النسب والفرص تُضبط من لوحة التحكم: settings.rob
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.data_manager import get_user, update_user, load_settings, now_ts
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


def fmt_left(seconds: int) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h} ساعة و {m} دقيقة"
    return f"{m} دقيقة و {s} ثانية"


class Rob(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------- السرقة
    @commands.hybrid_command(name="rob", aliases=["سرقة", "اسرق"], description="حاول تسرق عضو آخر (بمخاطرة!)")
    @app_commands.describe(member="الضحية")
    async def rob(self, ctx: commands.Context, member: discord.Member):
        cfg = load_settings().get("rob", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام السرقة معطل من الإدارة."))
            return
        if member.bot or member.id == ctx.author.id:
            await ctx.send(embed=error_embed("خطأ", "اختر ضحية صحيحة غيرك!"))
            return

        settings = load_settings()["economy"]
        robber = get_user(ctx.author.id, settings["starting_balance"])
        victim = get_user(member.id, settings["starting_balance"])
        now = now_ts()

        # كولداون
        cooldown = int(cfg.get("cooldown_minutes", 30)) * 60
        elapsed = now - robber.get("last_rob", 0)
        if elapsed < cooldown:
            await ctx.send(embed=error_embed(
                "ارتاح شوي 😅",
                f"تقدر تحاول تسرق مرة ثانية بعد **{fmt_left(cooldown - elapsed)}**."
            ))
            return

        # الضحية لازم يكون عنده فلوس تُسرق
        min_wallet = int(cfg.get("min_victim_wallet", 100))
        if victim["wallet"] < min_wallet:
            await ctx.send(embed=error_embed(
                "لا يستاهل",
                f"محفظة {member.display_name} فيها {currency(victim['wallet'])} — أقل حد للسرقة {currency(min_wallet)}."
            ))
            return
        if robber["wallet"] < min_wallet:
            await ctx.send(embed=error_embed("محفظتك فاضية", f"لازم يكون بجيبك على الأقل {currency(min_wallet)} حتى تحاول تسرق."))

        # بيانات الضحية المرسلة قبل التحديث
        victim_wallet = victim["wallet"]
        robber_wallet = robber["wallet"]
        success_chance = float(cfg.get("success_chance", 45))
        max_steal_pct = float(cfg.get("max_steal_percent", 40))

        update_user(ctx.author.id, {"last_rob": now})

        if random.uniform(0, 100) <= success_chance:
            # نجاح — سرقة نسبة من محفظة الضحية
            stolen = int(victim_wallet * (max_steal_pct / 100) * random.uniform(0.5, 1.0))
            stolen = max(1, stolen)
            update_user(ctx.author.id, {
                "wallet": robber_wallet + stolen,
                "rob_success": robber.get("rob_success", 0) + 1,
                "rob_profits": robber.get("rob_profits", 0) + stolen,
            })
            update_user(member.id, {"wallet": victim_wallet - stolen})

            embed = success_embed(
                "🚨 سرقة ناجحة!",
                f"خشيت جيب {member.mention} بسرعة وكسبت **{currency(stolen)}** 🤑"
            )
            embed.add_field(name="محفظتك الآن", value=currency(robber_wallet + stolen), inline=True)
            await ctx.send(embed=embed)
        else:
            # فشل — غرامة تروح للضحية
            fine_pct = float(cfg.get("fine_percent", 25))
            fine = int(robber_wallet * (fine_pct / 100))
            fine = max(1, fine)

            if cfg.get("fine_to_victim", True):
                update_user(ctx.author.id, {
                    "wallet": robber_wallet - fine,
                    "rob_fail": robber.get("rob_fail", 0) + 1,
                })
                update_user(member.id, {"wallet": victim_wallet + fine})
                fine_txt = f"الغرامة ({currency(fine)}) رحت للضحية {member.mention} 🤣"
            else:
                update_user(ctx.author.id, {
                    "wallet": robber_wallet - fine,
                    "rob_fail": robber.get("rob_fail", 0) + 1,
                })
                fine_txt = f"دفعت غرامة {currency(fine)} 💸"

            embed = error_embed(
                "🚔 فشلت السرقة!",
                f"مسكوك على حار {member.mention}!\n{fine_txt}"
            )
            embed.add_field(name="محفظتك الآن", value=currency(max(0, robber_wallet - fine)), inline=True)
            await ctx.send(embed=embed)

    # ------------------------------------------------------------- إحصائيات
    @commands.hybrid_command(name="robstats", aliases=["سرقاتي"], description="إحصائيات سرقاتك")
    async def robstats(self, ctx: commands.Context):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        success = user.get("rob_success", 0)
        fail = user.get("rob_fail", 0)
        total = success + fail
        rate = (success / total * 100) if total else 0

        embed = base_embed("🥷 إحصائيات سرقاتك")
        embed.add_field(name="✅ سرقات ناجحة", value=str(success), inline=True)
        embed.add_field(name="❌ مرات الفشل", value=str(fail), inline=True)
        embed.add_field(name="📊 نسبة النجاح", value=f"{rate:.0f}%", inline=True)
        embed.add_field(name="💰 إجمالي المكاسب", value=currency(user.get("rob_profits", 0)), inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Rob(bot))
