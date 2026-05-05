# ──────────────────────────────────────────────────────────────────────────────
# cogs/voice_xp.py
#
# Tracks voice channel activity and awards XP every 10 minutes.
#
# Rules:
#   • User must be in a VC with at least 2 non-bot members to earn XP
#   • +10 XP per 10-minute tick
#   • Uses voice_sessions table to persist join timestamps
#   • Level-up notifications posted in the VC's text counterpart (if any)
#     or the guild's system channel
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord.ext import commands, tasks as ext_tasks
import time

from database.db import get_db
from cogs.xp import award_xp_raw

VOICE_XP_AMOUNT  = 10   # XP per tick
VOICE_XP_MINUTES = 10   # minutes between ticks


class VoiceXP(commands.Cog):
    """Award XP for active voice channel participation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_xp_tick.start()

    def cog_unload(self):
        self.voice_xp_tick.cancel()

    # ── Track joins / leaves ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after:  discord.VoiceState,
    ):
        if member.bot:
            return

        uid = str(member.id)
        gid = str(member.guild.id)

        # User joined a channel
        if after.channel and (before.channel is None or before.channel.id != after.channel.id):
            async with get_db() as db:
                await db.execute(
                    """
                    INSERT INTO voice_sessions (user_id, guild_id, channel_id, join_time)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, guild_id) DO UPDATE
                        SET channel_id = $3, join_time = $4
                    """,
                    uid, gid, str(after.channel.id), time.time(),
                )
            print(f'[VOICE XP] {member} joined VC {after.channel.name}')

        # User left / moved away
        if before.channel and (after.channel is None or after.channel.id != before.channel.id):
            async with get_db() as db:
                await db.execute(
                    'DELETE FROM voice_sessions WHERE user_id = $1 AND guild_id = $2',
                    uid, gid,
                )

    # ── 10-minute XP tick ────────────────────────────────────────────────────

    @ext_tasks.loop(minutes=VOICE_XP_MINUTES)
    async def voice_xp_tick(self):
        try:
            async with get_db() as db:
                rows = await db.fetch('SELECT user_id, guild_id, channel_id FROM voice_sessions')
            sessions = [dict(r) for r in rows]
        except Exception as e:
            print(f'[VOICE XP] DB error: {e}')
            return

        for session in sessions:
            uid  = session['user_id']
            gid  = session['guild_id']
            chid = int(session['channel_id'])

            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue

            channel = guild.get_channel(chid)
            if not isinstance(channel, discord.VoiceChannel):
                continue

            # At least 2 non-bot members required
            active = [m for m in channel.members if not m.bot]
            if len(active) < 2:
                continue

            result = await award_xp_raw(uid, gid, VOICE_XP_AMOUNT)
            print(f'[VOICE XP] +{VOICE_XP_AMOUNT} XP → {uid} (total {result["xp"]})')

            if result['leveled_up']:
                await self._notify_level_up(guild, uid, result['level'])

    @voice_xp_tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()

    # ── Level-up notification ─────────────────────────────────────────────────

    async def _notify_level_up(self, guild: discord.Guild, user_id: str, level: int):
        member = guild.get_member(int(user_id))
        name   = member.display_name if member else f'<@{user_id}>'
        msg    = f'🎙️ {name} just hit **Level {level}** from chatting in voice! Keep talking! ⚡'

        target = guild.system_channel or next(
            (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
            None,
        )
        if target:
            try:
                await target.send(msg)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceXP(bot))
