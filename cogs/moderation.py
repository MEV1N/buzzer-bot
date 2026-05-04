# ──────────────────────────────────────────────────────────────────────────────
# cogs/moderation.py
# Custom moderation system with a 3-tier permission hierarchy:
#   owner → admin → member
#
# Slash commands:
#   Admin+: /warn, /mute, /kick
#   Owner:  /ban, /resetxp, /promote, /demote, /deletetask
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands
import json
import os

from database.db import get_db
from utils.embeds import success_embed, error_embed, mod_log_embed, warning_embed
from utils.time_parser import parse_time, format_duration

ROLE_LEVELS = {'member': 0, 'admin': 1, 'owner': 2}


def is_owner_id(user_id: str) -> bool:
    """Returns True if the user ID matches the configured owner."""
    owner = os.getenv('OWNER_ID', '')
    return bool(owner) and user_id == owner


async def is_protected_target(target_id: str, guild_id: str) -> bool:
    """
    Returns True if the target should be immune to moderation actions.
    The owner is always protected — no one can take actions against them.
    """
    return is_owner_id(target_id)


# ── Permission helpers ────────────────────────────────────────────────────────

async def get_role(user_id: str, guild_id: str) -> str:
    """Returns the user's bot role ('owner'|'admin'|'member')."""
    if user_id == os.getenv('OWNER_ID', ''):
        # Ensure owner row is correct in DB
        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO users (user_id, guild_id, role)
                VALUES (?, ?, 'owner')
                ON CONFLICT(user_id, guild_id) DO UPDATE SET role = 'owner'
                """,
                (user_id, guild_id),
            )
            await db.commit()
        return 'owner'

    async with await get_db() as db:
        async with db.execute(
            'SELECT role FROM users WHERE user_id = ? AND guild_id = ?',
            (user_id, guild_id),
        ) as cur:
            row = await cur.fetchone()
    return row['role'] if row else 'member'


async def has_permission(user_id: str, guild_id: str, required: str) -> bool:
    role = await get_role(user_id, guild_id)
    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS.get(required, 0)


# ── Logging helper ────────────────────────────────────────────────────────────

async def log_action(
    interaction: discord.Interaction,
    action: str,
    target: discord.User,
    reason: str,
    extra: dict | None = None,
):
    """Saves action to DB and posts to the configured log channel."""
    async with await get_db() as db:
        await db.execute(
            """
            INSERT INTO mod_logs (guild_id, action, moderator_id, target_id, reason, extra)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(interaction.guild_id),
                action,
                str(interaction.user.id),
                str(target.id),
                reason,
                json.dumps(extra) if extra else None,
            ),
        )
        await db.commit()

    log_ch_id = os.getenv('LOG_CHANNEL_ID', '')
    if not log_ch_id:
        return
    channel = interaction.guild.get_channel(int(log_ch_id))
    if channel and channel.type in (discord.ChannelType.text,):
        embed = mod_log_embed(action, interaction.user, target, reason, extra)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


# ── Cog ──────────────────────────────────────────────────────────────────────

