"""Atria Dawn integration: explicit AI chat plus optional moderation hooks."""
import os, aiohttp, discord, asyncio, json, datetime, time
from discord.ext import commands
from discord import app_commands
from bot.utils.data_manager import load_settings

BASE="https://api.atria-asi.ai/v1/chat/completions"
MODEL="Atria-Dawn-Preview"
AI_SEMAPHORE = asyncio.Semaphore(3)
AI_MIN_INTERVAL = 0.35
_last_ai_call = 0.0

async def atria_chat(messages, max_tokens=1200):
    global _last_ai_call
    key=os.getenv("ATRIA_API_KEY")
    if not key: raise RuntimeError("ATRIA_API_KEY غير مضبوط")
    payload={"model":MODEL,"messages":messages,"max_tokens":max_tokens}
    async with AI_SEMAPHORE:
        wait=max(0.0, AI_MIN_INTERVAL-(time.monotonic()-_last_ai_call))
        if wait: await asyncio.sleep(wait)
        timeout=aiohttp.ClientTimeout(total=45)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(BASE,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload) as r:
                data=await r.json(content_type=None)
                _last_ai_call=time.monotonic()
                if r.status>=400: raise RuntimeError(data.get("error",{}).get("message",f"Atria HTTP {r.status}"))
                content=((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                if not content: raise RuntimeError("Atria returned an empty response")
                return content

class Atria(commands.Cog):
    def __init__(self, bot): self.bot=bot

    @commands.hybrid_group(name="ai", invoke_without_command=True, description="Atria Dawn AI")
    async def ai(self, ctx): await ctx.send("استخدم /ai chat لبدء محادثة مع Atria Dawn.")

    @ai.command(name="chat", description="محادثة مباشرة مع Atria Dawn")
    @app_commands.describe(prompt="رسالتك")
    async def chat(self, ctx, prompt: str):
        await ctx.defer()
        try:
            answer=await atria_chat([{"role":"system","content":"You are Vixen Discord EDR assistant. Be concise, safe, and operational."},{"role":"user","content":prompt}])
            await ctx.send(answer[:1900])
        except Exception as e: await ctx.send(f"❌ Atria: {e}")

    @ai.command(name="moderate", description="فحص رسالة باستخدام Atria Dawn")
    @app_commands.describe(text="النص المراد فحصه")
    async def moderate(self, ctx, text: str):
        await ctx.defer(ephemeral=True)
        try:
            verdict=await atria_chat([{"role":"system","content":"You are a Discord safety moderator. Return JSON only with action one of allow, warn, timeout, ban and a short reason. Do not invent facts."},{"role":"user","content":text}],400)
            await ctx.send(verdict[:1900], ephemeral=True)
        except Exception as e: await ctx.send(f"❌ Atria: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        cfg=load_settings().get("atria",{})
        if not cfg.get("moderation_enabled",False): return
        # Full-message moderation is optional and configurable. A prefix allowlist remains available for low-cost mode.
        if cfg.get("moderation_mode", "all") == "prefix":
            prefixes=tuple(cfg.get("moderation_prefixes", ["[mod]","!modcheck"]))
            if not message.content.lower().startswith(tuple(p.lower() for p in prefixes)): return
        if not message.content.strip(): return
        # لا نرسل الرسائل الضخمة أو رسائل الإدارة الداخلية إلى النموذج.
        content=message.content[:2000]
        try:
            verdict=await atria_chat([{"role":"system","content":"Moderate this Discord message. Reply JSON only: {\"action\":\"allow\"|\"warn\"|\"timeout\"|\"ban\",\"reason\":\"short\"}. Never ban/timeout based on guesses; use allow when evidence is insufficient."},{"role":"user","content":content}],400)
            compact=verdict.strip().removeprefix("```json").removesuffix("```").strip()
            try: result=json.loads(compact)
            except Exception: result={"action":"allow","reason":"invalid AI response"}
            action=str(result.get("action","allow")).lower()
            reason=str(result.get("reason","Atria moderation"))[:500]
            if action not in {"allow","warn","timeout","ban"}: action="allow"
            if action=="timeout" and message.author.id != message.guild.owner_id:
                await message.author.timeout(discord.utils.utcnow()+datetime.timedelta(minutes=max(1,min(60,int(cfg.get("timeout_minutes",10))))),reason=reason)
            elif action=="ban" and message.author.id != message.guild.owner_id:
                await message.guild.ban(message.author,reason=reason,delete_message_seconds=0)
            elif action=="warn":
                await message.channel.send(f"⚠️ {message.author.mention}: {reason}",delete_after=8)
        except (discord.Forbidden, discord.HTTPException):
            return
        except Exception:
            return

async def setup(bot): await bot.add_cog(Atria(bot))
