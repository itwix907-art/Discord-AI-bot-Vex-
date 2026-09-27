"""
shop.py
--------
نظام المتجر: عرض المنتجات، الشراء، وعرض المخزون (Inventory).
المنتجات تُدار بالكامل من لوحة التحكم عن طريق settings.json -> shop.items
"""

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.data_manager import get_user, add_wallet, update_user, load_settings
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="shop", aliases=["متجر"], description="عرض متجر السيرفر")
    async def shop(self, ctx: commands.Context):
        settings = load_settings()
        items = settings.get("shop", {}).get("items", [])

        if not items:
            await ctx.send(embed=error_embed("المتجر فارغ", "ما فيه منتجات بالمتجر حاليًا."))
            return

        embed = base_embed("🛒 المتجر", "استخدم `buy <id>` عشان تشتري منتج")
        for item in items:
            embed.add_field(
                name=f"{item.get('emoji', '📦')} {item['name']}  —  {currency(item['price'])}",
                value=f"{item.get('description', '')}\n`ID: {item['id']}`",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy", aliases=["شراء"], description="اشتري منتج من المتجر")
    @app_commands.describe(item_id="آيدي المنتج من المتجر")
    async def buy(self, ctx: commands.Context, item_id: str):
        settings = load_settings()
        e = settings["economy"]
        items = settings.get("shop", {}).get("items", [])

        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            await ctx.send(embed=error_embed("غير موجود", "ما فيه منتج بهذا الآيدي. شوف `shop` للقائمة الكاملة."))
            return

        user = get_user(ctx.author.id, e["starting_balance"])
        if user["wallet"] < item["price"]:
            await ctx.send(embed=error_embed("رصيد غير كافي", f"تحتاج {currency(item['price'])} لشراء هذا المنتج."))
            return

        # لو المنتج رتبة، أعطها للعضو مباشرة
        if item.get("type") == "role" and item.get("role_id"):
            try:
                role = ctx.guild.get_role(int(item["role_id"]))
                if role:
                    await ctx.author.add_roles(role, reason="شراء من المتجر")
            except (discord.Forbidden, discord.HTTPException, ValueError):
                await ctx.send(embed=error_embed(
                    "خطأ بالصلاحيات",
                    "ما قدرت أعطيك الرتبة. تأكد إن رتبة البوت أعلى من الرتبة المطلوبة."
                ))
                return

        add_wallet(ctx.author.id, -item["price"], e["max_wallet"])
        inventory = user.get("inventory", [])
        inventory.append(item["id"])
        update_user(ctx.author.id, {"inventory": inventory})

        await ctx.send(embed=success_embed(
            "تم الشراء! 🎉",
            f"اشتريت **{item['name']}** مقابل {currency(item['price'])}"
        ))

    @commands.hybrid_command(name="inventory", aliases=["inv", "مخزون"], description="عرض مخزونك من المنتجات")
    async def inventory(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        settings = load_settings()
        items = {i["id"]: i for i in settings.get("shop", {}).get("items", [])}

        user = get_user(member.id, settings["economy"]["starting_balance"])
        inv = user.get("inventory", [])

        if not inv:
            await ctx.send(embed=base_embed("المخزون", f"{member.display_name} ما عنده أي منتجات."))
            return

        counts = {}
        for iid in inv:
            counts[iid] = counts.get(iid, 0) + 1

        lines = []
        for iid, count in counts.items():
            item = items.get(iid)
            name = item["name"] if item else iid
            emoji = item.get("emoji", "📦") if item else "📦"
            lines.append(f"{emoji} {name} × {count}")

        embed = base_embed(f"🎒 مخزون {member.display_name}", "\n".join(lines))
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
