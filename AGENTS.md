# Agent notes

## Cursor Cloud specific instructions

### What this repo is
Python Telegram bot (`python-telegram-bot`) that stores chat messages in PostgreSQL and calls an OpenAI-compatible API (plus Serper for search).

### Required secrets
Configure these in the Cloud Agents Secrets tab (or a local `.env` — see `.env.example`):

- `BOT_TOKEN` — Telegram bot token from @BotFather
- `DATABASE_URL` — Postgres DSN (local default: `postgresql://fiveguys:fiveguys@localhost:5432/fiveguys`)
- `MODEL` — model name for the AI provider
- `API_KEY` — AI provider API key
- `BASE_URL` — AI provider base URL
- `SERPER_API_KEY` — Serper.dev key used by tool-calling search

Without real `BOT_TOKEN` / AI keys, `python3 main.py` will initialize Postgres then fail when contacting Telegram/OpenAI. Use `python3 scripts/verify_env.py` to confirm local infra without external APIs.

### Local services
- Postgres is started by `.cursor/setup_db.sh` (also wired into `environment.json` `start`).
- Default local DB: user/password/db = `fiveguys` / `fiveguys` / `fiveguys` on `localhost:5432`.

### Useful commands
```bash
bash .cursor/setup_db.sh
python3 scripts/verify_env.py
python3 main.py
```

### Offline demo (no real BotFather token)
```bash
# terminal 1
python3 scripts/mock_telegram_api.py --port 8089

# terminal 2
TELEGRAM_API_BASE=http://127.0.0.1:8089/bot python3 main.py
```
