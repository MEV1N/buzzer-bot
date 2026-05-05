# ──────────────────────────────────────────────────────────────────────────────
# cogs/xp.py
# XP & Leveling system.
#
# XP gain: 5–15 per message, 30-second cooldown.
# Level formula: level = floor(0.1 * sqrt(xp))
# Slash commands: /bzrank, /bzleaderboard
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands
import math
import random
import os

from database.db import get_db
from utils.embeds import rank_embed, leaderboard_embed, success_embed, error_embed


XP_MIN = 5
XP_MAX = 15


def calculate_level(xp: int) -> int:
    """level = floor(0.1 * sqrt(xp))"""
    return math.floor(0.1 * math.sqrt(xp))


async def _ensure_user(db, user_id: str, guild_id: str):
    """Creates a user row if it doesn't exist; returns the row."""
    owner_id = os.getenv('OWNER_ID', '')
    role = 'owner' if user_id == owner_id else 'member'
    await db.execute(
        """
        INSERT INTO users (user_id, guild_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, guild_id) DO NOTHING
        """,
        user_id, guild_id, role,
    )
    return await db.fetchrow(
        'SELECT * FROM users WHERE user_id = $1 AND guild_id = $2',
        user_id, guild_id,
    )


class XP(commands.Cog):
    """XP and leveling system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Message XP listener ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMs, bots, system messages
        if not message.guild or message.author.bot or message.is_system():
            return

        uid = str(message.author.id)
        gid = str(message.guild.id)

        async with get_db() as db:
            user = await _ensure_user(db, uid, gid)

            gain      = random.randint(XP_MIN, XP_MAX)
            old_level = user['level']
            new_xp    = user['xp'] + gain
            new_level = calculate_level(new_xp)

            await db.execute(
                """
                UPDATE users
                SET xp = $1, level = $2
                WHERE user_id = $3 AND guild_id = $4
                """,
                new_xp, new_level, uid, gid,
            )

        # Level-up notification
        if new_level > old_level:
            embed = success_embed(
                '🎉  Level Up!',
                f'{message.author.mention} just reached **Level {new_level}**! Keep it up! ⚡',
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            try:
                await message.channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ── /bzrank ───────────────────────────────────────────────────────────────

    @app_commands.command(name='bzrank', description="Check your XP rank (or another user's).")
    @app_commands.describe(user='The user to check (defaults to you)')
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer()

        target = user or interaction.user
        if target.bot:
            return await interaction.followup.send(
                embed=error_embed('Bots do not have XP.'), ephemeral=True
            )

        uid = str(target.id)
        gid = str(interaction.guild_id)

        async with get_db() as db:
            row = await _ensure_user(db, uid, gid)

            # Count users with more XP → rank
            rank_row = await db.fetchrow(
                'SELECT COUNT(*) AS cnt FROM users WHERE guild_id = $1 AND xp > $2',
                gid, row['xp'],
            )

        rank = (rank_row['cnt'] + 1) if rank_row else 1
        member = interaction.guild.get_member(target.id) or target

        await interaction.followup.send(
            embed=rank_embed(member, row['xp'], row['level'], rank)
        )

    # ── /bzleaderboard ────────────────────────────────────────────────────────

    @app_commands.command(name='bzleaderboard', description='View the top XP earners in this server.')
    @app_commands.describe(limit='How many users to show (1–20, default 10)')
    async def leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer()
        limit = max(1, min(20, limit))
        gid   = str(interaction.guild_id)

        async with get_db() as db:
            records = await db.fetch(
                'SELECT user_id, xp, level FROM users WHERE guild_id = $1 ORDER BY xp DESC LIMIT $2',
                gid, limit,
            )

        rows = [dict(r) for r in records]

        if not rows:
            return await interaction.followup.send(
                embed=error_embed('No XP data yet. Start chatting to earn XP!')
            )

        await interaction.followup.send(
            embed=leaderboard_embed(rows, interaction.guild)
        )


# ── Shared helpers used by other cogs ─────────────────────────────────────────

async def award_task_xp(user_id: str, guild_id: str, is_late: bool = False) -> dict:
    """Awards XP for completing a task. Returns updated xp/level info."""
    bonus = 20 if is_late else 50
    async with get_db() as db:
        await db.execute(
            'INSERT INTO users (user_id, guild_id) VALUES ($1, $2) ON CONFLICT (user_id, guild_id) DO NOTHING',
            user_id, guild_id,
        )
        row = await db.fetchrow(
            'SELECT xp, level FROM users WHERE user_id = $1 AND guild_id = $2',
            user_id, guild_id,
        )

        old_level = row['level']
        new_xp    = row['xp'] + bonus
        new_level = calculate_level(new_xp)

        await db.execute(
            'UPDATE users SET xp = $1, level = $2 WHERE user_id = $3 AND guild_id = $4',
            new_xp, new_level, user_id, guild_id,
        )

    return {'xp': new_xp, 'level': new_level, 'leveled_up': new_level > old_level, 'bonus': bonus}


async def reset_user_xp(user_id: str, guild_id: str):
    async with get_db() as db:
        await db.execute(
            'UPDATE users SET xp = 0, level = 0, last_xp_at = NULL WHERE user_id = $1 AND guild_id = $2',
            user_id, guild_id,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(XP(bot))
