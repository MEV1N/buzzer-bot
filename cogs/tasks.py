# ──────────────────────────────────────────────────────────────────────────────
# cogs/tasks.py
# Task management system with:
#   - /task assign  — assign a task to a user
#   - /task update  — post a status update on a task
#   - /task complete — mark as done with proof
#   - /task my      — list all your tasks
#
# Background reminder scheduler:
#   - Runs every REMINDER_INTERVAL_SECS seconds
#   - DMs the assignee if task is still pending
#   - Escalates to admin after 3 missed reminders
#   - Marks task as 'overdue' when past due date
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord import app_commands
from discord.ext import commands, tasks as ext_tasks
import time
import os

from database.db import get_db
from utils.embeds import (
    success_embed, error_embed, warning_embed, task_embed, info_embed
)
from utils.time_parser import parse_time, format_duration
from cogs.xp import award_task_xp

ESCALATION_THRESHOLD = 3


def _make_task_id() -> str:
    """Generates a short unique task ID, e.g. TASK-1ABC23."""
    return f'TASK-{int(time.time() * 1000) % 0xFFFFFF:06X}'


class Tasks(commands.Cog):
    """Task assignment and reminder system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._interval = int(os.getenv('REMINDER_INTERVAL_SECS', '60'))
        self.reminder_loop.change_interval(seconds=self._interval)
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    # ── /task group ───────────────────────────────────────────────────────────

    task_group = app_commands.Group(name='task', description='Task management commands.')

    # ── /task assign ──────────────────────────────────────────────────────────

    @task_group.command(name='assign', description='Assign a task to a user. [Admin+]')
    @app_commands.describe(
        user        = 'Who to assign the task to',
        title       = 'Task title / description',
        due         = 'Time until due (e.g. 2h, 1d, 3w)',
        remind      = 'Reminder interval (e.g. 30m, 2h)',
    )
    async def assign(
        self,
        interaction: discord.Interaction,
        user:   discord.Member,
        title:  str,
        due:    str,
        remind: str = '2h',
    ):
        await interaction.response.defer(ephemeral=True)

        from cogs.moderation import has_permission
        if not await has_permission(str(interaction.user.id), str(interaction.guild_id), 'admin'):
            return await interaction.followup.send(
                embed=error_embed('Only **Admins** and the **Owner** can assign tasks.'), ephemeral=True
            )
        if user.bot:
            return await interaction.followup.send(embed=error_embed('Cannot assign tasks to bots.'), ephemeral=True)

        due_secs = parse_time(due)
        if due_secs is None:
            return await interaction.followup.send(
                embed=error_embed('Invalid due format. Use e.g. `2h`, `1d`, `3w`.'), ephemeral=True
            )

        remind_secs = parse_time(remind)
        if remind_secs is None:
            return await interaction.followup.send(
                embed=error_embed('Invalid reminder format. Use e.g. `30m`, `2h`.'), ephemeral=True
            )

        now      = time.time()
        due_ts   = now + due_secs
        task_id  = _make_task_id()

        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO tasks
                    (task_id, guild_id, title, assigned_to, assigned_by,
                     due_date, reminder_interval, next_reminder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(interaction.guild_id),
                    title,
                    str(user.id),
                    str(interaction.user.id),
                    due_ts,
                    remind_secs,
                    now + remind_secs,
                ),
            )
            await db.commit()

            async with db.execute(
                'SELECT * FROM tasks WHERE task_id = ?', (task_id,)
            ) as cur:
                row = dict(await cur.fetchone())

        # DM the assigned user
        try:
            embed = info_embed(
                '📋  New Task Assigned',
                f'You have been assigned a new task by {interaction.user.mention}.',
            )
            embed.add_field(name='Task ID',   value=f'`{task_id}`',                         inline=True)
            embed.add_field(name='Title',     value=title,                                   inline=False)
            embed.add_field(name='Due',       value=f'<t:{int(due_ts)}:F>  (<t:{int(due_ts)}:R>)', inline=False)
            embed.add_field(name='Reminders', value=f'Every {format_duration(remind_secs)}', inline=True)
            embed.set_footer(text='Use /task complete <taskId> to mark it done with proof.')
            await user.send(embed=embed)
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            embed=success_embed(
                'Task Assigned',
                f'Task `{task_id}` assigned to {user.mention}.\n**Title:** {title}\n**Due:** <t:{int(due_ts)}:F>',
            ),
            ephemeral=True,
        )

    # ── /task update ──────────────────────────────────────────────────────────

    @task_group.command(name='update', description='Post a status update on your task.')
    @app_commands.describe(task_id='Your task ID', message='Status update message')
    async def update(self, interaction: discord.Interaction, task_id: str, message: str):
        await interaction.response.defer(ephemeral=True)

        tid = task_id.upper()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        async with await get_db() as db:
            async with db.execute(
                'SELECT * FROM tasks WHERE task_id = ? AND guild_id = ?', (tid, gid)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return await interaction.followup.send(
                    embed=error_embed(f'Task `{tid}` not found.'), ephemeral=True
                )

            # Only the assignee, admins, or owner can update
            from cogs.moderation import has_permission
            is_admin = await has_permission(uid, gid, 'admin')
            if row['assigned_to'] != uid and not is_admin:
                return await interaction.followup.send(
                    embed=error_embed('You can only update tasks assigned to you.'), ephemeral=True
                )

            if row['status'] == 'completed':
                return await interaction.followup.send(
                    embed=error_embed('This task is already completed.'), ephemeral=True
                )

            await db.execute(
                'UPDATE tasks SET last_update = ? WHERE task_id = ? AND guild_id = ?',
                (message, tid, gid),
            )
            await db.commit()

            async with db.execute('SELECT * FROM tasks WHERE task_id = ?', (tid,)) as cur:
                updated = dict(await cur.fetchone())

        await interaction.followup.send(
            embed=success_embed('Task Updated', f'Task `{tid}` update recorded.'),
            ephemeral=True,
        )

        # Notify the admin who assigned it
        try:
            admin = await self.bot.fetch_user(int(updated['assigned_by']))
            notify = info_embed(
                '📝  Task Update',
                f'<@{uid}> posted an update on task `{tid}`:\n> {message}',
            )
            await admin.send(embed=notify)
        except (discord.HTTPException, ValueError):
            pass

    # ── /task complete ────────────────────────────────────────────────────────

    @task_group.command(name='complete', description='Mark a task as completed. Proof required.')
    @app_commands.describe(task_id='Your task ID', proof='Image URL or attachment URL as proof')
    async def complete(self, interaction: discord.Interaction, task_id: str, proof: str):
        await interaction.response.defer(ephemeral=True)

        tid = task_id.upper()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        # Validate proof is not empty
        if not proof or not proof.strip():
            return await interaction.followup.send(
                embed=error_embed('Proof is required. Provide an image URL or attachment link.'),
                ephemeral=True,
            )

        async with await get_db() as db:
            async with db.execute(
                'SELECT * FROM tasks WHERE task_id = ? AND guild_id = ?', (tid, gid)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return await interaction.followup.send(
                    embed=error_embed(f'Task `{tid}` not found.'), ephemeral=True
                )
            if row['assigned_to'] != uid:
                return await interaction.followup.send(
                    embed=error_embed('You can only complete tasks assigned to you.'), ephemeral=True
                )
            if row['status'] == 'completed':
                return await interaction.followup.send(
                    embed=error_embed('This task is already completed.'), ephemeral=True
                )

            now     = time.time()
            is_late = now > row['due_date']

            await db.execute(
                """
                UPDATE tasks
                SET status = 'completed', proof = ?, completed_at = ?, last_update = ?
                WHERE task_id = ? AND guild_id = ?
                """,
                (proof, now, 'Completed by assignee', tid, gid),
            )
            await db.commit()

        # Award XP
        xp_result = await award_task_xp(uid, gid, is_late)

        late_note = ' _(late completion — reduced XP)_' if is_late else ''
        embed = success_embed(
            'Task Completed! ✅',
            (
                f'Task `{tid}` has been marked as **completed**.\n'
                f'**Proof:** {proof}\n'
                f'**XP Awarded:** +{xp_result["bonus"]} XP{late_note}'
            ),
        )
        if xp_result['leveled_up']:
            embed.add_field(
                name='🎉 Level Up!',
                value=f'You reached **Level {xp_result["level"]}**!',
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Notify the assigning admin
        try:
            admin = await self.bot.fetch_user(int(row['assigned_by']))
            notify = success_embed(
                'Task Completed',
                f'<@{uid}> completed task `{tid}` — _{row["title"]}_\n**Proof:** {proof}',
            )
            if is_late:
                notify.add_field(name='⚠️ Late', value='Completed after due date.', inline=False)
            await admin.send(embed=notify)
        except (discord.HTTPException, ValueError):
            pass

    # ── /task my ─────────────────────────────────────────────────────────────

    @task_group.command(name='my', description='List all tasks assigned to you.')
    async def my(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        uid = str(interaction.user.id)
        gid = str(interaction.guild_id)

        async with await get_db() as db:
            async with db.execute(
                'SELECT * FROM tasks WHERE assigned_to = ? AND guild_id = ? ORDER BY due_date ASC',
                (uid, gid),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]

        if not rows:
            return await interaction.followup.send(
                embed=info_embed('Your Tasks', 'You have no tasks assigned. 🎉'), ephemeral=True
            )

        # Split into pages of 3 tasks (to respect embed limits)
        for i in range(0, len(rows), 3):
            batch = rows[i:i+3]
            embeds = [task_embed(t) for t in batch]
            await interaction.followup.send(embeds=embeds, ephemeral=True)

    # ── Background reminder loop ───────────────────────────────────────────────

    @ext_tasks.loop(seconds=60)  # default; overridden in __init__
    async def reminder_loop(self):
        """Periodic task: send reminders and escalate ignored tasks."""
        now = time.time()

        try:
            async with await get_db() as db:
                # All pending tasks whose next_reminder is due
                async with db.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = 'pending' AND next_reminder <= ?
                    """,
                    (now,),
                ) as cur:
                    due_tasks = [dict(r) for r in await cur.fetchall()]

                for task in due_tasks:
                    # Mark overdue if past due date
                    if now > task['due_date']:
                        await db.execute(
                            "UPDATE tasks SET status = 'overdue' WHERE task_id = ?",
                            (task['task_id'],),
                        )
                        await db.commit()
                        await self._send_reminder(task, overdue=True)
                        continue

                    # Send reminder DM
                    await self._send_reminder(task, overdue=False)

                    new_count    = task['reminder_count'] + 1
                    next_remind  = now + task['reminder_interval']
                    escalated    = task['escalated']

                    # Escalate if too many misses
                    if new_count >= ESCALATION_THRESHOLD and not escalated:
                        escalated = 1
                        await self._send_escalation(task)

                    await db.execute(
                        """
                        UPDATE tasks
                        SET reminder_count = ?, next_reminder = ?, escalated = ?
                        WHERE task_id = ?
                        """,
                        (new_count, next_remind, escalated, task['task_id']),
                    )
                    await db.commit()

        except Exception as exc:
            print(f'[TASKS] Scheduler error: {exc}')

    @reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    async def _send_reminder(self, task: dict, overdue: bool):
        try:
            user = await self.bot.fetch_user(int(task['assigned_to']))
            due_ts = int(task['due_date'])

            if overdue:
                embed = warning_embed(
                    '🔴  Task OVERDUE',
                    (
                        f"Your task **`{task['task_id']}`** — _{task['title']}_ — is **overdue**!\n"
                        f"Please complete it immediately using `/task complete`."
                    ),
                )
            else:
                embed = warning_embed(
                    '⏰  Task Reminder',
                    (
                        f"Reminder: Task **`{task['task_id']}`** — _{task['title']}_ — is still **pending**.\n"
                        f"Please update or complete it using `/task complete`."
                    ),
                )

            embed.add_field(name='Due',             value=f'<t:{due_ts}:F>',              inline=True)
            embed.add_field(name='Reminders Sent',  value=str(task['reminder_count'] + 1), inline=True)
            await user.send(embed=embed)

        except (discord.HTTPException, ValueError):
            pass  # DMs closed / user left — safe to skip

    async def _send_escalation(self, task: dict):
        try:
            admin = await self.bot.fetch_user(int(task['assigned_by']))
            embed = warning_embed(
                '🚨  Task Escalation',
                (
                    f"<@{task['assigned_to']}> has **ignored {ESCALATION_THRESHOLD} reminders** "
                    f"for task **`{task['task_id']}`** — _{task['title']}_.\n"
                    f"Immediate attention may be required."
                ),
            )
            embed.add_field(name='Task ID', value=task['task_id'],                     inline=True)
            embed.add_field(name='Due',     value=f"<t:{int(task['due_date'])}:F>",    inline=True)
            await admin.send(embed=embed)
        except (discord.HTTPException, ValueError):
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tasks(bot))
