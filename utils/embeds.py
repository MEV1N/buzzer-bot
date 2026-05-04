# ──────────────────────────────────────────────────────────────────────────────
# utils/embeds.py
# Pre-built discord.Embed factories for consistent UI across all cogs.
#
# Colour palette:
#   Info    → 0x5865F2  (blurple)
#   Success → 0x57F287  (green)
#   Warning → 0xFEE75C  (yellow)
#   Error   → 0xED4245  (red)
#   XP      → 0xFF9A3C  (orange)
#   Task    → 0xEB459E  (pink)
#   Mod     → 0x23272A  (dark)
# ──────────────────────────────────────────────────────────────────────────────

import discord
import math
from datetime import datetime, timezone


COLORS = {
    'info':    0x5865F2,
    'success': 0x57F287,
    'warning': 0xFEE75C,
    'error':   0xED4245,
    'xp':      0xFF9A3C,
    'task':    0xEB459E,
    'mod':     0x23272A,
}

FOOTER = {'text': '⚡ Buzzer Bot'}


def _base(color_key: str) -> discord.Embed:
    e = discord.Embed(color=COLORS[color_key], timestamp=datetime.now(timezone.utc))
    e.set_footer(text=FOOTER['text'])
    return e


def info_embed(title: str, description: str) -> discord.Embed:
    e = _base('info')
    e.title = title
    e.description = description
    return e


def success_embed(title: str, description: str) -> discord.Embed:
    e = _base('success')
    e.title = f'✅  {title}'
    e.description = description
    return e


def warning_embed(title: str, description: str) -> discord.Embed:
    e = _base('warning')
    e.title = f'⚠️  {title}'
    e.description = description
    return e


def error_embed(description: str) -> discord.Embed:
    e = _base('error')
    e.title = '❌  Error'
    e.description = description
    return e


def _progress_bar(pct: int, length: int = 20) -> str:
    filled = round((pct / 100) * length)
    return '█' * filled + '░' * (length - filled)


def rank_embed(member: discord.Member, xp: int, level: int, rank: int) -> discord.Embed:
    next_xp    = int((( level + 1) / 0.1) ** 2)
    cur_xp     = int((level       / 0.1) ** 2)
    progress   = xp - cur_xp
    needed     = next_xp - cur_xp
    pct        = min(100, int((progress / max(needed, 1)) * 100))

    e = _base('xp')
    e.title = '⚡  XP Rank Card'
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name='User',  value=member.mention,         inline=True)
    e.add_field(name='Rank',  value=f'#{rank}',             inline=True)
    e.add_field(name='Level', value=str(level),             inline=True)
    e.add_field(name='XP',    value=f'{xp:,} XP',          inline=True)
    e.add_field(name='Progress to Next Level',
                value=f'{_progress_bar(pct)}  {pct}%',     inline=False)
    return e


def leaderboard_embed(entries: list[dict], guild: discord.Guild) -> discord.Embed:
    medals = ['🥇', '🥈', '🥉']
    lines = []
    for i, row in enumerate(entries):
        prefix = medals[i] if i < 3 else f'**{i+1}.**'
        lines.append(
            f"{prefix}  <@{row['user_id']}> — Level **{row['level']}** · **{row['xp']:,}** XP"
        )
    e = _base('xp')
    e.title = '🏆  XP Leaderboard'
    e.description = '\n'.join(lines) or 'No data yet.'
    e.set_footer(text=f'{guild.name} · Top {len(entries)}')
    return e


def task_embed(task: dict) -> discord.Embed:
    status_emoji = {'pending': '🕐', 'completed': '✅', 'overdue': '🔴'}
    due_ts  = int(task['due_date'])
    e = _base('task')
    e.title = f"📋  Task `{task['task_id']}`"
    e.add_field(name='Title',       value=task['title'],                                  inline=False)
    e.add_field(name='Assigned To', value=f"<@{task['assigned_to']}>",                    inline=True)
    e.add_field(name='Assigned By', value=f"<@{task['assigned_by']}>",                    inline=True)
    e.add_field(name='Status',      value=f"{status_emoji.get(task['status'], '?')}  {task['status']}", inline=True)
    e.add_field(name='Due',         value=f'<t:{due_ts}:F>  (<t:{due_ts}:R>)',            inline=False)
    e.add_field(name='Last Update', value=task['last_update'] or '_No update yet._',       inline=False)
    e.add_field(name='Proof',       value=task['proof']       or '_No proof yet._',        inline=False)
    return e


def mod_log_embed(
    action: str,
    moderator: discord.User,
    target: discord.User,
    reason: str,
    extra: dict | None = None,
) -> discord.Embed:
    ACTION_EMOJI = {
        'warn': '⚠️', 'mute': '🔇', 'kick': '👢', 'ban': '🔨',
        'promote': '⬆️', 'demote': '⬇️', 'resetxp': '🔄', 'deletetask': '🗑️',
    }
    e = _base('mod')
    e.title = f"{ACTION_EMOJI.get(action, '🔧')}  Moderation: {action.upper()}"
    e.add_field(name='Moderator', value=f'{moderator.mention} ({moderator})', inline=True)
    e.add_field(name='Target',    value=f'{target.mention} ({target})',       inline=True)
    e.add_field(name='Reason',    value=reason,                                inline=False)
    if extra:
        for k, v in extra.items():
            e.add_field(name=k, value=str(v), inline=True)
    return e
