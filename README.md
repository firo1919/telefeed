# TeleFeed 📡

**A personalized Telegram feed aggregator.**
Stop manually searching channels. Define your interests once — TeleFeed watches for you in the background and notifies you of key updates.

---

## Features

- 🎯 **Areas of Concern**: Group keywords, negative keywords, and semantic intent into named topic areas.
- ⚡ **Auto-Discovery**: Automatically scans all broadcast channels and supergroups you subscribe to on Telegram.
- 🤖 **Multi-Provider AI Matching**: Optional smart semantic matching powered by your choice of AI provider — Gemini, OpenAI, Anthropic Claude, local Ollama models, or OpenRouter.
- 🖥️ **Desktop OS Notifications**: Native popup alerts on Linux, macOS, and Windows when relevant posts match.
- 💬 **Telegram Bot Push Alerts**: Direct notifications forwarded to your Telegram user chat via a Telegram bot.
- ⚙️ **Background Service**: Easily install and run as an automated user daemon.
- 🌐 **Modern Web Dashboard**: Configure everything, authenticate, and view your live feed in a beautiful web interface.
- 📦 **Single Config File**: all credentials, notification rules, and topic filters live in `config.yaml`.

---

## Quick Start

### 1. Installation

The easiest way to install TeleFeed and its dependencies securely is via `pipx`:

```bash
pipx install telefeed
```

_Alternatively, you can install via standard pip: `pip install telefeed`_

**Local editable install (development):**

```bash
git clone https://github.com/firo1919/telefeed.git
cd telefeed
pipx install -e .
```

### 2. Initialize Configuration

```bash
telefeed init
```

This creates `~/.config/telefeed/config.yaml`.

---

### 3. Start the Web Dashboard & Setup

You can configure everything, authenticate with Telegram, and view your feed directly from the Web UI:

```bash
telefeed web
```

Open `http://127.0.0.1:8000` in your browser. From here, you can:

- Enter your Telegram API credentials and log in securely.
- Setup your AI Provider (Gemini, OpenAI, Anthropic, Ollama).
- Add the specific "Areas" (topics/keywords) you want to track.
- Enable desktop or Telegram Bot push notifications.
- Start the background service.

_Note: You can also configure everything manually by editing `~/.config/telefeed/config.yaml` and running `telefeed auth` in your terminal._

---

### 5. Validate setup

```bash
telefeed doctor
```

---

## CLI Usage

```bash
# Launch the interactive web dashboard (Recommended)
telefeed web

# Pull recent messages and print matches to terminal
telefeed fetch

# Watch in real-time with notifications enabled
telefeed fetch --live --notify

# Use keyword matching only (skip AI)
telefeed fetch --no-ai

# Restrict to a single area
telefeed fetch --area "Remote Dev Jobs"

# Show previously saved matches from database
telefeed show-matches
```

---

## Running in Background on Linux & Windows

TeleFeed includes built-in commands to manage a background service (`systemd` on Linux, Startup VBScript on Windows):

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
├── pyproject.toml
├── ui/                   # Vue/Vite frontend source code (HTML/CSS/JS)
└── telefeed/
    ├── __main__.py       # python -m telefeed entry point
    ├── cli.py            # Click CLI commands & service actions
    ├── client.py         # Telethon MTProto wrapper
    ├── config.py         # XDG path resolver & YAML config loader
    ├── engine.py         # Live feed processing engine
    ├── ai_filter.py      # Multi-provider AI scorer (Gemini, OpenAI, Anthropic, Ollama)
    ├── notifications.py  # OS desktop notifications & Telegram Bot API push
    ├── service.py        # Systemd/Windows service installer & manager
    ├── store.py          # SQLite persistence layer
    └── web/              # FastAPI backend
        └── server.py     # Web endpoints, WebSockets, and static file serving
```
