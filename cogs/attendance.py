# ──────────────────────────────────────────────────────────────────────────────
# cogs/attendance.py
# Original attendance tracking functionality, ported to a Cog.
# Commands: !startmeeting <#channel>, !endmeeting
# ──────────────────────────────────────────────────────────────────────────────

import discord
from discord.ext import commands
import datetime


class Attendance(commands.Cog):
    """Voice-channel attendance tracking for meetings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Active meeting state (one meeting per bot instance)
        self._meeting = {
            'is_active':   False,
            'channel_id':  None,
            'start_time':  None,
            'participants': {},   # user_id → {total_time, join_time}
            'all_members':  set(),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def m(self):
        return self._meeting

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def startmeeting(self, ctx: commands.Context, channel: discord.VoiceChannel):
        """
        Start tracking attendance in a voice channel.
        Usage: !startmeeting <#VoiceChannel>
        """
        if self.m['is_active']:
            await ctx.send('A meeting is already active. Use `!endmeeting` first.')
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        self.m.update({
            'is_active':    True,
            'channel_id':   channel.id,
            'start_time':   now,
            'participants': {},
            'all_members':  {
                member.id
                for member in ctx.channel.members
                if not member.bot
            },
        })

        await ctx.send(f'✅ Meeting started in {channel.mention}. Tracking attendance...')

        # Connect bot to the voice channel
        try:
            if ctx.voice_client is None:
                await channel.connect()
            else:
                await ctx.voice_client.move_to(channel)
        except Exception as e:
            await ctx.send(f'Could not connect to voice: {e}')
            self.m['is_active'] = False
            return

        # Track members already in the channel
        for member in channel.members:
            if not member.bot:
                self.m['participants'][member.id] = {
                    'total_time': 0.0,
                    'join_time':  now,
                }

    @startmeeting.error
    async def startmeeting_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('You need Administrator permissions.')
        elif isinstance(error, (commands.ChannelNotFound, commands.BadArgument)):
            await ctx.send('Invalid channel. Please mention a valid voice channel.')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('Usage: `!startmeeting <#VoiceChannel>`')

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def endmeeting(self, ctx: commands.Context):
        """
        End the current meeting and print the attendance report.
        Usage: !endmeeting
        """
        if not self.m['is_active']:
            await ctx.send('No active meeting to end.')
            return

        if ctx.voice_client:
            await ctx.voice_client.disconnect()

        end_time        = datetime.datetime.now(datetime.timezone.utc)
        total_secs      = (end_time - self.m['start_time']).total_seconds()
        required_secs   = total_secs * 0.80

        # Finalise time for anyone still in VC
        for uid, data in self.m['participants'].items():
            if data['join_time'] is not None:
                data['total_time'] += (end_time - data['join_time']).total_seconds()
                data['join_time'] = None

        present, late, absent = [], [], []

        for uid in self.m['all_members']:
            member = ctx.guild.get_member(uid)
            if member is None:
                continue
            name = member.display_name

            if uid in self.m['participants']:
                secs = self.m['participants'][uid]['total_time']
                mins = int(secs // 60)
                if secs >= required_secs:
                    present.append(f'* {name} ({mins} min)')
                elif secs > 0:
                    late.append(f'* {name} ({max(mins, 1)} min)')
                else:
                    absent.append(f'* {name}')
            else:
                absent.append(f'* {name}')

        # Build report
        lines = ['📊 **Meeting Report**\n']
        lines += ['✅ **Present:**'] + (present or ['* None'])
        lines += ['\n⚠️ **Late:**']   + (late    or ['* None'])
        lines += ['\n❌ **Absent:**'] + (absent   or ['* None'])
        report = '\n'.join(lines)

        # Chunk to respect Discord's 2000-char limit
        chunks, cur = [], ''
        for line in report.split('\n'):
            if len(cur) + len(line) + 1 > 1950:
                chunks.append(cur)
                cur = line + '\n'
            else:
                cur += line + '\n'
        if cur:
            chunks.append(cur)

        for chunk in chunks:
            await ctx.send(chunk)

        # Reset state
        self.m.update({
            'is_active': False, 'channel_id': None, 'start_time': None,
        })
        self.m['participants'].clear()
        self.m['all_members'].clear()

    @endmeeting.error
    async def endmeeting_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('You need Administrator permissions.')

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after:  discord.VoiceState,
    ):
        if member.bot or not self.m['is_active']:
            return

        ch_id = self.m['channel_id']
        now   = datetime.datetime.now(datetime.timezone.utc)

        # Joined the meeting channel
        if after.channel and after.channel.id == ch_id:
            if not before.channel or before.channel.id != ch_id:
                if member.id not in self.m['participants']:
                    self.m['participants'][member.id] = {'total_time': 0.0, 'join_time': now}
                else:
                    self.m['participants'][member.id]['join_time'] = now

        # Left the meeting channel
        if before.channel and before.channel.id == ch_id:
            if not after.channel or after.channel.id != ch_id:
                data = self.m['participants'].get(member.id)
                if data and data['join_time']:
                    data['total_time'] += (now - data['join_time']).total_seconds()
                    data['join_time'] = None


async def setup(bot: commands.Bot):
    await bot.add_cog(Attendance(bot))
