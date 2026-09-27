"""
stocks.py
----------
نظام الأسهم والاستثمار (Stocks):
  - سوق فيه عدة أسهم أسعارها تتحرك تلقائيًا كل فترة (محاكاة بورصة)
  - اشترِ وبيّع واربح من فروقات الأسعار
  - محفظة استثمارية لكل عضو مع حساب الربح/الخسارة

الأسعار محفوظة في bot/data/market.json والأسهم تُضبط من لوحة التحكم.
"""

import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.data_manager import (
    get_user, update_user, load_settings, load_market, save_market, now_ts
)
from bot.utils.embeds import base_embed, success_embed, error_embed, currency


def _init_prices(market: dict, symbols_cfg: list) -> dict:
    """يضمن إن لكل سهم معرف بالإعدادات سعر مبدئي في السوق."""
    prices = market.setdefault("prices", {})
    for entry in symbols_cfg:
        sym = entry["symbol"].upper()
        if sym not in prices or not prices[sym].get("price"):
            base = float(entry.get("base_price", 100))
            prices[sym] = {
                "price": round(base, 2),
                "prev": round(base, 2),
                "base": base,
                "history": [base],
            }
    return market


def trend_emoji(market_price: dict) -> str:
    if market_price["price"] > market_price["prev"]:
        return "🔺"
    if market_price["price"] < market_price["prev"]:
        return "🔻"
    return "🔸"


def mini_chart(history: list, width: int = 14) -> str:
    """رسم مصغر لتاريخ السعر بحروف الكتل."""
    if len(history) < 2:
        return "—"
    data = history[-width:]
    lo, hi = min(data), max(data)
    rng = (hi - lo) or 1
    blocks = "▁▂▃▄▅▆▇█"
    return "".join(blocks[int((v - lo) / rng * 7)] for v in data)


