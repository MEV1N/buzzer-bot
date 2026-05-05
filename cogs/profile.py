# ──────────────────────────────────────────────────────────────────────────────
# cogs/profile.py
# /bzprofile — Shows a user's full activity profile.
#
# Displays:
#   • XP, Level, Server rank
#   • Tasks assigned / completed
#   • Activity streak (days)
#   • Member since (Discord join date)
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database.db import get_db
from utils.embeds import COLORS, _progress_bar


class Profile(commands.Cog):
    """User profile command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='bzprofile', description='View your full activity profile (or another user\'s).')
    @app_commands.describe(user='The member to view (defaults to you)')
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer()

        target = user or interaction.user
        if target.bot:
            return await interaction.followup.send(
                '❌ Bots do not have profiles.', ephemeral=True
            )

        uid = str(target.id)
        gid = str(interaction.guild_id)

        async with get_db() as db:
            # XP / level / rank
            xp_row = await db.fetchrow(
                'SELECT xp, level FROM users WHERE user_id = $1 AND guild_id = $2',
                uid, gid,
            )
            rank_row = await db.fetchrow(
                'SELECT COUNT(*) AS cnt FROM users WHERE guild_id = $1 AND xp > $2',
                gid, (xp_row['xp'] if xp_row else 0),
            )

            # Tasks
            task_total = await db.fetchval(
                'SELECT COUNT(*) FROM tasks WHERE assigned_to = $1 AND guild_id = $2',
                uid, gid,
            ) or 0
            task_done = await db.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE assigned_to = $1 AND guild_id = $2 AND status = 'completed'",
                uid, gid,
            ) or 0

            # Streak
            activity = await db.fetchrow(
                'SELECT streak FROM user_activity WHERE user_id = $1 AND guild_id = $2',
                uid, gid,
            )

        xp    = xp_row['xp']    if xp_row    else 0
        level = xp_row['level'] if xp_row    else 0
        rank  = (rank_row['cnt'] + 1) if rank_row else 1
        streak = activity['streak'] if activity else 0

        # Progress to next level
        next_xp = int(((level + 1) / 0.1) ** 2)
        cur_xp  = int((level / 0.1) ** 2)
        progress = xp - cur_xp
        needed   = max(next_xp - cur_xp, 1)
        pct      = min(100, int((progress / needed) * 100))

        member = interaction.guild.get_member(target.id) or target

        embed = discord.Embed(
            title=f'👤  {member.display_name}\'s Profile',
            color=COLORS['xp'],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name='⚡ XP',    value=f'{xp:,}',  inline=True)
        embed.add_field(name='🎯 Level', value=str(level), inline=True)
        embed.add_field(name='🏅 Rank',  value=f'#{rank}', inline=True)

        embed.add_field(
            name='📈 Progress to Next Level',
            value=f'{_progress_bar(pct)}  {pct}%',
            inline=False,
        )

        embed.add_field(
            name='📋 Tasks',
            value=f'**{task_done}** completed out of **{task_total}** assigned',
            inline=True,
        )
        embed.add_field(
            name='🔥 Activity Streak',
            value=f'**{streak}** day{"s" if streak != 1 else ""}',
            inline=True,
        )

        joined = member.joined_at
        if joined:
            embed.add_field(
                name='📅 Member Since',
                value=f'<t:{int(joined.timestamp())}:D>',
                inline=True,
            )

        embed.set_footer(text='⚡ Buzzer Bot  •  /bzleaderboard to see the full ranking')
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
