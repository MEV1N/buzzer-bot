# Buzzer Bot — Setup Guide

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure your `.env` file
```
DISCORD_TOKEN=your_bot_token
OWNER_ID=your_discord_user_id        # Right-click name → Copy User ID
LOG_CHANNEL_ID=mod_log_channel_id    # Optional
REMINDER_INTERVAL_SECS=60            # Optional, default 60
```

### 3. Run the bot
```bash
python buzzer.py
```

The SQLite database (`database/buzzer.db`) is created automatically on first run.

---

## Slash Commands

> Slash commands sync globally on startup. **It can take up to 1 hour** for them to appear everywhere.  
> For instant testing, uncomment the `GUILD_ID` lines in `buzzer.py → setup_hook()`.

### XP / Leveling
| Command | Description | Who |
|---|---|---|
| `/rank [user]` | Show XP rank card | Anyone |
| `/leaderboard [limit]` | Top XP earners | Anyone |

### Moderation
| Command | Description | Who |
|---|---|---|
| `/warn @user reason` | Issue a warning | Admin+ |
| `/mute @user duration reason` | Timeout a member | Admin+ |
| `/kick @user reason` | Kick a member | Admin+ |
| `/ban @user reason` | Ban a member | Owner only |
| `/resetxp @user` | Reset user XP to 0 | Owner only |
| `/promote @user` | Make user a Core Admin | Owner only |
| `/demote @user` | Remove Core Admin role | Owner only |
| `/deletetask taskId` | Delete a task permanently | Owner only |

### Task Management
| Command | Description | Who |
|---|---|---|
| `/task assign @user title due:<time> remind:<interval>` | Assign a task | Admin+ |
| `/task update taskId message` | Post a status update | Assignee/Admin |
| `/task complete taskId proof:<url>` | Mark done with proof | Assignee only |
| `/task my` | List your assigned tasks | Anyone |

### Attendance (prefix commands)
| Command | Description | Who |
|---|---|---|
| `!startmeeting #channel` | Start attendance tracking | Discord Admin |
| `!endmeeting` | End meeting & print report | Discord Admin |

---

## Permission Hierarchy

```
Owner  (OWNER_ID env var)
  └── Full control of all commands

Admin  (/promote @user)
  └── /warn, /mute, /kick, /task assign

Member (default)
  └── /rank, /leaderboard, /task my, /task update (own tasks), /task complete (own tasks)
```

---

## Time Formats
All duration arguments accept: `30s`, `10m`, `2h`, `1d`, `1w`

---

## Required Bot Permissions
- **Send Messages**, **Embed Links**, **Read Message History**
- **Moderate Members** (for `/mute` timeout)
- **Kick Members**, **Ban Members**
- **View Channels**

---

## Project Structure
```
meeting/
├── buzzer.py          ← Main entry point
├── .env               ← Your secrets
├── requirements.txt
├── cogs/
│   ├── attendance.py  ← !startmeeting / !endmeeting
│   ├── xp.py          ← /rank, /leaderboard, XP listener
│   ├── moderation.py  ← /warn, /mute, /kick, /ban, etc.
│   └── tasks.py       ← /task commands + reminder scheduler
├── database/
│   ├── db.py          ← SQLite init + connection helper
│   └── buzzer.db      ← Auto-created on first run
└── utils/
    ├── embeds.py      ← Shared embed builders
    └── time_parser.py ← "2h" → seconds converter
```
