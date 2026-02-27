# TamaBotchi

An AI-powered iMessage auto-reply agent. TamaBotchi watches your Mac's Messages app, reads incoming iMessages, generates replies using Claude, and sends them back — automatically.

---

## How It Works

```
Incoming iMessage
      │
      ▼
 chat.db (~/Library/Messages)
      │
      ▼
  watcher.py  ──────────────────────────────►  Agent API (port 5000)
  polls every 3s                                    │
                                                    │  calls Claude
                                                    ▼
                                               Claude AI generates reply
                                                    │
                                                    ▼
  watcher.py  ◄──────────────────────────────  returns reply text
      │
      ▼
iMessage Bridge (port 5001)
      │
      ▼
AppleScript → Messages.app → sends reply
```

**Four services run in parallel:**

| Service | Port | What it does |
|---------|------|-------------|
| Agent API | 5000 | Receives messages, calls Claude, returns reply |
| iMessage Bridge | 5001 | Sends iMessages via AppleScript |
| MCP Server | 5002 | Stores user preferences in SQLite |
| Watcher | — | Polls chat.db, orchestrates the full flow |

---

## Prerequisites

- macOS (iMessage requires it)
- Python 3.12+
- An Anthropic API key ([get one here](https://console.anthropic.com/))
- Full Disk Access granted to Terminal (required to read `chat.db`)
- iMessage configured and signed in on your Mac

### Grant Full Disk Access to Terminal

1. Open **System Settings > Privacy & Security > Full Disk Access**
2. Click **+** and add your terminal app (Terminal.app or iTerm2)
3. Restart your terminal

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Jay-tech456/TamaBotchi.git
cd TamaBotchi
```

### 2. Create virtual environments

Each service has its own venv. Run these from the repo root:

```bash
# Agent API
cd agent && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && deactivate && cd ..

# iMessage Bridge + Watcher
cd imessage-server && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install requests && deactivate && cd ..

# MCP Server
cd mcp-server && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && deactivate && cd ..
```

### 3. Configure environment

Create `agent/.env`:

```bash
touch agent/.env
```

Add your Anthropic API key:

```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-3-5-haiku-20241022
IMESSAGE_SERVER_URL=http://localhost:5001
MCP_SERVER_URL=http://localhost:5002
AGENT_NAME=TamaBotchi
```

---

## Running TamaBotchi

Open **four separate terminal tabs** and run one command per tab, from the repo root.

### Terminal 1 — MCP Server

```bash
cd mcp-server && source .venv/bin/activate && uvicorn main:app --reload --port 5002
```

### Terminal 2 — iMessage Bridge

```bash
cd imessage-server && source .venv/bin/activate && uvicorn server:app --reload --port 5001
```

### Terminal 3 — Agent API

```bash
cd agent && source .venv/bin/activate && uvicorn main:app --reload --port 5000
```

### Terminal 4 — Watcher (starts auto-reply)

```bash
cd imessage-server && source .venv/bin/activate && python watcher.py
```

The watcher will print:

```
============================================================
  TamaBotchi iMessage Auto-Reply Watcher
============================================================

[INFO] Agent API (http://127.0.0.1:5000): UP
[INFO] iMessage Server (http://127.0.0.1:5001): UP
[INFO] Starting from message ROWID XXXXX - will only respond to NEW messages
[INFO] Polling every 3 seconds...
[INFO] Waiting for incoming iMessages...
```

Send yourself an iMessage from another device. Within a few seconds you should see:

```
[INFO] New message from +1xxxxxxxxxx: hey
[INFO] Generating AI response...
[INFO] Sending reply: Hey! ...
[INFO] Reply sent successfully to +1xxxxxxxxxx
```

---

## Configuration

All config lives in `agent/.env`. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-3-5-haiku-20241022` | Claude model to use for replies |
| `IMESSAGE_SERVER_URL` | `http://localhost:5001` | iMessage bridge URL |
| `MCP_SERVER_URL` | `http://localhost:5002` | MCP server URL |
| `AGENT_NAME` | `TamaBotchi` | Name the agent uses in its system prompt |
| `POLL_INTERVAL` | `3` | Seconds between chat.db polls (set in watcher env) |

---

## Project Structure

```
TamaBotchi/
├── agent/                    # Claude AI agent (port 5000)
│   ├── core/
│   │   ├── agent.py          # Main TamaBotchiAgent class + Claude integration
│   │   ├── matching.py       # Interest-based compatibility scoring
│   │   └── permissions.py    # Auto vs ask permission logic
│   ├── tools/
│   │   ├── imessage_tool.py  # iMessage bridge HTTP client
│   │   └── mcp_client.py     # MCP server HTTP client
│   ├── config.py             # Loads settings from .env
│   ├── exceptions.py         # Custom exception hierarchy
│   ├── socius_types.py       # TypedDict type definitions
│   ├── main.py               # FastAPI server entrypoint
│   └── requirements.txt
│
├── imessage-server/          # iMessage bridge + watcher
│   ├── server.py             # FastAPI server (port 5001), sends via AppleScript
│   ├── watcher.py            # Polls chat.db, routes messages through agent
│   └── requirements.txt
│
├── mcp-server/               # User preferences/profile store (port 5002)
│   ├── main.py               # FastAPI server
│   ├── config.py
│   └── requirements.txt
│
└── README.md
```

---

## API Reference

The Agent API (port 5000) exposes these endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check for all services |
| `POST` | `/users/{user_id}/messages/incoming` | Handle incoming message, returns AI reply |
| `POST` | `/users/{user_id}/messages/send` | Send a message on behalf of a user |
| `POST` | `/users/{user_id}/detected` | Trigger outreach when person detected nearby |
| `GET` | `/users/{user_id}/profile` | Get user profile |
| `PATCH` | `/users/{user_id}/profile` | Update user profile |
| `GET` | `/users/{user_id}/preferences` | Get preferences |
| `PATCH` | `/users/{user_id}/preferences` | Update preferences |

---

## Troubleshooting

**"iMessage server returned 500: syntax error"**
Upgrade to the latest version — this was a bug in the AppleScript escaping that has been fixed.

**"Cannot read Messages database"**
Terminal does not have Full Disk Access. See Prerequisites above.

**"Agent API is not running. Start it first."**
The watcher requires all three servers to be up before it starts. Launch Terminals 1–3 first.

**Watcher detects messages but sends no reply**
Check the agent terminal (Terminal 3) for error logs. Most common cause: `ANTHROPIC_API_KEY` not set in `agent/.env`.

**Reply sends to the wrong contact**
The watcher uses the phone number directly from `chat.db`. Make sure numbers in your contacts are in E.164 format (`+1xxxxxxxxxx`).

---

## License

MIT
