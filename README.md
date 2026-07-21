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
- ⚙️ **Background Systemd Service**: Easily install and run as an automated `systemd` user daemon.
- 📦 **Single Config File**: Zero `.env` files — all credentials, notification rules, and topic filters live in `config.yaml`.

---

## Quick Start

### 1. Installation

```bash
pip install git+https://github.com/firo1919/telefeed.git
```

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

### 3. Configure Credentials & AI Provider

Edit `~/.config/telefeed/config.yaml`:

```yaml
matcher: ai # 'keywords' or 'ai'
ai_threshold: 65 # relevance threshold 0-100

telegram:
    api_id: 12345678
    api_hash: "your_api_hash_here"
    phone: "+1234567890"

# AI provider — pick one:
ai:
    provider: gemini # gemini | openai | anthropic | ollama | openrouter
    model: gemini-2.5-flash # leave blank to use the default model for the provider
    api_key: "your_api_key_here" # not required for Ollama
    base_url: "" # override endpoint, e.g. http://localhost:11434/v1 for Ollama

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

Enter your Telegram OTP when prompted. The session is saved to `~/.config/telefeed/telefeed.session`.

---

### 5. Validate setup

```bash
telefeed doctor
```

---

## CLI Usage

```bash
# Pull recent messages and print matches
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

## Running in Background (`systemd`) on Linux

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
├── pyproject.toml
└── telefeed/
    ├── __init__.py
    ├── __main__.py       # python -m telefeed entry point
    ├── cli.py            # Click CLI commands & service actions
    ├── client.py         # Telethon MTProto wrapper
    ├── config.py         # XDG path resolver & YAML config loader
    ├── display.py        # Rich terminal UI rendering
    ├── filters.py        # Pure keyword matching engine
    ├── ai_filter.py      # Multi-provider AI scorer (Gemini, OpenAI, Anthropic, Ollama)
    ├── notifications.py  # OS desktop notifications & Telegram Bot API push
    ├── service.py        # Systemd user service installer & manager
    └── store.py          # SQLite persistence layer
```

---

## Development

```bash
git clone https://github.com/firo1919/telefeed.git
cd telefeed

# Create a venv for dev tools (tests, linting) — separate from the pipx install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"

# Run tests
pytest tests/ -v
```
