"""
gambling.py
------------
أوامر المقامرة: سلوتس، كوين فليب، بلاك جاك.
"""

import random
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.data_manager import get_user, add_wallet, load_settings
from bot.utils.embeds import base_embed, success_embed, error_embed, currency

SLOT_EMOJIS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]


def check_gambling_enabled():
    async def predicate(ctx):
        settings = load_settings()["gambling"]
        if not settings.get("gambling_enabled", True):
            await ctx.send(embed=error_embed("مغلق", "نظام المقامرة موقوف حاليًا من الإدارة."))
            return False
        return True
    return commands.check(predicate)


class BlackjackView(discord.ui.View):
    def __init__(self, ctx, bet: int, max_wallet: int):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.bet = bet
        self.max_wallet = max_wallet
        self.deck = self._new_deck()
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.finished = False

    def _new_deck(self):
        suits = ["♠️", "♥️", "♦️", "♣️"]
        ranks = list(range(2, 11)) + ["J", "Q", "K", "A"]
        deck = [(r, s) for s in suits for r in ranks]
        random.shuffle(deck)
        return deck

    @staticmethod
    def hand_value(hand):
        value = 0
        aces = 0
        for rank, _ in hand:
            if rank == "A":
                value += 11
                aces += 1
            elif rank in ("J", "Q", "K"):
                value += 10
            else:
                value += rank
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    @staticmethod
    def hand_str(hand):
        return " ".join(f"{r}{s}" for r, s in hand)

    def build_embed(self, reveal_dealer=False, result_text=None):
        embed = base_embed("🃏 بلاك جاك")
        embed.add_field(
            name=f"يدك ({self.hand_value(self.player)})",
            value=self.hand_str(self.player),
            inline=False
        )
        if reveal_dealer:
            embed.add_field(
                name=f"يد الديلر ({self.hand_value(self.dealer)})",
                value=self.hand_str(self.dealer),
                inline=False
            )
        else:
            embed.add_field(
                name="يد الديلر",
                value=f"{self.hand_str([self.dealer[0]])} 🎴",
                inline=False
            )
        embed.add_field(name="الرهان", value=currency(self.bet), inline=False)
        if result_text:
            embed.description = result_text
        return embed

    async def end_game(self, interaction, outcome: str):
        self.finished = True
        for child in self.children:
            child.disabled = True

        if outcome == "win":
            add_wallet(self.ctx.author.id, self.bet, self.max_wallet)
            text = f"🎉 فزت! ربحت {currency(self.bet)}"
        elif outcome == "push":
            text = "🤝 تعادل! رجع لك رهانك."
        elif outcome == "blackjack":
            win_amount = int(self.bet * 1.5)
            add_wallet(self.ctx.author.id, self.bet + win_amount, self.max_wallet)
            text = f"🂡 بلاك جاك! ربحت {currency(win_amount)}"
        else:
            text = f"💥 خسرت {currency(self.bet)}"

        embed = self.build_embed(reveal_dealer=True, result_text=text)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="اسحب (Hit)", style=discord.ButtonStyle.primary, emoji="🎴")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("هذي مو لعبتك!", ephemeral=True)
            return
        self.player.append(self.deck.pop())
        if self.hand_value(self.player) > 21:
            await self.end_game(interaction, "lose")
            return
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="وقف (Stand)", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("هذي مو لعبتك!", ephemeral=True)
            return
        while self.hand_value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

        player_val = self.hand_value(self.player)
        dealer_val = self.hand_value(self.dealer)

        if dealer_val > 21 or player_val > dealer_val:
            await self.end_game(interaction, "win")
        elif player_val == dealer_val:
            await self.end_game(interaction, "push")
        else:
            await self.end_game(interaction, "lose")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class Gambling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------------------------------------------------------------- سلوتس
    @commands.hybrid_command(name="slots", aliases=["سلوتس"], description="جرب حظك بالسلوتس")
    @app_commands.describe(bet="مبلغ الرهان")
    @check_gambling_enabled()
    async def slots(self, ctx: commands.Context, bet: int):
        settings = load_settings()
        g = settings["gambling"]
        e = settings["economy"]

        if bet < g["slots_min_bet"] or bet > g["slots_max_bet"]:
            await ctx.send(embed=error_embed(
                "رهان غير صالح",
                f"الرهان لازم يكون بين {currency(g['slots_min_bet'])} و {currency(g['slots_max_bet'])}"
            ))
            return

        user = get_user(ctx.author.id, e["starting_balance"])
        if user["wallet"] < bet:
            await ctx.send(embed=error_embed("رصيد غير كافي", "ما عندك فلوس كافية لهذا الرهان."))
            return

        add_wallet(ctx.author.id, -bet, e["max_wallet"])

        result = [random.choice(SLOT_EMOJIS) for _ in range(3)]
        display = " | ".join(result)

        if result[0] == result[1] == result[2]:
            if result[0] == "7️⃣":
                winnings = bet * g["slots_jackpot_multiplier"]
                title = "💎 جاكبوت! 💎"
            else:
                winnings = bet * g["slots_win_multiplier"]
                title = "🎉 فوز! 🎉"
            add_wallet(ctx.author.id, winnings, e["max_wallet"])
            embed = success_embed(title, f"[ {display} ]\nربحت {currency(winnings)}")
        elif result[0] == result[1] or result[1] == result[2]:
            winnings = int(bet * 1.2)
            add_wallet(ctx.author.id, winnings, e["max_wallet"])
            embed = success_embed("زوج! 🎊", f"[ {display} ]\nربحت {currency(winnings)}")
        else:
            embed = error_embed("خسرت 😢", f"[ {display} ]\nخسرت {currency(bet)}")

        await ctx.send(embed=embed)

    # ------------------------------------------------------------- كوينفليب
    @commands.hybrid_command(name="coinflip", aliases=["cf", "عملة"], description="راهن على وجه العملة")
    @app_commands.describe(bet="مبلغ الرهان", choice="وجه ولا كتابة")
    @app_commands.choices(choice=[
        app_commands.Choice(name="وجه", value="heads"),
        app_commands.Choice(name="كتابة", value="tails"),
    ])
    @check_gambling_enabled()
    async def coinflip(self, ctx: commands.Context, bet: int, choice: str):
        settings = load_settings()
        g = settings["gambling"]
        e = settings["economy"]

        if bet < g["coinflip_min_bet"] or bet > g["coinflip_max_bet"]:
            await ctx.send(embed=error_embed(
                "رهان غير صالح",
                f"الرهان لازم يكون بين {currency(g['coinflip_min_bet'])} و {currency(g['coinflip_max_bet'])}"
            ))
            return

        user = get_user(ctx.author.id, e["starting_balance"])
        if user["wallet"] < bet:
            await ctx.send(embed=error_embed("رصيد غير كافي", "ما عندك فلوس كافية لهذا الرهان."))
            return

        choice = choice.lower()
        result = random.choice(["heads", "tails"])
        add_wallet(ctx.author.id, -bet, e["max_wallet"])

        result_ar = "وجه 🪙" if result == "heads" else "كتابة 🎯"

        if choice == result:
            winnings = bet * 2
            add_wallet(ctx.author.id, winnings, e["max_wallet"])
            embed = success_embed("ربحت!", f"النتيجة: {result_ar}\nربحت {currency(winnings)}")
        else:
            embed = error_embed("خسرت", f"النتيجة: {result_ar}\nخسرت {currency(bet)}")

        await ctx.send(embed=embed)

    # -------------------------------------------------------------- بلاك جاك
    @commands.hybrid_command(name="blackjack", aliases=["bj", "بلاك"], description="العب بلاك جاك ضد الديلر")
    @app_commands.describe(bet="مبلغ الرهان")
    @check_gambling_enabled()
    async def blackjack(self, ctx: commands.Context, bet: int):
        settings = load_settings()
        g = settings["gambling"]
        e = settings["economy"]

        if bet < g["blackjack_min_bet"] or bet > g["blackjack_max_bet"]:
            await ctx.send(embed=error_embed(
                "رهان غير صالح",
                f"الرهان لازم يكون بين {currency(g['blackjack_min_bet'])} و {currency(g['blackjack_max_bet'])}"
            ))
            return

        user = get_user(ctx.author.id, e["starting_balance"])
        if user["wallet"] < bet:
            await ctx.send(embed=error_embed("رصيد غير كافي", "ما عندك فلوس كافية لهذا الرهان."))
            return

        add_wallet(ctx.author.id, -bet, e["max_wallet"])

        view = BlackjackView(ctx, bet, e["max_wallet"])

        # بلاك جاك طبيعي (21 من أول ورقتين) يربح فورًا
        if view.hand_value(view.player) == 21:
            for child in view.children:
                child.disabled = True
            winnings = int(bet * 1.5)
            add_wallet(ctx.author.id, bet + winnings, e["max_wallet"])
            embed = view.build_embed(reveal_dealer=True, result_text=f"🂡 بلاك جاك! ربحت {currency(winnings)}")
            view.finished = True
            await ctx.send(embed=embed, view=view)
            view.stop()
            return

        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Gambling(bot))