class Stocks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_prices.start()

    def cog_unload(self):
        self.update_prices.cancel()

    # ------------------------------------------------------------- تحديث الأسعار
    @tasks.loop(minutes=5)
    async def update_prices(self):
        cfg = load_settings().get("stocks", {})
        if not cfg.get("enabled", True):
            return
        market = load_market()
        market = _init_prices(market, cfg.get("symbols", []))
        volatility = float(cfg.get("volatility", 12))

        for sym, entry in market["prices"].items():
            base = float(entry.get("base", entry["price"]))
            change_pct = random.uniform(-volatility, volatility) / 100
            # انحياز خفيف يعيد السعر نحو السعر الأساسي (يمنع الهروب للصفر/اللانهاية)
            drift = (base - entry["price"]) / base * 0.05
            new_price = entry["price"] * (1 + change_pct + drift)
            new_price = max(base * 0.15, min(base * 5, new_price))
            entry["prev"] = entry["price"]
            entry["price"] = round(new_price, 2)
            history = entry.setdefault("history", [])
            history.append(entry["price"])
            entry["history"] = history[-24:]

        market["last_update"] = now_ts()
        save_market(market)

    @update_prices.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------- عرض السوق
    @commands.hybrid_command(name="stocks", aliases=["بورصة", "market"], description="عرض سوق الأسهم الحالي")
    async def stocks(self, ctx: commands.Context):
        cfg = load_settings().get("stocks", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام الأسهم معطل حاليًا من الإدارة."))
            return

        market = _init_prices(load_market(), cfg.get("symbols", []))
        lines = []
        for entry in cfg.get("symbols", []):
            sym = entry["symbol"].upper()
            data = market["prices"].get(sym, {"price": entry.get("base_price", 100), "prev": 0, "history": []})
            change = ((data["price"] - data["prev"]) / data["prev"] * 100) if data.get("prev") else 0
            arrow = trend_emoji(data)
            lines.append(
                f"{entry.get('emoji', '📈')} **{sym}** ({entry.get('name', '')})\n"
                f"└ السعر: `{data['price']:,.2f}` {arrow} {change:+.1f}% — `{mini_chart(data.get('history', []))}`"
            )

        embed = base_embed("📈 سوق الأسهم")
        embed.description = "\n\n".join(lines) or "لا توجد أسهم معرفة."
        embed.set_footer(text="اشترِ بـ /stockbuy وبيّع بـ /stocksell — الأسعار تتغير كل فترة!")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- شراء
    @commands.hybrid_command(name="stockbuy", aliases=["اشتري"], description="شراء أسهم من السوق")
    @app_commands.describe(symbol="رمز السهم", qty="الكمية")
    async def stockbuy(self, ctx: commands.Context, symbol: str, qty: int):
        cfg = load_settings().get("stocks", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام الأسهم معطل حاليًا."))
            return
        if qty <= 0:
            await ctx.send(embed=error_embed("خطأ", "الكمية لازم تكون أكبر من صفر."))
            return

        symbol = symbol.upper()
        sym_cfg = next((s for s in cfg.get("symbols", []) if s["symbol"].upper() == symbol), None)
        if not sym_cfg:
            await ctx.send(embed=error_embed("سهم غير موجود", "شوف الأسهم المتاحة بأمر `/stocks`."))
            return

        market = _init_prices(load_market(), cfg.get("symbols", []))
        price = market["prices"][symbol]["price"]
        cost = int(round(price * qty))

        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        if user["wallet"] < cost:
            await ctx.send(embed=error_embed(
                "رصيد غير كافي",
                f"سعر السهم `{price:,.2f}` × {qty} = {currency(cost)}\nومحفظتك فيها {currency(user['wallet'])} فقط."
            ))
            return

        # تحديث المحفظة (متوسط تكلفة الشراء)
        portfolio = user.get("stocks", {}) or {}
        holding = portfolio.get(symbol, {"qty": 0, "avg_cost": 0})
        total_qty = holding["qty"] + qty
        avg_cost = ((holding["avg_cost"] * holding["qty"]) + cost) / total_qty
        portfolio[symbol] = {"qty": total_qty, "avg_cost": round(avg_cost, 2)}

        update_user(ctx.author.id, {
            "wallet": user["wallet"] - cost,
            "stocks": portfolio
        })

        embed = success_embed(
            "تم الشراء",
            f"{sym_cfg.get('emoji', '📈')} اشتريت **{qty} سهم {symbol}** بسعر `{price:,.2f}`\n"
            f"💰 الإجمالي المدفوع: {currency(cost)}"
        )
        embed.add_field(name="متوسط تكلفة سهمك", value=f"`{avg_cost:,.2f}`", inline=True)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- بيع
    @commands.hybrid_command(name="stocksell", aliases=["بيع"], description="بيع أسهم من محفظتك")
    @app_commands.describe(symbol="رمز السهم", qty="الكمية (أو اكتب all)")
    async def stocksell(self, ctx: commands.Context, symbol: str, qty: str):
        cfg = load_settings().get("stocks", {})
        if not cfg.get("enabled", True):
            await ctx.send(embed=error_embed("معطل", "نظام الأسهم معطل حاليًا."))
            return

        symbol = symbol.upper()
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        portfolio = user.get("stocks", {}) or {}
        holding = portfolio.get(symbol)

        if not holding or holding["qty"] <= 0:
            await ctx.send(embed=error_embed("ما عندك أسهم", f"ما تملك أي سهم من نوع `{symbol}`."))
            return

        if str(qty).lower() in ("all", "الكل", "كل"):
            sell_qty = holding["qty"]
        else:
            try:
                sell_qty = int(qty)
            except ValueError:
                await ctx.send(embed=error_embed("خطأ", "اكتب رقم صحيح أو `all`."))
                return

        if sell_qty <= 0 or sell_qty > holding["qty"]:
            await ctx.send(embed=error_embed("خطأ", f"تملك {holding['qty']} سهم فقط من `{symbol}`."))
            return

        market = _init_prices(load_market(), cfg.get("symbols", []))
        price = market["prices"][symbol]["price"]
        revenue = int(round(price * sell_qty))
        profit = int(round((price - holding["avg_cost"]) * sell_qty))

        remaining = holding["qty"] - sell_qty
        if remaining > 0:
            portfolio[symbol]["qty"] = remaining
        else:
            del portfolio[symbol]

        update_user(ctx.author.id, {
            "wallet": user["wallet"] + revenue,
            "stocks": portfolio
        })

        profit_txt = f"{'🟢 ربح' if profit >= 0 else '🔴 خسارة'}: {currency(abs(profit))}"
        embed = success_embed(
            "تم البيع",
            f"بعت **{sell_qty} سهم {symbol}** بسعر `{price:,.2f}`\n"
            f"💵 حصلت على: {currency(revenue)}\n{profit_txt}"
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------- المحفظة الاستثمارية
    @commands.hybrid_command(name="portfolio", aliases=["محفظتي"], description="عرض محفظتك الاستثمارية")
    async def portfolio(self, ctx: commands.Context):
        cfg = load_settings().get("stocks", {})
        market = _init_prices(load_market(), cfg.get("symbols", []))
        settings = load_settings()["economy"]
        user = get_user(ctx.author.id, settings["starting_balance"])
        portfolio = user.get("stocks", {}) or {}

        if not portfolio:
            await ctx.send(embed=error_embed("محفظتك فاضية", "اشترِ أول سهم بأمر `/stockbuy`."))
            return

        sym_names = {s["symbol"].upper(): s for s in cfg.get("symbols", [])}
        lines = []
        total_value = 0
        total_cost = 0
        for sym, holding in portfolio.items():
            price = market["prices"].get(sym, {}).get("price", holding["avg_cost"])
            value = price * holding["qty"]
            cost = holding["avg_cost"] * holding["qty"]
            total_value += value
            total_cost += cost
            pl = value - cost
            pl_txt = f"{'🟢 +' if pl >= 0 else '🔴 '}{pl:,.0f}"
            emoji = sym_names.get(sym, {}).get("emoji", "📈")
            lines.append(
                f"{emoji} **{sym}** — {holding['qty']} سهم\n"
                f"└ متوسط الشراء: `{holding['avg_cost']:,.2f}` | السعر الحالي: `{price:,.2f}` | {pl_txt}"
            )

        total_pl = total_value - total_cost
        embed = base_embed(f"💼 محفظة {ctx.author.display_name}")
        embed.description = "\n\n".join(lines)
        embed.add_field(name="📊 قيمة المحفظة", value=currency(int(total_value)), inline=True)
        embed.add_field(name="💸 التكلفة", value=currency(int(total_cost)), inline=True)
        embed.add_field(name="📈 الربح/الخسارة", value=f"{'🟢 +' if total_pl >= 0 else '🔴 '}{total_pl:,.0f}", inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stocks(bot))
