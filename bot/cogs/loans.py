"""
loans.py
---------
نظام القروض بين الأعضاء (Loans):
  - /loan request @عضو مبلغ [أيام] → العضو يوافق أو يرفض بالأزرار
  - عند الموافقة: الفلوس تنتقل فورًا من محفظة المُقرض للمقترض
  - المقترض يرجع المبلغ + فايدة محددة بأمر /loan repay
  - لو تأخر بالسداد → القرض يتعلم "متأخر" ويمنعه من طلب قروض جديدة
  - /loan my → قروضك كدائن ومدين

كل شيء محفوظ في bot/data/loans.json.
"""

import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.data_manager import (
    get_user, update_user, load_settings, load_loans, save_loans, now_ts
)
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


def fmt_left(seconds: int) -> str:
    h, rem = divmod(max(0, seconds), 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h} ساعة و {m} دقيقة"
    return f"{m} دقيقة"


def has_overdue(loans_data: dict, user_id: int) -> bool:
    now = now_ts()
    for loan in loans_data["loans"]:
        if loan["borrower"] != str(user_id):
            continue
        # نشط ولم يستحق بعد، أو متأخر بالفعل — كلاهما يمنع قرضًا جديدًا
        if loan["status"] == "overdue" or (loan["status"] == "active" and loan["due"] < now):
            return True
    return False


def refresh_overdue(loans_data: dict) -> None:
    """يعلم أي قرض نشط فات موعده كـ متأخر."""
    now = now_ts()
    changed = False
    for loan in loans_data["loans"]:
        if loan["status"] == "active" and loan["due"] < now:
            loan["status"] = "overdue"
            changed = True
    if changed:
        save_loans(loans_data)


