# TeleFeed 📡

> **A personalized Telegram feed aggregator.**
> Stop manually searching channels. Define your interests once — TeleFeed watches for you in the background and notifies you of key updates.

---

## Features

- 🎯 **Areas of Concern**: Group keywords, negative keywords, and semantic intent into named topic areas.
- ⚡ **Auto-Discovery**: Automatically scans all broadcast channels and supergroups you subscribe to on Telegram.
- 🤖 **AI Matching (Gemini)**: Optional smart semantic matching using Google Gemini 2.5 Flash (`--smart` or `matcher: ai`).
- 🖥️ **Desktop OS Notifications**: Native popup alerts on Linux, macOS, and Windows when relevant posts match.
- 💬 **Telegram Bot Push Alerts**: Direct notifications forwarded to your Telegram user chat via a Telegram bot.
- ⚙️ **Background Systemd Service**: Easily install and run as an automated `systemd` user daemon.
- 📦 **Single Config File**: Zero `.env` files — all credentials, notification rules, and topic filters live in `config.yaml`.

---

## Quick Start

### 1. Installation

Install via `pipx` (recommended for CLI tools):

```bash
pipx install git+https://github.com/firo1919/telefeed.git
```

Or install locally in editable mode:

```bash
pip install -e .
```

### 2. Initialize Configuration

Initialize your configuration file:

```bash
telefeed init
```

This creates `~/.config/telefeed/config.yaml` (following XDG standards).

### 3. Add Telegram Credentials

Edit `~/.config/telefeed/config.yaml` to add your Telegram credentials from [my.telegram.org/apps](https://my.telegram.org/apps):

```yaml
matcher: ai
ai_threshold: 65

telegram:
  api_id: 12345678
  api_hash: "your_api_hash_here"
  phone: "+1234567890"

gemini:
  api_key: "your_gemini_api_key_here"

notifications:
  desktop: true
  telegram_bot:
    enabled: false
    bot_token: ""
    chat_id: ""
```

### 4. Authenticate

```bash
telefeed auth
```

Enter your Telegram OTP code when prompted. The session is saved to `~/.config/telefeed/telefeed.session`.

### 5. Validate setup with `doctor`

```bash
telefeed doctor
```

---

## Usage

```bash
# Pull recent messages and print matches
telefeed fetch

# Watch in real-time with notifications enabled
telefeed fetch --live --notify

# Restrict to a single area
telefeed fetch --area "Remote Dev Jobs"

# Show previously saved matches from database
telefeed show-matches
```

---

## Running in Background (`systemd`)

TeleFeed includes built-in commands to manage a background `systemd` user service:

```bash
# Install and enable background service (runs `telefeed fetch --live --notify`)
telefeed service install

# Check service status
telefeed service status

# Tail live service logs
telefeed service logs

# Stop or restart service
telefeed service stop
telefeed service restart

# Uninstall service
telefeed service uninstall
```

---

## Project Structure

```
telefeed/
├── config.yaml           # Default configuration template
├── pyproject.toml
└── telefeed/
    ├── __init__.py
    ├── __main__.py       # python -m telefeed
    ├── cli.py            # Click CLI commands & service actions
    ├── client.py         # Telethon MTProto wrapper
    ├── config.py         # XDG path resolver & YAML config loader
    ├── display.py        # Rich terminal UI rendering
    ├── filters.py        # Pure keyword matching engine
    ├── ai_filter.py      # Gemini 2.5 Flash semantic scoring
    ├── notifications.py  # OS desktop notifications & Telegram Bot API push
    ├── service.py        # Systemd user service installer & manager
    └── store.py          # SQLite persistence layer
```

---

## License

MIT
