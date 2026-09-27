"""Vixen Discord EDR Control Center: real Discord moderation/admin operations.
All commands are hybrid commands, so every command is available as /slash and prefix.
"""
import asyncio
import io
import math
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands


def need(permission: str):
    async def predicate(ctx: commands.Context):
        from bot.utils import ranks
        if getattr(ctx, "dashboard_session", None) is not None and ctx.dashboard_session.get("virtual"):
            if permission in ranks.DEFAULT_PERMISSIONS.get(ctx.dashboard_session.get("rank", ""), []):
                return True
        if ranks.is_owner(ctx.author.id) or ranks.has_permission(ctx.author.id, permission):
            return True
        raise commands.CheckFailure(f"Missing Vixen permission: {permission}")
    return commands.check(predicate)


class Control(commands.Cog):
    def __init__(self, bot): self.bot = bot

    def _latency_ms(self) -> int:
        """Return a stable value while the Gateway is still connecting."""
        latency = self.bot.latency
        return round(latency * 1000) if math.isfinite(latency) else 0

    async def _reply(self, ctx, text, ephemeral=False):
        if ctx.interaction:
            await ctx.interaction.response.send_message(text, ephemeral=ephemeral)
        else:
            await ctx.send(text)

    # ---------------- server ----------------
    @commands.hybrid_group(name="server", invoke_without_command=True, description="إدارة السيرفر")
    async def server(self, ctx): await self._reply(ctx, "استخدم /server ثم اختر العملية.")

    @server.command(name="lockdown", description="قفل السيرفر دفعة واحدة مع حفظ الحالة")
    @need("manage_server")
    async def server_lockdown(self, ctx): await self._lockdown(ctx.guild, True, ctx)

    @server.command(name="unlockdown", description="استعادة حالة السيرفر المحفوظة")
    @need("manage_server")
    async def server_unlockdown(self, ctx): await self._lockdown(ctx.guild, False, ctx)

    @server.command(name="name", description="تغيير اسم السيرفر")
    @app_commands.describe(name="الاسم الجديد")
    @need("manage_server")
    async def server_name(self, ctx, name: str): await ctx.guild.edit(name=name); await self._reply(ctx, "✅ تم تغيير اسم السيرفر.")

    @server.command(name="icon", description="تغيير أيقونة السيرفر من رابط")
    @app_commands.describe(url="رابط الصورة")
    @need("manage_server")
    async def server_icon(self, ctx, url: str):
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data=await r.read()
        await ctx.guild.edit(icon=data); await self._reply(ctx, "✅ تم تحديث الأيقونة.")

    @server.command(name="verification", description="تغيير مستوى التحقق")
    @app_commands.describe(level="0 none, 1 low, 2 medium, 3 high, 4 highest")
    @need("manage_server")
    async def server_verification(self, ctx, level: int):
        await ctx.guild.edit(verification_level=discord.VerificationLevel(max(0,min(4,level))))
        await self._reply(ctx, "✅ تم تحديث مستوى التحقق.")

    @server.command(name="slowmode", description="تغيير slowmode لكل القنوات النصية")
    @app_commands.describe(seconds="الثواني 0-21600")
    @need("manage_server")
    async def server_slowmode(self, ctx, seconds: int):
        seconds=max(0,min(21600,seconds)); changed=0
        for c in ctx.guild.text_channels:
            try: await c.edit(slowmode_delay=seconds); changed+=1
            except discord.HTTPException: pass
            await asyncio.sleep(.15)
        await self._reply(ctx,f"✅ تم تحديث {changed} قناة.")

    @server.command(name="systemchannel", description="تعيين قناة النظام")
    @app_commands.describe(channel="القناة")
    @need("manage_server")
    async def server_systemchannel(self, ctx, channel: discord.TextChannel): await ctx.guild.edit(system_channel=channel); await self._reply(ctx,"✅ تم.")

    @server.command(name="features", description="عرض إعدادات السيرفر الأساسية")
    @need("view_stats")
    async def server_features(self, ctx): await self._reply(ctx,f"📊 {ctx.guild.name}\nMembers: {ctx.guild.member_count}\nChannels: {len(ctx.guild.channels)}\nRoles: {len(ctx.guild.roles)}")

    @server.command(name="description", description="تغيير وصف السيرفر")
    @app_commands.describe(description="الوصف")
    @need("manage_server")
    async def server_description(self, ctx, description: str): await ctx.guild.edit(description=description[:1000]); await self._reply(ctx,"✅ تم.")

    @server.command(name="banner", description="تغيير بانر السيرفر من رابط")
    @app_commands.describe(url="رابط الصورة")
    @need("manage_server")
    async def server_banner(self, ctx, url: str):
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r: data=await r.read()
        await ctx.guild.edit(banner=data); await self._reply(ctx,"✅ تم.")

    # ---------------- channel ----------------
    @commands.hybrid_group(name="channel", invoke_without_command=True, description="إدارة القنوات")
    async def channel(self, ctx): await self._reply(ctx,"استخدم /channel ثم اختر العملية.")

    @channel.command(name="create", description="إنشاء قناة نصية")
    @app_commands.describe(name="اسم القناة", category="التصنيف اختياري")
    @need("manage_channels")
    async def channel_create(self, ctx, name: str, category: Optional[discord.CategoryChannel]=None): c=await ctx.guild.create_text_channel(name,category=category); await self._reply(ctx,f"✅ <#{c.id}>")

    @channel.command(name="delete", description="حذف قناة")
    @app_commands.describe(channel="القناة")
    @need("manage_channels")
    async def channel_delete(self, ctx, channel: discord.TextChannel): await channel.delete(reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"✅ تم حذف القناة.")

    @channel.command(name="rename", description="إعادة تسمية قناة")
    @app_commands.describe(channel="القناة", name="الاسم")
    @need("manage_channels")
    async def channel_rename(self, ctx, channel: discord.TextChannel, name: str): await channel.edit(name=name); await self._reply(ctx,"✅ تم.")

    @channel.command(name="topic", description="تغيير موضوع القناة")
    @app_commands.describe(channel="القناة", topic="الموضوع")
    @need("manage_channels")
    async def channel_topic(self, ctx, channel: discord.TextChannel, topic: str): await channel.edit(topic=topic[:1024]); await self._reply(ctx,"✅ تم.")

    @channel.command(name="slowmode", description="تغيير slowmode لقناة")
    @app_commands.describe(channel="القناة", seconds="الثواني")
    @need("manage_channels")
    async def channel_slowmode(self, ctx, channel: discord.TextChannel, seconds: int): await channel.edit(slowmode_delay=max(0,min(21600,seconds))); await self._reply(ctx,"✅ تم.")

    @channel.command(name="clone", description="استنساخ قناة")
    @app_commands.describe(channel="القناة")
    @need("manage_channels")
    async def channel_clone(self, ctx, channel: discord.TextChannel): c=await channel.clone(reason=f"Vixen by {ctx.author}"); await self._reply(ctx,f"✅ <#{c.id}>")

    @channel.command(name="purge", description="حذف عدد من الرسائل")
    @app_commands.describe(channel="القناة", amount="1-100")
    @need("manage_messages")
    async def channel_purge(self, ctx, channel: discord.TextChannel, amount: int): n=await channel.purge(limit=max(1,min(100,amount))); await self._reply(ctx,f"🧹 حُذفت {len(n)} رسالة.",True)

    @channel.command(name="lock", description="قفل الكتابة")
    @app_commands.describe(channel="القناة")
    @need("manage_channels")
    async def channel_lock(self, ctx, channel: discord.TextChannel): await channel.set_permissions(ctx.guild.default_role, send_messages=False); await self._reply(ctx,"🔒 تم القفل.")

    @channel.command(name="unlock", description="فتح الكتابة")
    @app_commands.describe(channel="القناة")
    @need("manage_channels")
    async def channel_unlock(self, ctx, channel: discord.TextChannel): await channel.set_permissions(ctx.guild.default_role, send_messages=None); await self._reply(ctx,"🔓 تم الفتح.")

    @channel.command(name="category", description="نقل قناة إلى تصنيف")
    @app_commands.describe(channel="القناة", category="التصنيف")
    @need("manage_channels")
    async def channel_category(self, ctx, channel: discord.TextChannel, category: discord.CategoryChannel): await channel.edit(category=category); await self._reply(ctx,"✅ تم.")

    # ---------------- member ----------------
    @commands.hybrid_group(name="member", invoke_without_command=True, description="إدارة الأعضاء")
    async def member(self, ctx): await self._reply(ctx,"استخدم /member ثم اختر العملية.")

    @member.command(name="timeout", description="تقييد عضو")
    @app_commands.describe(member="العضو", minutes="الدقائق")
    @need("moderate_members")
    async def member_timeout(self, ctx, member: discord.Member, minutes: int): await member.timeout(discord.utils.utcnow()+__import__('datetime').timedelta(minutes=max(1,min(40320,minutes))),reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"⏳ تم.")

    @member.command(name="untimeout", description="إزالة التقييد")
    @need("moderate_members")
    async def member_untimeout(self, ctx, member: discord.Member): await member.timeout(None,reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"✅ تم.")

    @member.command(name="kick", description="طرد عضو")
    @need("kick_members")
    async def member_kick(self, ctx, member: discord.Member, reason: str="Vixen moderation"): await member.kick(reason=reason); await self._reply(ctx,"👢 تم الطرد.")

    @member.command(name="ban", description="حظر عضو")
    @need("ban_members")
    async def member_ban(self, ctx, member: discord.Member, reason: str="Vixen moderation"): await ctx.guild.ban(member,reason=reason,delete_message_seconds=0); await self._reply(ctx,"🔨 تم الحظر.")

    @member.command(name="unban", description="فك حظر بواسطة ID")
    @app_commands.describe(user_id="Discord user ID")
    @need("ban_members")
    async def member_unban(self, ctx, user_id: str): await ctx.guild.unban(discord.Object(id=int(user_id))); await self._reply(ctx,"✅ تم فك الحظر.")

    @member.command(name="deafen", description="كتم صوت العضو")
    @need("deafen_members")
    async def member_deafen(self, ctx, member: discord.Member): await member.edit(deafen=True); await self._reply(ctx,"🔇 تم.")

    @member.command(name="undeafen", description="إلغاء كتم الصوت")
    @need("deafen_members")
    async def member_undeafen(self, ctx, member: discord.Member): await member.edit(deafen=False); await self._reply(ctx,"🔊 تم.")

    @member.command(name="mute", description="كتم عضو في الصوت")
    @need("mute_members")
    async def member_mute(self, ctx, member: discord.Member): await member.edit(mute=True); await self._reply(ctx,"🔇 تم.")

    @member.command(name="unmute", description="إلغاء كتم الصوت")
    @need("mute_members")
    async def member_unmute(self, ctx, member: discord.Member): await member.edit(mute=False); await self._reply(ctx,"🔊 تم.")

    @member.command(name="move", description="نقل عضو صوتيًا")
    @app_commands.describe(member="العضو", channel="القناة الصوتية")
    @need("move_members")
    async def member_move(self, ctx, member: discord.Member, channel: discord.VoiceChannel): await member.move_to(channel); await self._reply(ctx,"✅ تم النقل.")

    @member.command(name="dm", description="إرسال DM لعضو")
    @app_commands.describe(member="العضو", message="الرسالة")
    @need("dm_members")
    async def member_dm(self, ctx, member: discord.Member, message: str): await member.send(message); await self._reply(ctx,"✉️ تم الإرسال.",True)

    @member.command(name="disconnect", description="فصل عضو من القناة الصوتية")
    @need("move_members")
    async def member_disconnect(self, ctx, member: discord.Member): await member.move_to(None); await self._reply(ctx,"✅ تم الفصل.")

    @member.command(name="avatar", description="إرسال رابط صورة عضو")
    @need("view_users")
    async def member_avatar(self, ctx, member: discord.Member): await self._reply(ctx,member.display_avatar.url)

    # ---------------- role ----------------
    @commands.hybrid_group(name="role", invoke_without_command=True, description="إدارة الرتب")
    async def role(self, ctx): await self._reply(ctx,"استخدم /role ثم اختر العملية.")

    @role.command(name="create", description="إنشاء رتبة")
    @app_commands.describe(name="اسم الرتبة")
    @need("manage_roles")
    async def role_create(self, ctx, name: str): r=await ctx.guild.create_role(name=name,reason=f"Vixen by {ctx.author}"); await self._reply(ctx,f"✅ {r.mention}")

    @role.command(name="delete", description="حذف رتبة")
    @app_commands.describe(role="الرتبة")
    @need("manage_roles")
    async def role_delete(self, ctx, role: discord.Role):
        if role >= ctx.guild.me.top_role: return await self._reply(ctx,"❌ الرتبة أعلى من رتبة البوت.",True)
        await role.delete(reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"✅ تم.")

    @role.command(name="add", description="إضافة رتبة لعضو")
    @need("manage_roles")
    async def role_add(self, ctx, member: discord.Member, role: discord.Role): await member.add_roles(role,reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"✅ تم.")

    @role.command(name="remove", description="إزالة رتبة من عضو")
    @need("manage_roles")
    async def role_remove(self, ctx, member: discord.Member, role: discord.Role): await member.remove_roles(role,reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"✅ تم.")

    @role.command(name="rename", description="إعادة تسمية رتبة")
    @need("manage_roles")
    async def role_rename(self, ctx, role: discord.Role, name: str): await role.edit(name=name); await self._reply(ctx,"✅ تم.")

    @role.command(name="list", description="عرض الرتب")
    @need("view_stats")
    async def role_list(self, ctx): await self._reply(ctx,"\n".join(f"• {r.name} ({r.id})" for r in ctx.guild.roles[-30:]))

    @role.command(name="color", description="تغيير لون رتبة")
    @app_commands.describe(role="الرتبة", hex_color="مثل #7c5cff")
    @need("manage_roles")
    async def role_color(self, ctx, role: discord.Role, hex_color: str): await role.edit(color=discord.Color(int(hex_color.strip().lstrip("#"),16))); await self._reply(ctx,"✅ تم.")

    @role.command(name="hoist", description="إظهار الرتبة منفصلة")
    @app_commands.describe(role="الرتبة", enabled="تشغيل")
    @need("manage_roles")
    async def role_hoist(self, ctx, role: discord.Role, enabled: bool): await role.edit(hoist=enabled); await self._reply(ctx,"✅ تم.")

    # ---------------- security ----------------
    @commands.hybrid_group(name="security", invoke_without_command=True, description="الأمان")
    async def security(self, ctx): await self._reply(ctx,"استخدم /security ثم اختر العملية.")

    @security.command(name="bans", description="قائمة المحظورين")
    @need("view_stats")
    async def security_bans(self, ctx):
        bans=[f"{e.user} ({e.user.id})" async for e in ctx.guild.bans(limit=None)]
        await self._reply(ctx,"🔨 المحظورون:\n"+("\n".join(bans) if bans else "لا يوجد"))

    @security.command(name="invites", description="قائمة الدعوات")
    @need("manage_server")
    async def security_invites(self, ctx):
        inv=await ctx.guild.invites(); await self._reply(ctx,"\n".join(f"{i.code} — {i.uses or 0} uses" for i in inv) or "لا توجد دعوات")

    @security.command(name="deleteinvite", description="حذف دعوة")
    @app_commands.describe(code="كود الدعوة")
    @need("manage_server")
    async def security_deleteinvite(self, ctx, code: str):
        inv=await ctx.guild.fetch_invite(code); await inv.delete(reason=f"Vixen by {ctx.author}"); await self._reply(ctx,"✅ تم.")

    @security.command(name="createinvite", description="إنشاء دعوة")
    @app_commands.describe(channel="القناة", max_uses="عدد الاستخدامات")
    @need("manage_server")
    async def security_createinvite(self, ctx, channel: discord.TextChannel, max_uses: int=0): inv=await channel.create_invite(max_uses=max(0,min(100,max_uses))); await self._reply(ctx,inv.url)

    @security.command(name="webhooks", description="عرض webhooks")
    @need("manage_server")
    async def security_webhooks(self, ctx):
        hooks=[]
        for c in ctx.guild.channels:
            if hasattr(c,'webhooks'):
                try: hooks += await c.webhooks()
                except discord.HTTPException: pass
        await self._reply(ctx,"\n".join(f"{h.name} — {h.id}" for h in hooks) or "لا توجد")

    @security.command(name="deletewebhooks", description="حذف كل webhooks")
    @need("manage_server")
    async def security_deletewebhooks(self, ctx):
        n=0
        for c in ctx.guild.channels:
            if hasattr(c,'webhooks'):
                try:
                    for h in await c.webhooks(): await h.delete(reason=f"Vixen by {ctx.author}"); n+=1
                except discord.HTTPException: pass
        await self._reply(ctx,f"✅ حذف {n} webhook.")

    @security.command(name="audit", description="آخر سجلات تدقيق Discord")
    @need("view_logs")
    async def security_audit(self, ctx):
        entries=[e async for e in ctx.guild.audit_logs(limit=15)]
        await self._reply(ctx,"\n".join(f"{e.action.name}: {e.user} ({e.target})" for e in entries) or "لا توجد سجلات")

    @security.command(name="automod", description="عرض قواعد AutoMod")
    @need("view_stats")
    async def security_automod(self, ctx):
        rules=await ctx.guild.fetch_automod_rules(); await self._reply(ctx,"\n".join(f"{r.name} — {r.id}" for r in rules) or "لا توجد قواعد AutoMod")

    # ---------------- utility ----------------
    @commands.hybrid_group(name="utility", invoke_without_command=True, description="أدوات الإدارة")
    async def utility(self, ctx): await self._reply(ctx,"استخدم /utility ثم اختر العملية.")

    @utility.command(name="ping", description="حالة البوت")
    async def utility_ping(self, ctx): await self._reply(ctx,f"🏓 {self._latency_ms()}ms")

    @utility.command(name="members", description="عدد الأعضاء")
    @need("view_stats")
    async def utility_members(self, ctx): await self._reply(ctx,f"👥 {ctx.guild.member_count}")

    @utility.command(name="emoji", description="إنشاء emoji من رابط")
    @app_commands.describe(name="الاسم", url="رابط الصورة")
    @need("manage_emojis")
    async def utility_emoji(self, ctx, name: str, url: str):
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r: data=await r.read()
        e=await ctx.guild.create_custom_emoji(name=name,image=data,reason=f"Vixen by {ctx.author}"); await self._reply(ctx,f"✅ {e}")

    @utility.command(name="sticker", description="عرض معلومات الملصقات")
    @need("view_stats")
    async def utility_sticker(self, ctx): await self._reply(ctx,"\n".join(f"{s.name} ({s.id})" for s in ctx.guild.stickers) or "لا توجد ملصقات")

    @utility.command(name="event", description="إنشاء Scheduled Event")
    @app_commands.describe(name="الاسم", start_iso="وقت البداية ISO 8601", description="الوصف")
    @need("manage_events")
    async def utility_event(self, ctx, name: str, start_iso: str, description: str=""):
        from datetime import datetime, timezone
        start=datetime.fromisoformat(start_iso.replace('Z','+00:00')).astimezone(timezone.utc)
        e=await ctx.guild.create_scheduled_event(name=name,start_time=start,end_time=start+__import__("datetime").timedelta(hours=1),entity_type=discord.EntityType.external,privacy_level=discord.PrivacyLevel.guild_only,location=ctx.guild.name,description=description)
        await self._reply(ctx,f"✅ تم إنشاء الحدث {e.name}.")

    @utility.command(name="events", description="عرض الأحداث")
    @need("view_stats")
    async def utility_events(self, ctx): ev=await ctx.guild.fetch_scheduled_events(); await self._reply(ctx,"\n".join(f"{e.name} — {e.id}" for e in ev) or "لا توجد أحداث")

    @utility.command(name="prune", description="إزالة أعضاء غير نشطين")
    @app_commands.describe(days="1-30")
    @need("kick_members")
    async def utility_prune(self, ctx, days: int=7):
        days=max(1,min(30,days))
        n=await ctx.guild.prune_members(days=days,dry=False,reason=f"Vixen prune by {ctx.author}")
        await self._reply(ctx,f"✅ تم تنفيذ Prune لمدة {days} يومًا. الأعضاء الذين أزيلوا: {n}")

    @utility.command(name="botinfo", description="معلومات البوت")
    async def utility_botinfo(self, ctx): await self._reply(ctx,f"Vixen EDR\nLatency: {self._latency_ms()}ms\nGuilds: {len(self.bot.guilds)}")

    @utility.command(name="say", description="إرسال رسالة من البوت إلى قناة")
    @app_commands.describe(channel="القناة", message="الرسالة")
    @need("manage_messages")
    async def utility_say(self, ctx, channel: discord.TextChannel, message: str): await channel.send(message[:2000]); await self._reply(ctx,"✅ تم الإرسال.",True)

    @utility.command(name="channelinfo", description="معلومات قناة")
    @app_commands.describe(channel="القناة")
    @need("view_stats")
    async def utility_channelinfo(self, ctx, channel: discord.TextChannel): await self._reply(ctx,f"#{channel.name}\nID: {channel.id}\nTopic: {channel.topic or '-'}\nSlowmode: {channel.slowmode_delay}s")

    @utility.command(name="roleinfo", description="معلومات رتبة")
    @app_commands.describe(role="الرتبة")
    @need("view_stats")
    async def utility_roleinfo(self, ctx, role: discord.Role): await self._reply(ctx,f"{role.name}\nID: {role.id}\nPosition: {role.position}\nMembers: {len(role.members)}")

    async def _lockdown(self, guild, lock, ctx):
        """قفل/فتح كل القنوات النصية بالتوازي (بدل واحدة تلو الأخرى) حتى لا
        يعلّق الطلب لثوانٍ طويلة على سيرفر فيه عدد كبير من القنوات.
        كل قناة تُحدَّث بمهلة زمنية مستقلة (10 ثوانٍ) — قناة بطيئة أو محظورة
        الوصول لن توقف بقية القنوات ولن تعلّق العملية كاملة."""
        from bot.utils.data_manager import load_settings, save_settings
        settings=load_settings(); store=settings.setdefault("lockdown_state",{})
        gid=str(guild.id)
        semaphore=asyncio.Semaphore(5)  # يحد التزامن حتى لا يصطدم بـ rate limit دفعة واحدة

        async def _apply(c, send_messages_value):
            async with semaphore:
                try:
                    ow=c.overwrites_for(guild.default_role)
                    prev=ow.send_messages
                    ow.send_messages=send_messages_value
                    await asyncio.wait_for(
                        c.set_permissions(guild.default_role,overwrite=ow,
                                           reason="Vixen Full Lockdown" if lock else "Vixen Unlockdown"),
                        timeout=10,
                    )
                    return str(c.id), prev, True
                except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError):
                    return str(c.id), None, False

        if lock:
            results = await asyncio.gather(*[_apply(c, False) for c in guild.text_channels])
            state={cid: {"send_messages": prev} for cid, prev, ok in results if ok}
            skipped = sum(1 for _, _, ok in results if not ok)
            store[gid]=state; save_settings(settings)
            msg = f"🔒 Full Lockdown اكتمل ({len(state)} قناة)."
            if skipped: msg += f" تم تخطي {skipped} قناة فشلت."
            await self._reply(ctx, msg)
        else:
            state=store.get(gid,{})
            channels=[c for c in guild.text_channels if str(c.id) in state]

            async def _restore(c):
                old=state.get(str(c.id))
                async with semaphore:
                    try:
                        ow=c.overwrites_for(guild.default_role)
                        ow.send_messages=old.get("send_messages")
                        await asyncio.wait_for(
                            c.set_permissions(guild.default_role,overwrite=ow,reason="Vixen Unlockdown"),
                            timeout=10,
                        )
                        return True
                    except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError):
                        return False

            results = await asyncio.gather(*[_restore(c) for c in channels])
            restored = sum(1 for ok in results if ok)
            skipped = len(results) - restored
            store.pop(gid,None); save_settings(settings)
            msg = f"🔓 Unlockdown اكتمل ({restored} قناة)."
            if skipped: msg += f" تم تخطي {skipped} قناة فشلت."
            await self._reply(ctx, msg)


async def setup(bot): await bot.add_cog(Control(bot))
