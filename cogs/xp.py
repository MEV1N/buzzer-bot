# ──────────────────────────────────────────────────────────────────────────────
# cogs/xp.py
# XP & Leveling system.
#
# XP gain: 5–15 per message, 30-second cooldown.
# Level formula: level = floor(0.1 * sqrt(xp))
# Slash commands: /rank, /leaderboard
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands
import math
import random
import time
import os

from database.db import get_db
from utils.embeds import rank_embed, leaderboard_embed, success_embed, error_embed


XP_MIN      = 5
XP_MAX      = 15
COOLDOWN_S  = 30   # seconds


def calculate_level(xp: int) -> int:
    """level = floor(0.1 * sqrt(xp))"""
    return math.floor(0.1 * math.sqrt(xp))


async def _ensure_user(db, user_id: str, guild_id: str):
    """Creates a user row if it doesn't exist; returns the row."""
    owner_id = os.getenv('OWNER_ID', '')
    role = 'owner' if user_id == owner_id else 'member'
    await db.execute(
        """
        INSERT OR IGNORE INTO users (user_id, guild_id, role)
        VALUES (?, ?, ?)
        """,
        (user_id, guild_id, role),
    )
    await db.commit()
    async with db.execute(
        'SELECT * FROM users WHERE user_id = ? AND guild_id = ?',
        (user_id, guild_id),
    ) as cur:
        return await cur.fetchone()


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

        now = time.time()
        uid = str(message.author.id)
        gid = str(message.guild.id)

        async with await get_db() as db:
            user = await _ensure_user(db, uid, gid)

            # Cooldown check
            last_xp = user['last_xp_at'] or 0.0
            if now - last_xp < COOLDOWN_S:
                return

            gain      = random.randint(XP_MIN, XP_MAX)
            old_level = user['level']
            new_xp    = user['xp'] + gain
            new_level = calculate_level(new_xp)

            await db.execute(
                """
                UPDATE users
                SET xp = ?, level = ?, last_xp_at = ?
                WHERE user_id = ? AND guild_id = ?
                """,
                (new_xp, new_level, now, uid, gid),
            )
            await db.commit()

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

    # ── /rank ─────────────────────────────────────────────────────────────────

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

        async with await get_db() as db:
            row = await _ensure_user(db, uid, gid)

            # Count users with more XP → rank
            async with db.execute(
                'SELECT COUNT(*) as cnt FROM users WHERE guild_id = ? AND xp > ?',
                (gid, row['xp']),
            ) as cur:
                rank_row = await cur.fetchone()

        rank = (rank_row['cnt'] + 1) if rank_row else 1
        member = interaction.guild.get_member(target.id) or target

        await interaction.followup.send(
            embed=rank_embed(member, row['xp'], row['level'], rank)
        )

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(name='bzleaderboard', description='View the top XP earners in this server.')
    @app_commands.describe(limit='How many users to show (1–20, default 10)')
    async def leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer()
        limit = max(1, min(20, limit))
        gid   = str(interaction.guild_id)

        async with await get_db() as db:
            async with db.execute(
                'SELECT user_id, xp, level FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT ?',
                (gid, limit),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]

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
    async with await get_db() as db:
        # Ensure row exists
        await db.execute(
            'INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)',
            (user_id, guild_id),
        )
        async with db.execute(
            'SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?',
            (user_id, guild_id),
        ) as cur:
            row = await cur.fetchone()

        old_level = row['level']
        new_xp    = row['xp'] + bonus
        new_level = calculate_level(new_xp)

        await db.execute(
            'UPDATE users SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?',
            (new_xp, new_level, user_id, guild_id),
        )
        await db.commit()

    return {'xp': new_xp, 'level': new_level, 'leveled_up': new_level > old_level, 'bonus': bonus}


async def reset_user_xp(user_id: str, guild_id: str):
    async with await get_db() as db:
        await db.execute(
            'UPDATE users SET xp = 0, level = 0, last_xp_at = NULL WHERE user_id = ? AND guild_id = ?',
            (user_id, guild_id),
        )
        await db.commit()


async def setup(bot: commands.Bot):
    await bot.add_cog(XP(bot))
