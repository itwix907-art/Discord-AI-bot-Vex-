"""
career.py
----------
نظام الوظائف والبزنس (Career / Business):
  - سلم وظائف بمستويات ترقية: توصيل → كاشير → مدير → المدير التنفيذي...
  - كل وظيفة لها راتب ومتطلبات مستوى (XP Level)
  - كل ما تشتغل تاخذ راتب + نقاط أقدمية → تترقى لوظيفة أعلى
  - البزنس: تشتري مشروعك الخاص → أرباح يومية تجمعها بأمر collect
           وتقدر تطوره لزيادة الأرباح

الوظائف والأرقام كلها من لوحة التحكم: settings.career
"""

import time
import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.data_manager import get_user, update_user, load_settings, now_ts
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


def fmt_left(seconds: int) -> str:
    h, rem = divmod(max(0, int(seconds)), 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h} ساعة و {m} دقيقة"
    return f"{m} دقيقة"


class Career(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_job(self, job_id: str):
        cfg = load_settings().get("career", {})
        return next((j for j in cfg.get("jobs", []) if j["id"] == job_id), None)

    # ------------------------------------------------------------- قائمة الوظائف
    @commands.hybrid_group(name="career", aliases=["وظيفة", "وظائف"], invoke_without_command=True,
                           description="نظام الوظائف والبزنس")
    async def career(self, ctx: commands.Context):
        prefix = load_settings().get("bot", {}).get("prefix", "!")
        embed = base_embed("💼 نظام الوظائف والبزنس")
        embed.description = (
            f"`{prefix}career list` — الوظائف المتاحة\n"
            f"`{prefix}career apply <id>` — تقدم لوظيفة\n"
            f"`{prefix}career work` — اشتغل واحصل على راتبك\n"
            f"`{prefix}career promote` — اطلب ترقية\n"
            f"`{prefix}career quit` — استقل من وظيفتك\n"
            f"`{prefix}career status` — وضعك الوظيفي\n"
            f"`{prefix}career business` — نظام البزنس الخاص"
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- عرض الوظائف
    @career.command(name="list", description="الوظائف المتاحة")
    async def career_list(self, ctx: commands.Context):
        cfg = load_settings().get("career", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام الوظائف معطل من الإدارة."))
            return

        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        my_level = int(user.get("level", 0))
        current_job = user.get("job", "")

        lines = []
        for job in sorted(cfg.get("jobs", []), key=lambda j: j.get("tier", 1)):
            req = int(job.get("req_level", 0))
            ok = my_level >= req
            mark = "✅" if ok else "🔒"
            current = "👈 وظيفتك الحالية" if job["id"] == current_job else ""
            lines.append(
                f"{mark} {job.get('emoji', '💼')} **{job['name']}** (`{job['id']}`)\n"
                f"└ الراتب: {currency(random.randint(*job.get('salary', [0, 0])))} تقريبًا — "
                f"المطلوب: مستوى {req} {current}"
            )

        embed = base_embed("💼 الوظائف المتاحة")
        embed.description = "\n\n".join(lines) or "لا توجد وظائف معرفة من الإدارة."
        embed.set_footer(text=f"مستواك الحالي: {my_level} — ترقى لوظائف أعلى بنظام XP")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- التقديم
    @career.command(name="apply", description="التقدم لوظيفة")
    @app_commands.describe(job_id="معرف الوظيفة (شوفه بأمر career list)")
    async def career_apply(self, ctx: commands.Context, job_id: str):
        cfg = load_settings().get("career", {})
        job = self._get_job(job_id.lower())
        if not job:
            await ctx.send(embed=error_embed("وظيفة غير موجودة", "شوف الوظائف المتاحة بأمر `career list`."))
            return

        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        my_level = int(user.get("level", 0))
        req = int(job.get("req_level", 0))

        if my_level < req:
            await ctx.send(embed=error_embed(
                "ما تجلس المتطلبات",
                f"وظيفة **{job['name']}** تتطلب مستوى **{req}** وأنت مستواك **{my_level}**.\n"
                "اكثر تكلم بالسيرفر وارفع مستوايك!"
            ))
            return

        update_user(ctx.author.id, {
            "job": job["id"],
            "job_seniority": 1,
            "job_works": 0
        })
        await ctx.send(embed=success_embed(
            "تم التعيين!",
            f"مبروك! صرت **{job.get('emoji', '💼')} {job['name']}**\n"
            f"اشتغل بأمر `career work` وخذ راتبك."
        ))

    # ------------------------------------------------------------- العمل
    @career.command(name="work", description="اشتغل واحصل على راتبك")
    async def career_work(self, ctx: commands.Context):
        cfg = load_settings().get("career", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام الوظائف معطل من الإدارة."))
            return

        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        job_id = user.get("job", "")
        if not job_id:
            await ctx.send(embed=error_embed("ما عندك وظيفة", "تقدم لوظيفة أول بأمر `career list` ثم `career apply`."))
            return

        job = self._get_job(job_id)
        if not job:
            update_user(ctx.author.id, {"job": ""})
            await ctx.send(embed=error_embed("الوظيفة ألغيت", "وظيفتك الحالية ما تعدت موجودة بالإعدادات. تقدم لوظيفة ثانية."))
            return

        now = now_ts()
        cooldown = int(cfg.get("work_cooldown_minutes", 45)) * 60
        elapsed = now - user.get("last_job_work", 0)
        if elapsed < cooldown:
            await ctx.send(embed=error_embed("لسا بدري!", f"شغلتك القادمة بعد **{fmt_left(cooldown - elapsed)}**."))
            return

        seniority = int(user.get("job_seniority", 1))
        bonus_pct = int(cfg.get("salary_seniority_bonus", 10)) * (seniority - 1)
        salary = random.randint(*job.get("salary", [50, 100]))
        salary = int(salary * (1 + bonus_pct / 100))

        works = int(user.get("job_works", 0)) + 1
        total_works = int(user.get("total_works", 0)) + 1

        update_user(ctx.author.id, {
            "wallet": user["wallet"] + salary,
            "total_earned": user.get("total_earned", 0) + salary,
            "last_job_work": now,
            "job_works": works,
            "total_works": total_works
        })

        promote_after = int(cfg.get("promote_after", 10))
        ready = works >= promote_after
        embed = success_embed(
            f"{job.get('emoji', '💼')} يومية زينة!",
            f"اشتغلت كـ **{job['name']}** وكسبت {currency(salary)}"
            + (f" (بونص أقدمية +{bonus_pct}%)" if bonus_pct else "")
        )
        progress = min(works, promote_after)
        embed.add_field(
            name="📈 نحو الترقية",
            value=f"`{'█' * progress}{'░' * (promote_after - progress)}` {progress}/{promote_after}"
                  + ("\n✨ جاهز للترقية! استخدم `career promote`" if ready else ""),
            inline=False
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- الترقية
    @career.command(name="promote", description="اطلب ترقية لوظيفة أعلى")
    async def career_promote(self, ctx: commands.Context):
        cfg = load_settings().get("career", {})
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        job_id = user.get("job", "")

        if not job_id:
            await ctx.send(embed=error_embed("ما عندك وظيفة", "تقدم لوظيفة أول!"))
            return

        job = self._get_job(job_id)
        if not job:
            await ctx.send(embed=error_embed("خطأ", "وظيفتك الحالية غير معرفة بالإعدادات."))
            return

        promote_after = int(cfg.get("promote_after", 10))
        works = int(user.get("job_works", 0))
        if works < promote_after:
            await ctx.send(embed=error_embed(
                "لسا بدري للترقية",
                f"لازم تشتغل **{promote_after}** مرة على الأقل بعد آخر ترقية (شغلت {works})."
            ))
            return

        jobs = sorted(cfg.get("jobs", []), key=lambda j: j.get("tier", 1))
        current_tier = int(job.get("tier", 1))
        my_level = int(user.get("level", 0))
        next_jobs = [j for j in jobs if int(j.get("tier", 1)) > current_tier]

        if next_jobs:
            target = next_jobs[0]
            req = int(target.get("req_level", 0))
            if my_level < req:
                await ctx.send(embed=error_embed(
                    "المستوى ما يكفي",
                    f"وظيفة **{target['name']}** تتطلب مستوى **{req}** وأنت **{my_level}**.\n"
                    "فعّل أكثر وارفع مستوايك بعدين رجوع ترقى!"
                ))
                return
            update_user(ctx.author.id, {
                "job": target["id"],
                "job_seniority": 1,
                "job_works": 0
            })
            await ctx.send(embed=success_embed(
                "🎉 ترقية مستحقة!",
                f"مبروك! رقيت من **{job['name']}** إلى **{target.get('emoji', '💼')} {target['name']}**\n"
                f"الراتب الجديد: {currency(random.randint(*target.get('salary', [0, 0])))} تقريبًا"
            ))
        else:
            # ما فيه وظيفة أعلى → زيادة أقدمية (بونص راتب دائم)
            max_seniority = 5
            seniority = int(user.get("job_seniority", 1))
            if seniority >= max_seniority:
                await ctx.send(embed=error_embed(
                    "قمة السلم! 🏔️",
                    f"وصلت أقصى أقدمية ({max_seniority}) في وظيفتك، وما فيه وظائف أعلى حاليًا."
                ))
                return
            update_user(ctx.author.id, {
                "job_seniority": seniority + 1,
                "job_works": 0
            })
            bonus = int(cfg.get("salary_seniority_bonus", 10)) * seniority
            await ctx.send(embed=success_embed(
                "⭐ ترقية أقدمية!",
                f"صار مستوى أقدميتك **{seniority + 1}** — راتبك زاد بونص دائم **+{bonus}%**"
            ))

    # ------------------------------------------------------------- الاستقالة
    @career.command(name="quit", description="استقل من وظيفتك")
    async def career_quit(self, ctx: commands.Context):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        if not user.get("job"):
            await ctx.send(embed=error_embed("خطأ", "ما عندك وظيفة تستقيل منها!"))
            return
        update_user(ctx.author.id, {"job": "", "job_seniority": 1, "job_works": 0})
        await ctx.send(embed=success_embed("تمت الاستقالة", "استقليت من وظيفتك. تقدر تقدم لوظيفة جديدة بأي وقت."))

    # ------------------------------------------------------------- الوضع الوظيفي
    @career.command(name="status", description="وضعك الوظيفي الحالي")
    async def career_status(self, ctx: commands.Context):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        job = self._get_job(user.get("job", "")) if user.get("job") else None

        embed = base_embed("📋 وضعك الوظيفي")
        if job:
            promote_after = int(load_settings().get("career", {}).get("promote_after", 10))
            works = int(user.get("job_works", 0))
            progress = min(works, promote_after)
            embed.add_field(name="💼 وظيفتك", value=f"{job.get('emoji', '💼')} {job['name']}", inline=True)
            embed.add_field(name="⭐ الأقدمية", value=f"مستوى {user.get('job_seniority', 1)}", inline=True)
            embed.add_field(name="✅ إجمالي الشغل", value=str(user.get("total_works", 0)), inline=True)
            embed.add_field(
                name="📈 الترقية",
                value=f"`{'█' * progress}{'░' * (promote_after - progress)}` {progress}/{promote_after}",
                inline=False
            )
        else:
            embed.description = "ما عندك وظيفة — تقدم بأمر `career list` ثم `career apply`."

        # البزنس
        biz = user.get("business")
        if biz:
            biz_cfg = load_settings().get("career", {}).get("business", {})
            next_collect = int(biz.get("last_collect", 0)) + 86400
            ready = now_ts() >= next_collect
            embed.add_field(
                name="🏪 بزنسك",
                value=f"مستوى {biz.get('level', 1)} — "
                      f"{'✅ جاهز للتحصيل!' if ready else f'التحصيل بعد {fmt_left(next_collect - now_ts())}'}",
                inline=False
            )
        else:
            biz_cfg = load_settings().get("career", {}).get("business", {})
            embed.add_field(
                name="🏪 بزنسك",
                value=f"ما عندك بزنس — ابدأ مشروعك بـ {currency(biz_cfg.get('start_cost', 10000))} بأمر `career business start`",
                inline=False
            )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- البزنس
    @career.command(name="business", description="إدارة بزنسك الخاص")
    @app_commands.describe(action="start / collect / upgrade")
    @app_commands.choices(action=[
        app_commands.Choice(name="🚀 start — ابدأ مشروعك", value="start"),
        app_commands.Choice(name="💵 collect — احصل أرباح اليوم", value="collect"),
        app_commands.Choice(name="📈 upgrade — طوّر بزنسك", value="upgrade"),
    ])
    async def career_business(self, ctx: commands.Context, action: app_commands.Choice[str]):
        cfg = load_settings().get("career", {})
        biz_cfg = cfg.get("business", {})
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        biz = user.get("business")
        now = now_ts()

        if action.value == "start":
            if biz:
                await ctx.send(embed=error_embed("عندك بزنس!", f"بزنسك مستواه {biz.get('level', 1)} — طوره بدل ما تفتح ثاني."))
                return
            cost = int(biz_cfg.get("start_cost", 10000))
            if user["wallet"] < cost:
                await ctx.send(embed=error_embed("رصيد غير كافي", f"تفتح بزنس بـ {currency(cost)} ومحفظتك فيها {currency(user['wallet'])}."))
                return
            update_user(ctx.author.id, {
                "wallet": user["wallet"] - cost,
                "business": {"level": 1, "last_collect": 0}
            })
            await ctx.send(embed=success_embed(
                "🚀 مشروع جديد!",
                f"فتحت بزنسك الخاص بـ {currency(cost)}!\n"
                f"كل يوم تقدر تحصّل أرباح بأمر `career business collect`."
            ))

        elif action.value == "collect":
            if not biz:
                await ctx.send(embed=error_embed("ما عندك بزنس", "ابدأ مشروعك أول بأمر `career business start`."))
                return
            elapsed = now - int(biz.get("last_collect", 0))
            if elapsed < 86400:
                await ctx.send(embed=error_embed("لسا بدري!", f"أرباح اليوم تتحصل بعد **{fmt_left(86400 - elapsed)}**."))
                return
            level = int(biz.get("level", 1))
            profit = random.randint(int(biz_cfg.get("daily_min", 100)), int(biz_cfg.get("daily_max", 400))) * level
            update_user(ctx.author.id, {
                "wallet": user["wallet"] + profit,
                "total_earned": user.get("total_earned", 0) + profit,
                "business": {"level": level, "last_collect": now}
            })
            await ctx.send(embed=success_embed(
                "💵 أرباح البزنس",
                f"حصلت على {currency(profit)} من بزنسك (مستوى {level})."
            ))

        elif action.value == "upgrade":
            if not biz:
                await ctx.send(embed=error_embed("ما عندك بزنس", "ابدأ مشروعك أول بأمر `career business start`."))
                return
            level = int(biz.get("level", 1))
            max_level = int(biz_cfg.get("max_level", 10))
            if level >= max_level:
                await ctx.send(embed=error_embed("أقصى مستوى", f"بزنسك وصل أقصى مستوى ({max_level}). مبروك يا رجل أعمال! 👔"))
                return
            mult = float(biz_cfg.get("upgrade_multiplier", 1.3))
            cost = int(biz_cfg.get("upgrade_cost", 5000) * (mult ** (level - 1)))
            if user["wallet"] < cost:
                await ctx.send(embed=error_embed("رصيد غير كافي", f"التطوير يكلف {currency(cost)} ومحفظتك فيها {currency(user['wallet'])}."))
                return
            update_user(ctx.author.id, {
                "wallet": user["wallet"] - cost,
                "business": {"level": level + 1, "last_collect": biz.get("last_collect", 0)}
            })
            await ctx.send(embed=success_embed(
                "📈 تم التطوير!",
                f"بزنسك صار **مستوى {level + 1}** — أرباحك اليومية زادت!\n"
                f"التطوير القادم يكلف حوالي {currency(int(biz_cfg.get('upgrade_cost', 5000) * (mult ** level)))}."
            ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Career(bot))
