# ──────────────────────────────────────────────────────────────────────────────
# cogs/help.py
# /bzhelp — Shows commands available to normal members by default.
#            Admins and the owner can pass `show:all` to see everything.
# /bzinfo  — Explains how Buzzer Bot works (XP, leveling, tasks, roles).
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import math
import os

from utils.embeds import COLORS


# ── Command data ──────────────────────────────────────────────────────────────
# Each entry: (usage, description, min_role)
# min_role: 'member' | 'admin' | 'owner'

ALL_COMMANDS = {
    'xp': {
        'label': '⚡  XP & Leveling',
        'color': COLORS['xp'],
        'desc':  'Earn XP by chatting. Level up automatically.',
        'commands': [
            ('/bzrank',              'Show your XP rank card.',             'member'),
            ('/bzrank @user',        "Show another user's rank card.",      'member'),
            ('/bzleaderboard',       'Top 10 XP earners in this server.',   'member'),
            ('/bzleaderboard limit', 'Show top N users (1–20).',            'member'),
        ],
    },
    'tasks': {
        'label': '📋  Task Management',
        'color': COLORS['task'],
        'desc':  'Assign, track, and complete tasks with proof.',
        'commands': [
            ('/bztask my',                            'List all tasks assigned to you.',          'member'),
            ('/bztask update taskId message',         'Post a status update on your task.',       'member'),
            ('/bztask complete taskId proof',         'Mark a task done. Proof URL required.',    'member'),
            ('/bztask assign @user title due remind', 'Assign a task to a member.',              'admin'),
        ],
    },
    'moderation': {
        'label': '🛡️  Moderation',
        'color': COLORS['mod'],
        'desc':  'Custom permission system — independent of Discord roles.',
        'commands': [
            ('/bzwarn @user reason',     'Issue a warning.',                         'admin'),
            ('/bzmute @user dur reason', 'Timeout a member (e.g. 10m, 2h, 1d).',    'admin'),
            ('/bzkick @user reason',     'Kick a member from the server.',           'admin'),
            ('/bzban @user reason',      'Ban a member from the server.',            'owner'),
            ('/bzresetxp @user',         "Reset a user's XP and level to 0.",       'owner'),
            ('/bzpromote @user',         'Grant Core Admin role to a member.',       'owner'),
            ('/bzdemote @user',          'Remove Core Admin role from a member.',    'owner'),
            ('/bzdeletetask taskId',     'Permanently delete a task.',               'owner'),
        ],
    },
    'attendance': {
        'label': '📊  Attendance',
        'color': COLORS['info'],
        'desc':  'Track voice-channel attendance for meetings.',
        'commands': [
            ('!startmeeting #channel', 'Start tracking attendance in a VC.',    'discord_admin'),
            ('!endmeeting',            'End the meeting and print the report.', 'discord_admin'),
        ],
    },
}

ROLE_RANK = {'member': 0, 'admin': 1, 'owner': 2, 'discord_admin': 3}


def _filter_commands(min_role: str) -> dict:
    """Return a copy of ALL_COMMANDS filtered to commands accessible at min_role level."""
    result = {}
    caller_rank = ROLE_RANK.get(min_role, 0)
    for key, cat in ALL_COMMANDS.items():
        cmds = [(u, d, r) for u, d, r in cat['commands']
                if ROLE_RANK.get(r, 0) <= caller_rank]
        if cmds:
            result[key] = {**cat, 'commands': cmds}
    return result


# ── Embed builders ────────────────────────────────────────────────────────────

def build_member_embed() -> discord.Embed:
    """Overview embed showing only member-accessible commands."""
    e = discord.Embed(
        title='⚡  Buzzer Bot — Help',
        description=(
            'Here are the commands available to you. '
            'Use `/bzhelp show:all` to see admin & owner commands too.\n\u200b'
        ),
        color=COLORS['xp'],
        timestamp=datetime.now(timezone.utc),
    )

    visible = _filter_commands('member')
    for cat in visible.values():
        lines = [f'`{cmd}`  —  {desc}' for cmd, desc, _ in cat['commands']]
        e.add_field(
            name=cat['label'],
            value='\n'.join(lines),
            inline=False,
        )

    e.add_field(
        name='⏱️  XP Info',
        value='`5–15 XP` per message · `30s` cooldown · Level = `floor(0.1 × √xp)`',
        inline=True,
    )
    e.add_field(
        name='✅  Task XP Bonus',
        value='`+50 XP` on time · `+20 XP` if late',
        inline=True,
    )
    e.set_footer(text='⚡ Buzzer Bot  •  /bzhelp show:all for the full command list')
    return e


