# TeleFeed 📡

> **A personalized Telegram feed aggregator.**
> Stop manually searching channels. Define your interests once — TeleFeed watches for you.

---

## What it does

TeleFeed connects to Telegram as **you** (using MTProto via Telethon) and filters messages from channels/groups based on **Areas of Concern** you define in a YAML config file. Each area has keywords, negative keywords, and a description of your intent.

```
┌─────────────────────────────────────────────────────────────┐
│  config.yaml                                                │
│  ─────────────                                              │
│  Area: "Remote Dev Jobs"                                    │
│    keywords: [python, rust, remote, hiring]                 │
│    negative: [internship, unpaid]                           │
│    sources:  [remotejobs, devjobs_channel]                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
               Telethon MTProto
                       │
              ┌────────▼────────┐
              │  TeleFeed CLI   │
              │  ─────────────  │
              │  fetch          │  ← pull history
              │  fetch --live   │  ← real-time watch
              │  show-matches   │  ← view saved results
              └─────────────────┘
```

---

## Quick Start

### 1. Get Telegram API credentials

1. Go to **https://my.telegram.org** and log in.
2. Click **"API development tools"**.
3. Create a new app (name doesn't matter).
4. Copy your **`api_id`** and **`api_hash`**.

### 2. Set up the project

```bash
cd telefeed

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

### 3. Configure credentials

```bash
cp .env.example .env
# Edit .env with your api_id, api_hash, and phone number
```

### 4. Configure your areas of concern

Edit **`config.yaml`** to add the channels you want to watch and the keywords that matter to you.

### 5. Authenticate

```bash
telefeed auth
# or: python -m telefeed auth
```

You'll receive an OTP on Telegram. Enter it when prompted. Your session is saved — you won't need to log in again.

### 6. Fetch & filter

```bash
# Pull recent messages and show matches
telefeed fetch

# Pull only the last 200 messages per channel
telefeed fetch --limit 200

# Watch in real-time (Ctrl-C to stop)
telefeed fetch --live

# Only run one specific area
telefeed fetch --area "Remote Dev Jobs"

# Show previously saved matches
telefeed show-matches
telefeed show-matches --area "Remote Dev Jobs" --status new
```

---

## Project structure

```
telefeed/
├── .env                  # Your credentials (git-ignored)
├── .env.example          # Template
├── config.yaml           # Areas of concern
├── pyproject.toml
├── requirements.txt
└── telefeed/
    ├── __init__.py
    ├── __main__.py       # python -m telefeed
    ├── cli.py            # Click CLI commands
    ├── client.py         # Telethon wrapper
    ├── filters.py        # Keyword matching engine
    ├── store.py          # SQLite persistence
    └── display.py        # Rich terminal output
```

---

## How the filtering works

1. **Keyword gate** — any message containing at least one keyword in an area is a candidate.
2. **Negative keyword gate** — if a message contains any negative keyword, it is immediately discarded.
3. **Relevance score** — `matched_keywords / total_keywords` gives a 0–100% score shown in the terminal.

> **Coming in Phase 2:** AI-powered semantic matching using Gemini, triggered by `--smart` flag.

---

## Privacy & security

- Your credentials are stored in `.env` and the session in `telefeed.session`. **Never commit these to git.**
- TeleFeed logs in as your user account (not a bot). It has the same access level as you do manually.
- All data stays local (SQLite file). Nothing is sent to external servers by TeleFeed itself.

---

## .gitignore recommendation

Add these to `.gitignore`:

```
.env
*.session
telefeed.db
__pycache__/
.venv/
*.egg-info/
```