class Moderation(commands.Cog):
    """Custom permission-based moderation commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────────────────────
    # ADMIN+ COMMANDS
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='warn', description='Issue a warning to a member. [Admin+]')
    @app_commands.describe(user='The member to warn', reason='Reason for the warning')
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'admin'):
            return await interaction.followup.send(
                embed=error_embed('You do not have permission to use this command.'), ephemeral=True
            )
        if user.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed('You cannot warn yourself.'), ephemeral=True)
        if user.bot:
            return await interaction.followup.send(embed=error_embed('You cannot warn bots.'), ephemeral=True)
        if await is_protected_target(str(user.id), str(interaction.guild_id)):
            return await interaction.followup.send(
                embed=error_embed('🛡️ The Owner is immune to moderation actions.'), ephemeral=True
            )

        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO users (user_id, guild_id, warn_count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET warn_count = warn_count + 1
                """,
                (str(user.id), str(interaction.guild_id)),
            )
            await db.commit()

        await log_action(interaction, 'warn', user, reason)

        # Try to DM the warned user
        try:
            await user.send(
                embed=warning_embed(
                    'You have been warned',
                    f'**Server:** {interaction.guild.name}\n**Reason:** {reason}',
                )
            )
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            embed=success_embed('Warning Issued', f'{user.mention} has been warned.\n**Reason:** {reason}'),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='mute', description='Timeout a member for a duration. [Admin+]')
    @app_commands.describe(user='The member to mute', duration='Duration e.g. 10m, 2h, 1d', reason='Reason')
    async def mute(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = 'No reason provided.'):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'admin'):
            return await interaction.followup.send(
                embed=error_embed('You do not have permission to use this command.'), ephemeral=True
            )
        if user.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed('You cannot mute yourself.'), ephemeral=True)
        if user.bot:
            return await interaction.followup.send(embed=error_embed('You cannot mute bots.'), ephemeral=True)
        if await is_protected_target(str(user.id), str(interaction.guild_id)):
            return await interaction.followup.send(
                embed=error_embed('🛡️ The Owner is immune to moderation actions.'), ephemeral=True
            )

        secs = parse_time(duration)
        if secs is None:
            return await interaction.followup.send(
                embed=error_embed('Invalid duration. Use formats like `10m`, `2h`, `1d`.'), ephemeral=True
            )

        MAX_SECS = 28 * 24 * 3600
        if secs > MAX_SECS:
            return await interaction.followup.send(
                embed=error_embed('Maximum mute duration is **28 days**.'), ephemeral=True
            )

        import datetime
        try:
            await user.timeout(
                datetime.timedelta(seconds=secs),
                reason=f'[Buzzer] {reason}',
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=error_embed('I lack permission to mute this user. Check role hierarchy.'), ephemeral=True
            )

        await log_action(interaction, 'mute', user, reason, {'Duration': format_duration(secs)})

        await interaction.followup.send(
            embed=success_embed(
                'Member Muted',
                f'{user.mention} has been muted for **{format_duration(secs)}**.\n**Reason:** {reason}',
            ),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='kick', description='Kick a member from the server. [Admin+]')
    @app_commands.describe(user='The member to kick', reason='Reason for the kick')
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = 'No reason provided.'):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'admin'):
            return await interaction.followup.send(
                embed=error_embed('You do not have permission to use this command.'), ephemeral=True
            )
        if user.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed('You cannot kick yourself.'), ephemeral=True)
        if await is_protected_target(str(user.id), str(interaction.guild_id)):
            return await interaction.followup.send(
                embed=error_embed('🛡️ The Owner is immune to moderation actions.'), ephemeral=True
            )
        if not user.is_timed_out() and not interaction.guild.me.top_role > user.top_role:
            return await interaction.followup.send(
                embed=error_embed('I cannot kick this user. Check my role hierarchy.'), ephemeral=True
            )

        try:
            await user.kick(reason=f'[Buzzer] {reason}')
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=error_embed('I lack permission to kick this user.'), ephemeral=True
            )

        await log_action(interaction, 'kick', user, reason)

        await interaction.followup.send(
            embed=success_embed('Member Kicked', f'**{user}** has been kicked.\n**Reason:** {reason}'),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # OWNER-ONLY COMMANDS
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='ban', description='Ban a member from the server. [Owner only]')
    @app_commands.describe(user='The member to ban', reason='Reason for the ban')
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = 'No reason provided.'):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'owner'):
            return await interaction.followup.send(
                embed=error_embed('Only the **Owner** can ban members.'), ephemeral=True
            )
        if user.id == interaction.user.id:
            return await interaction.followup.send(embed=error_embed('You cannot ban yourself.'), ephemeral=True)
        if await is_protected_target(str(user.id), str(interaction.guild_id)):
            return await interaction.followup.send(
                embed=error_embed('🛡️ The Owner cannot be banned.'), ephemeral=True
            )

        try:
            await user.ban(reason=f'[Buzzer] {reason}', delete_message_days=1)
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=error_embed('I lack permission to ban this user.'), ephemeral=True
            )

        await log_action(interaction, 'ban', user, reason)

        await interaction.followup.send(
            embed=success_embed('Member Banned', f'**{user}** has been banned.\n**Reason:** {reason}'),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='resetxp', description="Reset a user's XP and level to 0. [Owner only]")
    @app_commands.describe(user='The user whose XP to reset')
    async def resetxp(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'owner'):
            return await interaction.followup.send(
                embed=error_embed('Only the **Owner** can reset XP.'), ephemeral=True
            )
        # Owner's own XP cannot be reset either (self-protection)
        if await is_protected_target(str(user.id), str(interaction.guild_id)) and str(user.id) != str(interaction.user.id):
            return await interaction.followup.send(
                embed=error_embed('🛡️ Cannot reset the Owner\'s XP.'), ephemeral=True
            )

        from cogs.xp import reset_user_xp
        await reset_user_xp(str(user.id), str(interaction.guild_id))
        await log_action(interaction, 'resetxp', user, 'XP reset by owner')

        await interaction.followup.send(
            embed=success_embed('XP Reset', f"{user.mention}'s XP and level have been reset to **0**."),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='promote', description='Promote a member to Core Admin. [Owner only]')
    @app_commands.describe(user='The member to promote')
    async def promote(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'owner'):
            return await interaction.followup.send(
                embed=error_embed('Only the **Owner** can promote members.'), ephemeral=True
            )
        if user.bot:
            return await interaction.followup.send(embed=error_embed('Cannot promote bots.'), ephemeral=True)

        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO users (user_id, guild_id, role) VALUES (?, ?, 'admin')
                ON CONFLICT(user_id, guild_id) DO UPDATE SET role = 'admin'
                """,
                (str(user.id), str(interaction.guild_id)),
            )
            await db.commit()

        await log_action(interaction, 'promote', user, 'Promoted to Core Admin')

        await interaction.followup.send(
            embed=success_embed('Promoted', f'{user.mention} is now a **Core Admin**. 🛡️'),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='demote', description='Demote a Core Admin back to Member. [Owner only]')
    @app_commands.describe(user='The admin to demote')
    async def demote(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'owner'):
            return await interaction.followup.send(
                embed=error_embed('Only the **Owner** can demote admins.'), ephemeral=True
            )

        # Cannot demote the owner — their role is always authoritative
        if await is_protected_target(str(user.id), str(interaction.guild_id)):
            return await interaction.followup.send(
                embed=error_embed('🛡️ The Owner\'s role cannot be changed.'), ephemeral=True
            )

        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO users (user_id, guild_id, role) VALUES (?, ?, 'member')
                ON CONFLICT(user_id, guild_id) DO UPDATE SET role = 'member'
                """,
                (str(user.id), str(interaction.guild_id)),
            )
            await db.commit()

        await log_action(interaction, 'demote', user, 'Demoted to Member')

        await interaction.followup.send(
            embed=success_embed('Demoted', f'{user.mention} has been demoted back to **Member**.'),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name='deletetask', description='Delete a task by ID. [Owner only]')
    @app_commands.describe(task_id='The task ID to delete (e.g. TASK-ABC123)')
    async def deletetask(self, interaction: discord.Interaction, task_id: str):
        await interaction.response.defer(ephemeral=True)

        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'owner'):
            return await interaction.followup.send(
                embed=error_embed('Only the **Owner** can delete tasks.'), ephemeral=True
            )

        async with await get_db() as db:
            async with db.execute(
                'SELECT task_id FROM tasks WHERE task_id = ? AND guild_id = ?',
                (task_id.upper(), str(interaction.guild_id)),
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return await interaction.followup.send(
                    embed=error_embed(f'Task `{task_id}` not found.'), ephemeral=True
                )

            await db.execute(
                'DELETE FROM tasks WHERE task_id = ? AND guild_id = ?',
                (task_id.upper(), str(interaction.guild_id)),
            )
            await db.commit()

        await log_action(interaction, 'deletetask', interaction.user, f'Deleted task {task_id}', {'Task ID': task_id})

        await interaction.followup.send(
            embed=success_embed('Task Deleted', f'Task `{task_id}` has been permanently deleted.'),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
