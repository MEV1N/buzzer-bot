import discord
from discord.ext import commands
import datetime

# Configure intents required for reading members and voice states
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

# Initialize bot with the '!' prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Dictionary to hold the state of the active meeting
active_meeting = {
    "is_active": False,
    "channel_id": None,
    "start_time": None,
    "participants": {},  # Format: user_id: { "total_time": float, "join_time": datetime }
    "all_members": set() # To track who hasn't joined at all (Absent)
}

@bot.event
async def on_ready():
    """Triggered when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user} and ready to track attendance.')

@bot.command()
@commands.has_permissions(administrator=True)
async def startmeeting(ctx, channel: discord.VoiceChannel):
    """
    Starts tracking attendance in the specified voice channel.
    Usage: !startmeeting <#channel>
    """
    if active_meeting["is_active"]:
        await ctx.send("A meeting is already active! Please use `!endmeeting` first.")
        return
    
    # Initialize the meeting state
    active_meeting["is_active"] = True
    active_meeting["channel_id"] = channel.id
    active_meeting["start_time"] = datetime.datetime.now(datetime.timezone.utc)
    active_meeting["participants"] = {}
    
    # Gather all members who have access to the text channel where the command was called
    active_meeting["all_members"] = {member.id for member in ctx.channel.members if not member.bot}

    await ctx.send(f"Meeting started in {channel.mention}. Tracking attendance...")

    # Bot joins the voice channel
    try:
        if ctx.voice_client is None:
            await channel.connect()
        else:
            await ctx.voice_client.move_to(channel)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await ctx.send(f"Could not connect to the voice channel: {e}")
        active_meeting["is_active"] = False
        return

    # Track anyone who was already in the voice channel before the meeting started
    now = datetime.datetime.now(datetime.timezone.utc)
    for member in channel.members:
        if not member.bot:
            active_meeting["participants"][member.id] = {
                "total_time": 0.0,
                "join_time": now
            }

@startmeeting.error
async def startmeeting_error(ctx, error):
    """Error handling for invalid input or permissions on !startmeeting."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need Administrator permissions to start a meeting.")
    elif isinstance(error, commands.ChannelNotFound) or isinstance(error, commands.BadArgument):
        await ctx.send("Invalid channel provided. Please mention a valid voice channel.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide a voice channel! Usage: `!startmeeting <#Channel>`")


@bot.command()
@commands.has_permissions(administrator=True)
async def endmeeting(ctx):
    """
    Ends the current meeting, parses tracked data, and sends a final attendance report.
    """
    if not active_meeting["is_active"]:
        await ctx.send("There is no active meeting to end.")
        return

    # Disconnect the bot from the voice channel
    if ctx.voice_client is not None:
        await ctx.voice_client.disconnect()

    end_time = datetime.datetime.now(datetime.timezone.utc)
    meeting_duration_seconds = (end_time - active_meeting["start_time"]).total_seconds()
    required_seconds = meeting_duration_seconds * 0.8
    
    present = []
    late = []
    absent = []

    # Finalize calculations for members who are still in the VC when the meeting ends
    for user_id, data in active_meeting["participants"].items():
        if data["join_time"] is not None:
            time_spent = (end_time - data["join_time"]).total_seconds()
            data["total_time"] += time_spent
            data["join_time"] = None # Reset their active session locally

    # Categorize members based on attendance rules
    for user_id in active_meeting["all_members"]:
        member = ctx.guild.get_member(user_id)
        if member is None:
            continue
            
        name = member.display_name
        
        # If they were tracked joining the meeting
        if user_id in active_meeting["participants"]:
            total_seconds = active_meeting["participants"][user_id]["total_time"]
            total_minutes = int(total_seconds // 60)
            
            # Rule: Present >= 80% of the total meeting time
            if total_seconds >= required_seconds:
                present.append(f"* {name} ({total_minutes} min)")
            # Rule: Late > 0 but < 80% of the total meeting time
            elif total_seconds > 0:
                # Use max of 1 to ensure anyone who stayed > 0s but < 60s gets recognized as having stayed 1 min
                late_mins = max(total_minutes, 1)
                late.append(f"* {name} ({late_mins} min)")
            else:
                # Stayed mathematically 0 seconds, considered absent
                absent.append(f"* {name}")
        else:
            # Rule: Absent = never joined
            absent.append(f"* {name}")

    # Construct the final formatted report
    report_lines = ["📊 Meeting Report\n"]
    
    report_lines.append("✅ Present:")
    if present:
        for p in present:
            report_lines.append(p)
    else:
        report_lines.append("* None")
    
    report_lines.append("\n⚠️ Late:")
    if late:
        for l in late:
            report_lines.append(l)
    else:
        report_lines.append("* None")

    report_lines.append("\n❌ Absent:")
    if absent:
        for a in absent:
            report_lines.append(a)
    else:
        report_lines.append("* None")

    final_report = "\n".join(report_lines)

    # Chunk the report to naturally handle Discord's 2000 character limits on large servers
    chunks = []
    cur_chunk = ""
    for line in final_report.split('\n'):
        if len(cur_chunk) + len(line) + 1 > 1950:
            chunks.append(cur_chunk)
            cur_chunk = line + "\n"
        else:
            cur_chunk += line + "\n"
    if cur_chunk:
        chunks.append(cur_chunk)

    for chunk in chunks:
        await ctx.send(chunk)

    # Clean up and reset state for the next meeting
    active_meeting["is_active"] = False
    active_meeting["channel_id"] = None
    active_meeting["start_time"] = None
    active_meeting["participants"].clear()
    active_meeting["all_members"].clear()

@endmeeting.error
async def endmeeting_error(ctx, error):
    """Error handling for permissions on !endmeeting."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need Administrator permissions to end a meeting.")


@bot.event
async def on_voice_state_update(member, before, after):
    """
    Event hook that triggers automatically when members change their voice state.
    Used to calculate start and stop jointime intervals.
    """
    # Ignore bots and ignore updates if there is no meeting currently running
    if member.bot or not active_meeting["is_active"]:
        return

    channel_id = active_meeting["channel_id"]
    now = datetime.datetime.now(datetime.timezone.utc)

    # Rule: Handle user joining the meeting channel
    if after.channel is not None and after.channel.id == channel_id:
        # Check that they literally moved channels, not just unmuted/deafened themselves
        if before.channel is None or before.channel.id != channel_id:
            # Never joined before
            if member.id not in active_meeting["participants"]:
                active_meeting["participants"][member.id] = {
                    "total_time": 0.0,
                    "join_time": now
                }
            # Rejoining after leaving
            else:
                active_meeting["participants"][member.id]["join_time"] = now

    # Rule: Handle user leaving the meeting channel
    if before.channel is not None and before.channel.id == channel_id:
        if after.channel is None or after.channel.id != channel_id:
            # Safety check: prevent crashes if user somehow leaves without joining properly
            if member.id in active_meeting["participants"]:
                join_time = active_meeting["participants"][member.id].get("join_time")
                if join_time:
                    # Update their total time spent and reset active join time flag
                    time_spent = (now - join_time).total_seconds()
                    active_meeting["participants"][member.id]["total_time"] += time_spent
                    active_meeting["participants"][member.id]["join_time"] = None

import os
from dotenv import load_dotenv

load_dotenv()

# Remember to insert the bot token here
bot.run(os.getenv("DISCORD_TOKEN"))