class LoanView(discord.ui.View):
    def __init__(self, cog, loan_id: int, borrower_id: int):
        super().__init__(timeout=86400)
        self.cog = cog
        self.loan_id = loan_id
        self.borrower_id = borrower_id

    @discord.ui.button(label="✅ موافقة", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.borrower_id:
            await interaction.response.send_message("هذا الطلب مو موجّه لك!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog.fund_loan(interaction.message, interaction, self.loan_id)
        self.stop()

    @discord.ui.button(label="❌ رفض", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.borrower_id:
            await interaction.response.send_message("هذا الطلب مو موجّه لك!", ephemeral=True)
            return
        loans_data = load_loans()
        loan = next((l for l in loans_data["loans"] if l["id"] == self.loan_id), None)
        if loan and loan["status"] == "pending":
            loan["status"] = "declined"
            save_loans(loans_data)
        embed = error_embed("تم الرفض", f"المقترض رفض القرض #{self.loan_id}.")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class Loans(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.overdue_check.start()

    def cog_unload(self):
        self.overdue_check.cancel()

    # ------------------------------------------------------------- فحص التأخير الدوري
    @tasks.loop(minutes=10)
    async def overdue_check(self):
        data = load_loans()
        refresh_overdue(data)

    @overdue_check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------- طلب قرض
    @commands.hybrid_group(name="loan", aliases=["قرض", "قروض"], invoke_without_command=True, description="نظام القروض بين الأعضاء")
    async def loan(self, ctx: commands.Context):
        embed = base_embed("💳 نظام القروض")
        prefix = load_settings().get("bot", {}).get("prefix", "!")
        embed.description = (
            f"`{prefix}loan request <عضو> <مبلغ> [أيام]` — اطلب قرض من عضو\n"
            f"`{prefix}loan repay <رقم>` — سدد قرضك (الكل افتراضيًا)\n"
            f"`{prefix}loan my` — قروضي كدائن ومدين"
        )
        await ctx.send(embed=embed)

    @loan.command(name="request", description="طلب قرض من عضو آخر")
    @app_commands.describe(lender="العضو اللي تطلب منه القرض", amount="مبلغ القرض", days="مدة السداد بالأيام (افتراضي 3)")
    async def loan_request(self, ctx: commands.Context, lender: discord.Member, amount: int, days: int = 3):
        cfg = load_settings().get("loans", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام القروض معطل من الإدارة."))
            return
        if lender.bot or lender.id == ctx.author.id:
            await ctx.send(embed=error_embed("خطأ", "اختر عضو صحيح غيرك."))
            return
        if amount < int(cfg.get("min_amount", 100)):
            await ctx.send(embed=error_embed("خطأ", f"أقل مبلغ قرض هو {currency(cfg.get('min_amount', 100))}."))
            return
        if amount > int(cfg.get("max_amount", 50000)):
            await ctx.send(embed=error_embed("خطأ", f"أقصى مبلغ قرض هو {currency(cfg.get('max_amount', 50000))}."))
            return
        days = max(1, min(days, int(cfg.get("max_duration_days", 7))))

        loans_data = load_loans()
        refresh_overdue(loans_data)

        # منع المدين المتأخر من طلب قروض جديدة
        if has_overdue(loans_data, ctx.author.id):
            await ctx.send(embed=error_embed("عندك قرض متأخر!", "سدد قروضك المتأخرة أول قبل ما تطلب قرض جديد."))
            return

        # حد عدد القروض النشطة
        active = [l for l in loans_data["loans"]
                  if l["borrower"] == str(ctx.author.id) and l["status"] in ("active", "overdue")]
        if len(active) >= int(cfg.get("max_active", 2)):
            await ctx.send(embed=error_embed("وصلت الحد", f"لازم تسدد قرض من قروضك الحالية ({len(active)})."))
            return

        # المُقرض لازم يكون محفظته تغطي المبلغ
        lender_user = get_user(lender.id, 100)
        if lender_user["wallet"] < amount:
            await ctx.send(embed=error_embed("ما يكفيه", f"محفظة {lender.display_name} ما تغطي هذا المبلغ."))
            return

        interest_pct = int(cfg.get("default_interest", 10))
        total = int(amount * (1 + interest_pct / 100))

        loan_id = loans_data["next_id"]
        loans_data["next_id"] += 1
        loan = {
            "id": loan_id,
            "lender": str(lender.id),
            "borrower": str(ctx.author.id),
            "principal": amount,
            "interest_pct": interest_pct,
            "total": total,
            "paid": 0,
            "status": "pending",
            "created": now_ts(),
            "due": now_ts() + days * 86400,
        }
        loans_data["loans"].append(loan)
        save_loans(loans_data)

        embed = base_embed(f"💳 طلب قرض #{loan_id}")
        embed.description = (
            f"{ctx.author.mention} يطلب قرضًا من {lender.mention}\n\n"
            f"💰 المبلغ: {currency(amount)}\n"
            f"📈 الفايدة: {interest_pct}%\n"
            f"💸 المطلوب سداده: {currency(total)}\n"
            f"⏳ المدة: {days} يوم"
        )
        embed.set_footer(text="للمقترض فقط: وافق بالزرار تحت")
        view = LoanView(self, loan_id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    # ------------------------------------------------------------- تمويل القرض (عند الموافقة)
    async def fund_loan(self, message: discord.Message, interaction: discord.Interaction, loan_id: int):
        loans_data = load_loans()
        loan = next((l for l in loans_data["loans"] if l["id"] == loan_id), None)
        if not loan or loan["status"] != "pending":
            await interaction.followup.send(embed=error_embed("انتهى الطلب", "هذا الطلب تم التعامل معه بالفعل."))
            return

        settings = load_settings()["economy"]
        lender_id = int(loan["lender"])
        borrower_id = int(loan["borrower"])

        lender_user = get_user(lender_id, settings["starting_balance"])
        if lender_user["wallet"] < loan["principal"]:
            loan["status"] = "declined"
            save_loans(loans_data)
            await interaction.followup.send(embed=error_embed("فشل التحويل", "محفظة المُقرض ما تغطي المبلغ بعد الآن."))
            return

        # نقل الفلوس: المُقرض → المقترض فورًا
        update_user(lender_id, {"wallet": lender_user["wallet"] - loan["principal"]})
        borrower_user = get_user(borrower_id, settings["starting_balance"])
        update_user(borrower_id, {"wallet": borrower_user["wallet"] + loan["principal"]})

        loan["status"] = "active"
        save_loans(loans_data)

        lender = self.bot.get_user(lender_id)
        borrower = self.bot.get_user(borrower_id)
        lender_name = lender.name if lender else f"ID {lender_id}"
        borrower_name = borrower.name if borrower else f"ID {borrower_id}"

        embed = success_embed(
            f"✅ القرض #{loan_id} نشط!",
            f"تم تحويل {currency(loan['principal'])} من **{lender_name}** إلى **{borrower_name}**\n"
            f"⏳ آخر موعد للسداد: <t:{loan['due']}:R>\n"
            f"💸 المطلوب سداده: {currency(loan['total'])}"
        )
        try:
            await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------- السداد
    @loan.command(name="repay", description="سداد قرض")
    @app_commands.describe(loan_id="رقم القرض (اتركه فارغًا لسداد كل قروضك)", full="سدد المبلغ كامل؟ (افتراضي نعم)")
    async def loan_repay(self, ctx: commands.Context, loan_id: int = None, full: bool = True):
        loans_data = load_loans()
        refresh_overdue(loans_data)

        if loan_id is None:
            mine = [l for l in loans_data["loans"] if l["borrower"] == str(ctx.author.id)
                    and l["status"] in ("active", "overdue")]
            if not mine:
                await ctx.send(embed=error_embed("ما عندك قروض", "ما عندك أي قروض تحتاج سداد."))
                return
            total_due = sum(l["total"] - l["paid"] for l in mine)
            await self._repay_amount(ctx, loans_data, mine, total_due)
            return

        loan = next((l for l in loans_data["loans"] if l["id"] == loan_id and l["borrower"] == str(ctx.author.id)), None)
        if not loan or loan["status"] not in ("active", "overdue"):
            await ctx.send(embed=error_embed("خطأ", "ما فيه قرض بهذا الرقم باسمك."))
            return
        await self._repay_amount(ctx, loans_data, [loan], loan["total"] - loan["paid"])

    async def _repay_amount(self, ctx, loans_data, loans, amount: int):
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        if user["wallet"] < amount:
            await ctx.send(embed=error_embed(
                "رصيد غير كافي",
                f"تحتاج {currency(amount)} بمحفظتك للسداد، وعندك {currency(user['wallet'])}."
            ))
            return

        update_user(ctx.author.id, {"wallet": user["wallet"] - amount})

        # توزيع المبلغ على القروض
        remaining = amount
        for loan in loans:
            if remaining <= 0:
                break
            due_now = loan["total"] - loan["paid"]
            pay = min(due_now, remaining)
            loan["paid"] += pay
            remaining -= pay
            if loan["paid"] >= loan["total"]:
                loan["status"] = "paid"
                lender_id = int(loan["lender"])
                lender_user = get_user(lender_id, settings["starting_balance"])
                update_user(lender_id, {"wallet": lender_user["wallet"] + pay})
            else:
                # سداد جزئي يروح للمُقرض أيضًا
                lender_id = int(loan["lender"])
                lender_user = get_user(lender_id, settings["starting_balance"])
                update_user(lender_id, {"wallet": lender_user["wallet"] + pay})

        save_loans(loans_data)
        await ctx.send(embed=success_embed("تم السداد", f"سددت {currency(amount)} بنجاح. الله يعافيك! 💰"))

    # ------------------------------------------------------------- قروضي
    @loan.command(name="my", description="عرض قروضي كدائن ومدين")
    async def loan_my(self, ctx: commands.Context):
        loans_data = load_loans()
        refresh_overdue(loans_data)

        debts = [l for l in loans_data["loans"] if l["borrower"] == str(ctx.author.id)
                 and l["status"] in ("active", "overdue", "pending")]
        credits = [l for l in loans_data["loans"] if l["lender"] == str(ctx.author.id)
                   and l["status"] in ("active", "overdue")]

        embed = base_embed(f"💳 قروض {ctx.author.display_name}")

        if debts:
            lines = []
            for l in debts:
                status = {"pending": "🟡 معلق", "active": "🟢 نشط", "overdue": "🔴 متأخر"}.get(l["status"], l["status"])
                lines.append(f"#{l['id']} — باقي عليك {currency(l['total'] - l['paid'])} — {status} — <t:{l['due']}:R>")
            embed.add_field(name="📥 ديونك", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📥 ديونك", value="ما عندك ديون ✨", inline=False)

        if credits:
            lines = []
            for l in credits:
                status = "🟢 نشط" if l["status"] == "active" else "🔴 متأخر"
                lines.append(f"#{l['id']} — لك {currency(l['total'] - l['paid'])} — {status} — <t:{l['due']}:R>")
            embed.add_field(name="📤 لك على الآخرين", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📤 لك على الآخرين", value="ما أقرضت أحد بعد", inline=False)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Loans(bot))