def build_full_embed() -> discord.Embed:
    """Full overview embed with all commands grouped by permission tier."""
    TIER_EMOJI = {'member': '👤', 'admin': '🛡️', 'owner': '👑', 'discord_admin': '🔧'}

    e = discord.Embed(
        title='⚡  Buzzer Bot — Full Command Reference',
        description='All commands grouped by category. Permission level shown on each.\n\u200b',
        color=COLORS['xp'],
        timestamp=datetime.now(timezone.utc),
    )

    for cat in ALL_COMMANDS.values():
        lines = []
        for cmd, desc, role in cat['commands']:
            emoji = TIER_EMOJI.get(role, '❓')
            lines.append(f'{emoji} `{cmd}`  —  {desc}')
        e.add_field(
            name=cat['label'],
            value='\n'.join(lines),
            inline=False,
        )

    e.add_field(
        name='🔑  Permission Levels',
        value=(
            '👤 **Member** — everyone\n'
            '🛡️ **Admin** — granted with `/bzpromote`\n'
            '👑 **Owner** — set via `OWNER_ID` in `.env`\n'
            '🔧 **Discord Admin** — server Discord permissions'
        ),
        inline=False,
    )
    e.set_footer(text='⚡ Buzzer Bot  •  /bzhelp for the member overview')
    return e


# ── Info embed builder ────────────────────────────────────────────────────────

def _level_milestones() -> str:
    """Generate a few example level → XP thresholds."""
    # Inverse of level = floor(0.1 * sqrt(xp))  →  xp ≈ (level / 0.1)^2
    milestones = []
    for lvl in [1, 5, 10, 20, 50]:
        xp_needed = int((lvl / 0.1) ** 2)
        milestones.append(f'**Lv {lvl}** ≈ {xp_needed:,} XP')
    return ' · '.join(milestones)


def build_info_embed() -> discord.Embed:
    """Rich embed explaining how Buzzer Bot works."""
    e = discord.Embed(
        title='⚡  How Buzzer Bot Works',
        description=(
            'Buzzer tracks your activity, manages tasks, and keeps the server organised.\n'
            'Here is everything you need to know to get the most out of it.\n\u200b'
        ),
        color=COLORS['xp'],
        timestamp=datetime.now(timezone.utc),
    )

    # ── XP & Leveling ──────────────────────────────────────────────────────────
    e.add_field(
        name='⚡  XP & Leveling',
        value=(
            'You earn **5–15 XP** for every message you send, with a **30-second cooldown** '
            'between XP grants (so spamming short messages won\'t help!).\n\n'
            '**Level formula:** `Level = floor(0.1 × √XP)`\n'
            'Your level increases automatically — no command needed. When you level up, '
            'the bot will celebrate in the channel you\'re chatting in.\n\n'
            f'**Milestones:** {_level_milestones()}'
        ),
        inline=False,
    )

    # ── Task XP ───────────────────────────────────────────────────────────────
    e.add_field(
        name='📋  Task XP Bonuses',
        value=(
            'Completing tasks assigned to you also rewards XP on top of your chat XP:\n'
            '> 🟢 **+50 XP** — completed on time\n'
            '> 🟡 **+20 XP** — completed after the deadline\n\n'
            'Use `/bztask complete <taskId> <proof>` to submit your work. '
            'A proof URL (screenshot, link, etc.) is required.'
        ),
        inline=False,
    )

    # ── Useful commands ───────────────────────────────────────────────────────
    e.add_field(
        name='📊  Check Your Progress',
        value=(
            '`/bzrank` — see your XP, level, and server rank\n'
            '`/bzleaderboard` — top 10 earners in the server\n'
            '`/bztask my` — view all tasks assigned to you'
        ),
        inline=False,
    )

    # ── Attendance ────────────────────────────────────────────────────────────
    e.add_field(
        name='📡  Attendance Tracking',
        value=(
            'Discord Admins can run `!startmeeting #channel` to begin tracking who joins a '
            'voice channel. Run `!endmeeting` to stop — the bot will print a full attendance report.'
        ),
        inline=False,
    )

    e.set_footer(text='⚡ Buzzer Bot  •  /bzhelp to see all commands')
    return e


# ── Cog ───────────────────────────────────────────────────────────────────────

class Help(commands.Cog):
    """Help command — member overview by default, full list with show:all."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='bzhelp', description='Show Buzzer commands. Add show:all to see admin commands.')
    @app_commands.describe(show='Pass "all" to see every command including admin/owner ones.')
    @app_commands.choices(show=[
        app_commands.Choice(name='all — show every command', value='all'),
    ])
    async def help(
        self,
        interaction: discord.Interaction,
        show: app_commands.Choice[str] = None,
    ):
        if show and show.value == 'all':
            embed = build_full_embed()
        else:
            embed = build_member_embed()

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /bzinfo ───────────────────────────────────────────────────────────────

    @app_commands.command(name='bzinfo', description='Learn how Buzzer Bot works — XP, leveling, tasks & more.')
    async def info(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_info_embed(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
