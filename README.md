# Telegram PDF → Markdown (via OpenDataLoader)

A self-hosted [n8n](https://n8n.io) workflow that receives a PDF file in Telegram, converts it to Markdown using [OpenDataLoader PDF](https://github.com/opendataloader-project/opendataloader-pdf), and sends the result back as a `.md` file — with images embedded inline as base64 so the output is fully self-contained.

---

## How It Works

```
You (Telegram)
    │  send PDF
    ▼
Telegram Trigger (n8n webhook)
    │
    ├─ not your chat ID → silent drop
    │
    ├─ not a PDF → "Please send a PDF file"
    │
    ▼
"⏳ Converting…" acknowledgement sent
    │
    ▼
Telegram getFile API → download URL
    │
    ▼
Code node (Python via child_process)
    ├─ downloads PDF from Telegram
    └─ POSTs to opendataloader sidecar (port 5002)
              │
              ▼
       opendataloader-pdf CLI
       (Java-based, runs locally)
              │
              ▼
       Markdown + extracted images
       → images embedded as base64 data URIs
              │
    ◄─────────┘
    │
    ▼
Telegram sends back .md file attachment
```

The conversion runs entirely on your own machine — no cloud APIs, no data leaves your server.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Docker Compose v2 | `docker compose version` |
| A public HTTPS URL for n8n | Use [ngrok](https://ngrok.com) for local testing, or a reverse proxy + domain for permanent deploys |
| Telegram bot token | Create one via [@BotFather](https://t.me/BotFather) |

---

## Project Structure

```
.
├── Dockerfile.n8n              # n8n (stock image + Python 3)
├── Dockerfile.opendataloader   # opendataloader-pdf sidecar (Python 3.11 + Java JRE + Flask)
├── server.py                   # Flask HTTP API wrapping the opendataloader-pdf CLI
├── docker-compose.yml          # Orchestrates both containers
├── .env.example                # Environment variable template
└── telegram-pdf-to-markdown.n8n.json   # Importable n8n workflow
```

---

## Setup

### 1. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:AABBcc...`)

### 2. Clone the repo

```bash
git clone https://github.com/thitipatj/telegrambot-pdf2md-opendataloader
cd telegrambot-pdf2md-opendataloader
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
TELEGRAM_BOT_TOKEN=123456789:AABBCCDDEEFFaabbccddeeff...
WEBHOOK_URL=https://your-public-url.com/
N8N_ENCRYPTION_KEY=<output of: openssl rand -hex 32>
GENERIC_TIMEZONE=Asia/Bangkok
```

> For local testing, run `ngrok http 5678` and use the `https://` URL it gives you as `WEBHOOK_URL`.

### 4. Deploy

```bash
docker compose up -d --build
```

The `opendataloader` container takes ~60 seconds to become healthy on first start (Java JRE initialisation). n8n waits for it before starting.

```bash
# Check both containers are up
docker compose ps

# Watch opendataloader startup
docker logs -f opendataloader
```

### 5. Import the n8n workflow

1. Open n8n at `http://localhost:5678`
2. Complete the first-run setup (create an account)
3. Go to **Workflows → Import from file**
4. Select `telegram-pdf-to-markdown.n8n.json`

### 6. Configure the Telegram credential

1. In n8n go to **Settings → Credentials → Add credential**
2. Search for **Telegram** and select it
3. Paste your bot token
4. Save

Then open the imported workflow and update the four Telegram nodes (Trigger, Acknowledge, Send File, Not a PDF) to use your new credential.

### 7. Set your authorized chat ID (required)

The **IF: Authorized?** node is pre-set to `0`, which blocks everyone. You must replace it with your own Telegram chat ID before the bot will respond to you:

1. Send any message to your bot in Telegram
2. In n8n, open the workflow execution log and find `message.chat.id` in the trigger output
3. Open the **IF: Authorized?** node and replace `0` with your chat ID number

Only messages from this chat ID will be processed; all others are silently dropped.

### 8. Activate

Toggle the workflow to **Active** in the top-right of the n8n editor.

Send a PDF to your bot — you should receive a `.md` file back within a few seconds.

---

## Dependencies

### opendataloader sidecar (`Dockerfile.opendataloader`)

| Package | Purpose |
|---|---|
| `python:3.11-slim` | Base image |
| `default-jre-headless` | Required by the opendataloader-pdf Java core |
| `opendataloader-pdf` (PyPI) | PDF → Markdown conversion CLI |
| `flask` (PyPI) | Lightweight HTTP server wrapping the CLI |

### n8n container (`Dockerfile.n8n`)

| Package | Purpose |
|---|---|
| `n8nio/n8n:latest` | Base n8n image (Node.js 20, Alpine) |
| `python3` (apk) | Required by the Code node to call the sidecar |

### n8n workflow env vars

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Loaded via `.env`, accessed in workflow as `$env['TELEGRAM_BOT_TOKEN']` |
| `WEBHOOK_URL` | Yes | Public URL n8n registers with Telegram for webhook delivery |
| `N8N_ENCRYPTION_KEY` | Yes | Encrypts stored credentials |
| `NODE_FUNCTION_ALLOW_BUILTIN=child_process` | Yes | Allows the Code node to call Python via `child_process.spawnSync` |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | Yes | Allows `$env[...]` expressions in HTTP Request node URLs |

---

## Sidecar API

The `opendataloader` container exposes a minimal HTTP API (internal only, not published to the host):

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/convert` | Raw PDF bytes (`Content-Type: application/pdf`) | Markdown text with images embedded as base64 `data:` URIs |
| `GET` | `/health` | — | `ok` (200) |

Images extracted by opendataloader-pdf are automatically embedded into the Markdown as `data:image/...;base64,...` URIs before the response is returned, so the `.md` file is fully self-contained.

---

## Troubleshooting

**"access to env vars denied" in HTTP nodes**
→ Add `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` to the n8n environment in `docker-compose.yml`.

**Code node error: `Module 'http' is disallowed`**
→ n8n's Code node sandbox blocks `require('http')` even with `NODE_FUNCTION_ALLOW_BUILTIN=http`. Use `child_process.spawnSync` with Python instead (already done in this workflow).

**Converted PDF has only 9 bytes**
→ n8n 2.x stores large binary data on disk as a filesystem reference — `item.binary.data.data` is not the actual file. The Code node works around this by re-downloading the PDF directly from Telegram using Python's `urllib`.

**Images in the output are broken links**
→ Make sure you are running the current `server.py` (which embeds images as base64). Rebuild the sidecar: `docker compose up -d --build opendataloader`.

**opendataloader takes a long time to start**
→ Normal — the Java JRE cold-starts on first request. The healthcheck polls every 15s with a 60s grace period. n8n waits for healthy status before starting.
