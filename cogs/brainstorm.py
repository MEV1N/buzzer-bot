# ──────────────────────────────────────────────────────────────────────────────
# cogs/brainstorm.py
#
# Daily brainstorming hub:
#   • Posts one prompt embed to BRAINSTORM_CHANNEL_ID at 09:00 UTC daily
#   • Auto-creates a thread on that message
#   • Awards +10 XP to users who reply in the thread (60 s cooldown)
#   • Stores the post in brainstorm_posts table
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord.ext import commands, tasks as ext_tasks
import random
import time
import os
from datetime import datetime, timezone, time as dtime

from database.db import get_db
from cogs.xp import award_xp_raw
from utils.embeds import COLORS

BRAINSTORM_XP       = 10
BRAINSTORM_COOLDOWN = 60   # seconds between XP grants in thread

PROMPTS = [
    "What's one thing you'd automate if you could? 🤖",
    "If you could add one feature to Discord, what would it be? 💬",
    "What's a skill you'd teach everyone here if you could? 🎓",
    "What's the most underrated productivity hack you know? ⚡",
    "If this server had a mascot, what would it be? 🦊",
    "What's the best way to stay focused during long work sessions? 🎯",
    "If you could solve one problem in your field overnight, what would it be? 🔬",
    "What tool or app has changed how you work the most? 🛠️",
    "What's a random idea you've had that you never executed on? 💡",
    "If you had 1 uninterrupted hour of focus time, what would you work on? ⏱️",
    "What's the most creative solution you've seen to a boring problem? 🎨",
    "Hot take: what's overrated in your field right now? 🌶️",
    "What's something you've been meaning to learn but haven't started? 📚",
    "If this team had a superpower, what should it be? 🦸",
    "What would make meetings 10x better? 🗓️",
    "What's a mistake that turned into a lesson you're glad you learned? 🔄",
    "What does your ideal work environment look like? 🏡",
    "If you could swap roles with someone for a day, who and why? 🔁",
    "What's a trend you think is overhyped right now? 📈",
    "What's one thing you're proud of accomplishing recently? 🏆",
]


class Brainstorm(commands.Cog):
    """Daily brainstorming prompt with auto-thread and XP rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._xp_cd: dict[str, float] = {}   # f"{uid}:{thread_id}" → last xp timestamp
        self._active_thread_ids: set[int] = set()  # thread IDs from today's post
        self.daily_brainstorm.start()

    def cog_unload(self):
        self.daily_brainstorm.cancel()

    # ── Daily post ────────────────────────────────────────────────────────────

    @ext_tasks.loop(time=dtime(hour=9, tzinfo=timezone.utc))
    async def daily_brainstorm(self):
        ch_id = int(os.getenv('BRAINSTORM_CHANNEL_ID', '0'))
        if not ch_id:
            print('[BRAINSTORM] BRAINSTORM_CHANNEL_ID not set — skipping.')
            return

        channel = self.bot.get_channel(ch_id)
        if not isinstance(channel, discord.TextChannel):
            print(f'[BRAINSTORM] Channel {ch_id} not found or not a text channel.')
            return

        prompt  = random.choice(PROMPTS)
        today   = datetime.now(timezone.utc).strftime('%B %d, %Y')

        embed = discord.Embed(
            title='🧠  Daily Brainstorm',
            description=f'**{prompt}**\n\n'
                        '_Drop your thoughts in the thread below. '
                        'Best ideas earn bragging rights (and +10 XP per reply). 👇_',
            color=COLORS['xp'],
        )
        embed.set_footer(text=f'⚡ Buzzer Bot  •  {today}')

        try:
            msg = await channel.send(embed=embed)
            thread = await msg.create_thread(
                name=f"Brainstorm — {today}",
                auto_archive_duration=1440,  # 24 hours
            )
            self._active_thread_ids.add(thread.id)

            # Persist to DB
            async with get_db() as db:
                await db.execute(
                    'INSERT INTO brainstorm_posts (guild_id, message_id, channel_id, posted_date) '
                    'VALUES ($1, $2, $3, $4)',
                    str(channel.guild.id), str(msg.id), str(ch_id),
                    datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                )
            print(f'[BRAINSTORM] Posted daily prompt in #{channel.name}, thread: {thread.name}')
        except discord.HTTPException as e:
            print(f'[BRAINSTORM] Failed to post: {e}')

    @daily_brainstorm.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    # ── Award XP for thread replies ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Only fire in brainstorm threads
        if not isinstance(message.channel, discord.Thread):
            return
        if message.channel.id not in self._active_thread_ids:
            # Recover thread IDs from DB on restart
            await self._load_active_threads(message.guild)
            if message.channel.id not in self._active_thread_ids:
                return

        uid = str(message.author.id)
        gid = str(message.guild.id)
        key = f'{uid}:{message.channel.id}'
        now = time.time()

        if now - self._xp_cd.get(key, 0) < BRAINSTORM_COOLDOWN:
            return

        result = await award_xp_raw(uid, gid, BRAINSTORM_XP)
        self._xp_cd[key] = now

        if result['leveled_up']:
            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} just levelled up to **Level {result['level']}** "
                    f"from brainstorming! That's the good stuff. ⚡",
                    delete_after=15,
                )
            except discord.HTTPException:
                pass

    async def _load_active_threads(self, guild: discord.Guild):
        """Load today's brainstorm thread IDs from DB (handles restarts)."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        try:
            async with get_db() as db:
                rows = await db.fetch(
                    'SELECT message_id, channel_id FROM brainstorm_posts '
                    'WHERE guild_id = $1 AND posted_date = $2',
                    str(guild.id), today,
                )
            for row in rows:
                ch = guild.get_channel(int(row['channel_id']))
                if ch:
                    msg_id = int(row['message_id'])
                    # Find thread by parent message
                    for thread in ch.threads:
                        if thread.parent_id == ch.id:
                            self._active_thread_ids.add(thread.id)
        except Exception as e:
            print(f'[BRAINSTORM] Thread load error: {e}')


async def setup(bot: commands.Bot):
    await bot.add_cog(Brainstorm(bot))
