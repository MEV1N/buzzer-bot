# ──────────────────────────────────────────────────────────────────────────────
# buzzer.py  —  Buzzer Bot: Main Entry Point
#
# Modular Discord bot using discord.py Cogs + Slash Commands + SQLite.
#
# Systems:
#   • Attendance tracking  (!startmeeting / !endmeeting)
#   • XP & Leveling        (/rank, /leaderboard)
#   • Moderation           (/warn, /mute, /kick, /ban, /promote, /demote, etc.)
#   • Task Management      (/task assign, /task complete, /task update, /task my)
#
# Environment variables (see .env.example):
#   DISCORD_TOKEN         — Required. Bot token.
#   OWNER_ID              — Required. Your Discord user ID.
#   LOG_CHANNEL_ID        — Optional. Channel ID for moderation logs.
#   REMINDER_INTERVAL_SECS — Optional. Task reminder frequency (default 60s).
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import os
import sys

load_dotenv()

# ── Validate required env vars ────────────────────────────────────────────────

TOKEN    = os.getenv('DISCORD_TOKEN')
OWNER_ID = os.getenv('OWNER_ID')

if not TOKEN:
    print('[ERROR] DISCORD_TOKEN is not set in .env')
    sys.exit(1)

if not OWNER_ID:
    print('[WARN]  OWNER_ID is not set — owner-only commands will not work.')

# ── Bot configuration ─────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True
intents.members         = True


class BuzzerBot(commands.Bot):
    """Custom Bot subclass to handle setup tasks cleanly."""

    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None,  # We'll define our own or let Cogs handle it
            description='Buzzer — your all-in-one server management bot.',
        )

    async def setup_hook(self):
        """Called once before the bot connects. Load cogs and sync commands."""

        # ── Initialise database ───────────────────────────────────────────────
        from database.db import init_db
        await init_db()
        print('[DB]    Database initialised.')

        # ── Load all cogs ─────────────────────────────────────────────────────
        cogs = [
            'cogs.attendance',
            'cogs.xp',
            'cogs.moderation',
            'cogs.tasks',
            'cogs.help',
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f'[COG]   Loaded: {cog}')
            except Exception as e:
                print(f'[COG]   Failed to load {cog}: {e}')

        # ── Sync slash commands to Discord ────────────────────────────────────
        # Syncs globally; may take up to 1 hour to propagate to all servers.
        # For instant testing on a single guild, uncomment the guild-specific sync below.
        try:
            synced = await self.tree.sync()
            print(f'[SYNC]  Synced {len(synced)} slash command(s) globally.')

            # --- Uncomment for instant guild-specific sync during development ---
            # GUILD_ID = os.getenv('GUILD_ID')
            # if GUILD_ID:
            #     guild = discord.Object(id=int(GUILD_ID))
            #     self.tree.copy_global_to(guild=guild)
            #     await self.tree.sync(guild=guild)
            #     print(f'[SYNC]  Synced to guild {GUILD_ID} instantly.')

        except Exception as e:
            print(f'[SYNC]  Failed to sync commands: {e}')

    async def on_ready(self):
        print(f'[READY] Logged in as {self.user} (ID: {self.user.id})')
        print(f'[READY] Serving {len(self.guilds)} guild(s).')
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name='/rank | Buzzer Bot',
            )
        )

    async def on_command_error(self, ctx: commands.Context, error):
        """Global prefix-command error handler."""
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown prefix commands
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('❌ You do not have permission to use that command.')
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send('❌ I do not have permission to perform that action.')
        else:
            print(f'[CMD ERROR] {error}')
            raise error


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    bot = BuzzerBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
