# Telegram PDF → Markdown (via OpenDataLoader)

A self-hosted [n8n](https://n8n.io) workflow that receives a **PDF or image** in Telegram, converts it to Markdown using [OpenDataLoader PDF](https://github.com/opendataloader-project/opendataloader-pdf), and sends the result back as a `.md` file — with images embedded inline as base64 so the output is fully self-contained.

- **PDFs** are converted by the opendataloader-pdf CLI, with the docling hybrid backend (`--hybrid docling-fast`) for more accurate layout/table extraction.
- **Images** (PNG, JPEG, TIFF, BMP, WebP — sent as a photo or as a file) are OCR'd by the docling hybrid backend (RapidOCR) and returned as Markdown, including detected tables.

---

## How It Works

```
You (Telegram)
    │  send PDF or image (photo or file)
    ▼
Telegram Trigger (n8n webhook)
    │
    ├─ not your chat ID → silent drop
    │
    ├─ unsupported type → "Please send a PDF or image"
    │
    ▼
"⏳ Converting…" acknowledgement sent
    │
    ▼
Telegram getFile API → download URL
(documents use file_id; photos use the largest size variant)
    │
    ▼
Code node (async execFile → Python)
    ├─ downloads the file from Telegram
    └─ POSTs to opendataloader sidecar (port 5002)
       with the file's real Content-Type
              │
              ▼
       /convert branches on content type:
       ├─ PDF   → opendataloader-pdf CLI (Java, local)
       │          + docling hybrid backend for layout/tables
       │          → images embedded as base64 data URIs
       └─ image → docling hybrid backend (port 5003, internal)
                  → RapidOCR + layout/table detection
                  → DoclingDocument → Markdown
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
├── Dockerfile.opendataloader   # opendataloader-pdf sidecar (Ubuntu 22.04 + Python 3.11 + Java JRE + docling hybrid)
├── server.py                   # Flask HTTP API: PDF → CLI, image → docling hybrid backend
├── start.sh                    # Sidecar entrypoint: starts hybrid backend (port 5003) then Flask (5002)
├── sitecustomize.py            # Optional: routes onnxruntime through OpenVINO (Intel iGPU) when OPENVINO_DEVICE is set
├── runner-start.sh             # Only for external task-runner deployments: fetches grant token, starts runner
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

Then open the imported workflow and update the four Telegram nodes (Trigger, Acknowledge, Send File, Unsupported File) to use your new credential.

### 7. Set your authorized chat ID (required)

The **IF: Authorized?** node is pre-set to `0`, which blocks everyone. You must replace it with your own Telegram chat ID before the bot will respond to you:

1. Send any message to your bot in Telegram
2. In n8n, open the workflow execution log and find `message.chat.id` in the trigger output
3. Open the **IF: Authorized?** node and replace `0` with your chat ID number

Only messages from this chat ID will be processed; all others are silently dropped.

### 8. Activate

Toggle the workflow to **Active** in the top-right of the n8n editor.

Send a PDF or an image to your bot — you should receive a `.md` file back. Hybrid-mode PDF conversions typically take 20–40 seconds.

> **Tip for images:** send them as a *file attachment* rather than a photo when possible — Telegram recompresses photos, and OCR/table detection quality depends heavily on resolution.

---

## Dependencies

### opendataloader sidecar (`Dockerfile.opendataloader`)

| Package | Purpose |
|---|---|
| `ubuntu:22.04` + deadsnakes Python 3.11 | Base image (Ubuntu needed for the Intel GPU compute runtime) |
| `default-jre-headless` | Required by the opendataloader-pdf Java core |
| `opendataloader-pdf[hybrid]` (PyPI) | PDF → Markdown CLI + docling hybrid backend server |
| `rapidocr-onnxruntime` (PyPI) | OCR engine used by the hybrid backend |
| `onnxruntime-openvino` (PyPI) | Optional: OCR inference on Intel iGPU via OpenVINO |
| `intel-opencl-icd` (apt) | Optional: Intel GPU compute runtime (Level Zero/OpenCL) |
| `flask` (PyPI) | Lightweight HTTP server wrapping the CLI |

**GPU acceleration is optional.** It only activates when the container has `OPENVINO_DEVICE=GPU` set and an Intel iGPU mapped in (`devices: /dev/dri/renderD128`). Without it, everything falls back to CPU automatically. Note that only OCR runs on the GPU — docling's layout/table models are PyTorch and always run on CPU, so don't expect much visible GPU utilization.

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
| `NODE_FUNCTION_ALLOW_BUILTIN=child_process` | Yes | Allows the Code node to call Python via `child_process.execFile` |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | Yes | Allows `$env[...]` expressions in HTTP Request node URLs |

---

## Sidecar API

The `opendataloader` container exposes a minimal HTTP API (internal only, not published to the host):

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/convert` | Raw PDF bytes (`Content-Type: application/pdf`) **or** raw image bytes (`Content-Type: image/*`) | Markdown text |
| `GET` | `/health` | — | `ok` (200) |

`/convert` branches on the request Content-Type (with a magic-byte fallback for missing/incorrect headers):

- **PDF** → opendataloader-pdf CLI with the docling hybrid backend. Images extracted from the PDF are embedded into the Markdown as `data:image/...;base64,...` URIs, so the `.md` file is fully self-contained.
- **Image** → forwarded to the docling hybrid backend (`localhost:5003`, container-internal), which runs OCR + layout/table detection; the resulting `DoclingDocument` is exported to Markdown via `docling-core`. Returns `422` if no text is recognized.

---

## Troubleshooting

**"access to env vars denied" in HTTP nodes**
→ Add `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` to the n8n environment in `docker-compose.yml`.

**Code node error: `Module 'http' is disallowed`**
→ n8n's Code node sandbox blocks `require('http')` even with `NODE_FUNCTION_ALLOW_BUILTIN=http`. Use `child_process` with Python instead (already done in this workflow).

**"Task execution aborted because runner became unresponsive"**
→ The Code node must use **async `execFile`, never `spawnSync`**. With external task runners, a synchronous call blocks the runner's event loop, so it misses its broker heartbeats during long conversions and n8n kills the task — typically at the exact moment the conversion finishes. The workflow in this repo already uses async `execFile`.

**Tables in images come back as plain text (no Markdown table)**
→ Resolution problem, not a pipeline problem. The layout model needs enough pixels to detect table structure — roughly 1000px of width for a typical table. Send images as a *file* (Telegram recompresses photos), and use a high-resolution source. OCR typos like `p0rts` for `ports` are a telltale sign the image is too small.

**`RapidOCR returned empty result!` warning in sidecar logs**
→ Benign. docling runs OCR over each bitmap region it finds in a page (logos, decorative images); regions with no readable text produce this warning. Only worry if a scanned, image-only document comes back mostly empty.

**GPU graph shows no utilization despite OpenVINO setup**
→ Expected. Only RapidOCR inference runs on the iGPU, in short bursts (the GPU power-gates between them, so monitoring graphs round to zero); the layout/table models are PyTorch on CPU. To verify GPU is really working, watch `/sys/class/drm/card0/gt_act_freq_mhz` during a conversion with lots of OCR — it should jump from 0 to max frequency.

**Converted PDF has only 9 bytes**
→ n8n 2.x stores large binary data on disk as a filesystem reference — `item.binary.data.data` is not the actual file. The Code node works around this by re-downloading the PDF directly from Telegram using Python's `urllib`.

**Images in the output are broken links**
→ Make sure you are running the current `server.py` (which embeds images as base64). Rebuild the sidecar: `docker compose up -d --build opendataloader`.

**opendataloader takes a long time to start**
→ Normal — the docling hybrid backend loads its models on startup, then the Java JRE cold-starts on first request. The healthcheck polls every 15s with a 120s grace period. n8n waits for healthy status before starting.
