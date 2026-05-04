# ──────────────────────────────────────────────────────────────────────────────
# cogs/help.py
# /help — Shows all Buzzer commands organised by category.
# Optional category argument to drill into a specific section.
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from utils.embeds import COLORS


# ── Command reference data ────────────────────────────────────────────────────

CATEGORIES = {
    'xp': {
        'label':  '⚡  XP & Leveling',
        'color':  COLORS['xp'],
        'desc':   'Earn XP by chatting. Level up automatically.',
        'commands': [
            ('/bzrank',              'Show your XP rank card.',                  'Anyone'),
            ('/bzrank @user',        'Show another user\'s rank card.',          'Anyone'),
            ('/bzleaderboard',       'Top 10 XP earners in this server.',        'Anyone'),
            ('/bzleaderboard limit', 'Show top N users (1–20).',                 'Anyone'),
        ],
    },
    'tasks': {
        'label':  '📋  Task Management',
        'color':  COLORS['task'],
        'desc':   'Assign, track, and complete tasks with proof.',
        'commands': [
            ('/bztask assign @user title due remind', 'Assign a task to a member.',              'Admin+'),
            ('/bztask update taskId message',         'Post a status update on a task.',         'Assignee / Admin'),
            ('/bztask complete taskId proof',         'Mark a task done. Proof URL required.',   'Assignee only'),
            ('/bztask my',                            'List all tasks assigned to you.',          'Anyone'),
        ],
    },
    'moderation': {
        'label':  '🛡️  Moderation',
        'color':  COLORS['mod'],
        'desc':   'Custom permission system — independent of Discord roles.',
        'commands': [
            ('/bzwarn @user reason',    'Issue a warning.',                         'Admin+'),
            ('/bzmute @user dur reason','Timeout a member (e.g. 10m, 2h, 1d).',    'Admin+'),
            ('/bzkick @user reason',    'Kick a member from the server.',           'Admin+'),
            ('/bzban @user reason',     'Ban a member from the server.',            'Owner only'),
            ('/bzresetxp @user',        'Reset a user\'s XP and level to 0.',      'Owner only'),
            ('/bzpromote @user',        'Grant Core Admin role to a member.',       'Owner only'),
            ('/bzdemote @user',         'Remove Core Admin role from a member.',    'Owner only'),
            ('/bzdeletetask taskId',    'Permanently delete a task.',               'Owner only'),
        ],
    },
    'attendance': {
        'label':  '📊  Attendance',
        'color':  COLORS['info'],
        'desc':   'Track voice-channel attendance for meetings.',
        'commands': [
            ('!startmeeting #channel', 'Start tracking attendance in a VC.',    'Discord Admin'),
            ('!endmeeting',            'End the meeting and print the report.', 'Discord Admin'),
        ],
    },
}

CATEGORY_CHOICES = [
    app_commands.Choice(name='⚡ XP & Leveling',    value='xp'),
    app_commands.Choice(name='📋 Task Management',  value='tasks'),
    app_commands.Choice(name='🛡️ Moderation',       value='moderation'),
    app_commands.Choice(name='📊 Attendance',        value='attendance'),
]


# ── Embed builders ────────────────────────────────────────────────────────────

def build_overview_embed() -> discord.Embed:
    """Main help embed listing all categories."""
    e = discord.Embed(
        title='⚡  Buzzer Bot — Help',
        description=(
            'A modular Discord bot with XP leveling, task management, '
            'moderation, and meeting attendance tracking.\n\n'
            'Use `/help category:<name>` to see commands for a specific system.'
        ),
        color=COLORS['xp'],
        timestamp=datetime.now(timezone.utc),
    )

    for cat in CATEGORIES.values():
        cmd_count = len(cat['commands'])
        e.add_field(
            name=cat['label'],
            value=f"{cat['desc']}\n`{cmd_count} command{'s' if cmd_count != 1 else ''}`",
            inline=True,
        )

    e.add_field(name='\u200b', value='\u200b', inline=True)  # padding for 3-col layout

    e.add_field(
        name='🔑  Permission Levels',
        value=(
            '👑 **Owner** — set via `OWNER_ID` in `.env`\n'
            '🛡️ **Admin** — granted with `/promote`\n'
            '👤 **Member** — everyone else'
        ),
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

    e.set_footer(text='⚡ Buzzer Bot  •  /help category:<name> for details')
    return e


def build_category_embed(key: str) -> discord.Embed:
    """Detailed embed for a single category."""
    cat = CATEGORIES[key]

    e = discord.Embed(
        title=cat['label'],
        description=cat['desc'],
        color=cat['color'],
        timestamp=datetime.now(timezone.utc),
    )

    for cmd, desc, who in cat['commands']:
        e.add_field(
            name=f'`{cmd}`',
            value=f'{desc}\n> 🔐 **{who}**',
            inline=False,
        )

    e.set_footer(text='⚡ Buzzer Bot  •  /help for full overview')
    return e


# ── Cog ──────────────────────────────────────────────────────────────────────

class Help(commands.Cog):
    """Help command — overview and per-category command reference."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='bzhelp', description='Show all Buzzer commands and how to use them.')
    @app_commands.describe(category='Drill into a specific category (optional)')
    @app_commands.choices(category=CATEGORY_CHOICES)
    async def help(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str] = None,
    ):
        if category:
            embed = build_category_embed(category.value)
        else:
            embed = build_overview_embed()

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
