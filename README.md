# Five Guys Summarize Telegram Bot 🤖

A witty Hong Kong Cantonese Telegram bot that brings the spirit of LIHKG discussion forums to your group chats. It summarizes conversations, answers questions, chats in threads, and runs entertainment commands—all with authentic Hong Kong internet culture flavor.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)

## ✨ Features

### 🎯 Core Functions
- **Daily Chat Summarization**: AI summaries of group conversations (time-range queries from PostgreSQL)
- **User-Specific Summaries**: Analyze what specific users have been talking about
- **Golden Quote King**: Find the most interesting/funny speaker of the day
- **Group chat AI**: Mention or reply to the bot for threaded Cantonese chat (daily usage cap)
- **Smart Q&A (`/ask`)**: Factual answers with optional web search (Serper) and tool loop

### 🎪 Entertainment Features
- **Compliment Generator**: Personalized compliments for users
- **Love Quote Generator**: Cheesy pickup lines (土味情話) in Cantonese
- **Apology Generator**: Humorous apologies featuring 五仁月餅 references
- **Roast Function**: Playful `diu` responses for friendly banter

### ⛡️ Safety Harness (Jev)
- **Input gate**: Blocks harmful user turns before the reply model runs (fail-closed)
- **Search gate**: Blocks unsafe model-generated search queries before they leave the process
- **Layered prompts**: Chat handles self-harm helpline copy; Jev focuses on actionable harm, jailbreaks, and secrets—not crisis counseling

### ⏰ Utility Features
- **Work / retirement countdowns**: Hong Kong timezone (HKT)
- **Timezone-aware AI**: Current Hong Kong datetime is prepended to chat and `/ask` system prompts at request time

## 🏛️ Architecture & Design

The bot splits into **two AI paths** that intentionally do not share the same prompts or memory model:

| Path | Trigger | History | Model tools | Jev gates |
|------|---------|---------|-------------|-----------|
| **Summarize & fun commands** | `/summarize`, `/compliment`, `/love`, etc. | Pasted transcript blob from DB time range | None | No |
| **Thread chat** | `@bot` mention or reply | Last ~20 user/assistant turns per thread | None | Input gate |
| **`/ask`** | `/ask …` | Same thread store as chat | `search_with_serper` | Input + search gate |

**Design choices**

1. **Two voices, two prompts** — `AI_CHAT_SYSTEM_PROMPT` is the group personality; `AI_ANSWER_SYSTEM_PROMPT` is the factual answerer. They stay separate; only both get shorter copy and a HK datetime line in code.
2. **Thread memory vs summarize** — Interactive chat uses real message turns in PostgreSQL (`resolve_thread_id`, `get_thread_messages`). Summarize commands still load raw messages for a time window and pass one big string to `get_ai_summary` with the legacy summary prompts (unchanged).
3. **Fail-closed Jev** — Missing OpenRouter key, timeout, or SDK error ⇒ treat as reject for the **input** gate only; user sees `呢條我答唔到。` and daily quota is not consumed on chat.
4. **Context-aware input gate** — Jev sees only `previous_assistant` + current `user` line, so innocuous follow-ups like “turn that story into real steps” are judged with the prior bot reply, not the new sentence alone.
5. **Search gate is soft** — A blocked Serper query returns a tool message; the model finishes the turn without calling Google. Only the input gate rejects the whole user message.
6. **No eval on tool args** — Search queries are gated as plain text; unknown tool names are ignored.

### High-level component diagram

```mermaid
flowchart TB
    TG[Telegram update]
    MAIN[main.py handlers]

    TG --> MAIN

    MAIN --> SUM[summarize.py / compliment / love / …]
    MAIN --> CHAT[ai_chat.handle_chat]
    MAIN --> ASK[main.answer /ask]

    SUM --> DB[(PostgreSQL messages)]
    SUM --> AI_SUM[ai.get_ai_summary]

    CHAT --> DB
    CHAT --> JEV_IN[jev_gate.allow_user_turn]
    JEV_IN -->|allow| AI_CHAT[ai.get_ai_chat_response]

    ASK --> DB
    ASK --> JEV_IN
    JEV_IN -->|allow| AI_ASK[ai.get_ai_answer_with_tools]

    AI_CHAT --> LLM[(OpenAI-compatible chat API)]
    AI_ASK --> LLM
    AI_ASK --> SERPER[Serper API]

    JEV_IN --> JEV[(Jev via OpenRouter typesafe/jev-1.13)]
    AI_ASK --> JEV_Q[jev_gate.allow_user_text on query]
    JEV_Q -->|allow| SERPER
    JEV_Q -->|refuse| TOOL_MSG[tool result: search refused]
    TOOL_MSG --> LLM
```

### Input gate (mention, reply, `/ask`)

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot handler
    participant DB as Thread DB
    participant J as Jev gate
    participant M as Reply model

    U->>B: message /ask
    B->>DB: resolve thread, load history
    B->>B: previous_assistant = last assistant turn
    B->>J: allow_user_turn(user, previous_assistant)
    alt noul ≥ threshold or Jev error
        J-->>B: reject
        B-->>U: GATE_REJECT_REPLY (no quota)
    else allow
        J-->>B: ok
        B->>M: system prompt + HK time + history
        M-->>U: Cantonese reply
    end
```

State sent to Jev (text `state` for TypeSafe):

```text
previous_assistant: <last assistant content, or empty>
user: <current user text>
```

### Search gate (`/ask` tool loop only)

```mermaid
sequenceDiagram
    participant M as Reply model
    participant A as ai.py tool branch
    participant J as Jev allow_user_text
    participant S as Serper

    M->>A: tool_call search_with_serper(query)
    A->>J: gate query string
    alt unsafe query
        J-->>A: reject
        A->>M: "Search refused by safety gate. Answer without this search."
    else safe
        J-->>A: allow
        A->>S: HTTP search
        S-->>M: formatted snippets
    end
    M-->>M: final answer (may iterate ≤ max_iterations)
```

### Key modules

| File | Role |
|------|------|
| `main.py` | Application wiring, `/ask`, countdowns, registers handlers |
| `ai_chat.py` | Mention/reply handler, daily limit, thread attach, input gate |
| `jev_gate.py` | `allow_user_turn`, `allow_user_text`, OpenRouter Jev client |
| `ai.py` | Chat completion, Serper search, tool loop, HK datetime on system prompts |
| `config.py` | Tokens, `AI_CHAT_SYSTEM_PROMPT`, `AI_ANSWER_SYSTEM_PROMPT`, Jev thresholds |
| `database.py` / `db.py` | Pooling, message log, thread messages, summarize range queries |
| `summarize.py` | Admin-gated summaries (separate prompt path) |

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- PostgreSQL database
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI-compatible chat API (`API_KEY`, `BASE_URL`, `MODEL`)
- Serper API key (for `/ask` search)
- OpenRouter API key (recommended for Jev; falls back to `API_KEY`)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Desmond112998/five-guys-summarize-tg-bot.git
   cd five-guys-summarize-tg-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Create a `.env` file in the project root:
   ```env
   BOT_TOKEN=your_telegram_bot_token_here
   DATABASE_URL=postgresql://username:password@host:port/database
   MODEL=your_ai_model_name
   API_KEY=your_openai_api_key
   BASE_URL=your_ai_service_base_url
   SERPER_API_KEY=your_serper_key
   OPENROUTER_API_KEY=your_openrouter_key
   ```

4. **Set up database**

   The bot creates necessary tables on first run.

5. **Run the bot**
   ```bash
   python main.py
   ```

## 🎮 Bot Commands

### Chat Management (Admin Required)
- `/summarize` — Summarize today's entire conversation
- `/summarize_user` — Summarize a specific user's messages (reply to user)
- `/golden_quote_king` — Find today's most interesting speaker

### Interactive AI
- Mention `@bot` or **reply** to the bot — Threaded group chat (Jev input gate, 20 uses/day per chat)
- `/ask [question]` — Factual Q&A with optional search (Jev input + search gates)

### Other Interactive Commands
- `/compliment` — Personalized compliment (reply to user)
- `/love` — Cheesy pickup lines (reply to user)
- `/apologize` — Humorous apology
- `/diu` — Playful roast (reply to user)

### Utility Commands
- `/countdown` — Time until end of work day (6 PM HKT)
- `/countdown_to_work` — Time until next workday starts
- `/countdown_to_retirement [year]` — Countdown to retirement year
- `/donate` — Support link

## 🏗️ Project Structure

```
five-guys-summarize-tg-bot/
├── main.py              # Bot application & command handlers
├── ai_chat.py           # Mention/reply chat + thread memory
├── jev_gate.py          # Jev input/search safety gates
├── config.py            # Env, prompts, GATE_REJECT_REPLY
├── ai.py                # LLM, Serper, tool loop
├── database.py          # Connection pool & thread/message helpers
├── db.py                # Summarize range queries & legacy DB ops
├── summarize.py         # /summarize* commands
├── compliment.py        # /compliment
├── love.py              # /love
├── dxx.py               # /diu
├── aplogize.py          # /apologize
├── requirements.txt
└── README.md
```

## 🧠 AI Integration

- **Chat & `/ask`**: OpenAI-compatible chat completions; system prompts include live Hong Kong datetime via `system_prompt_with_hk_time()`.
- **Summarize & entertainment**: One-shot prompts (`AI_GENERATE_BASE_PROMPT`, `SUMMARIZE_PROMPTS`, etc.) over pasted transcripts—no Jev, no tools.
- **Culture**: LIHKG / JFFT-inspired Cantonese where those prompts apply; chat and answer prompts are shorter and focused on safety + mode rules.

### Supported backends
- Any OpenAI-compatible chat endpoint (`BASE_URL` + `MODEL`)
- Jev on OpenRouter (`JEV_BASE_URL`, `JEV_MODEL`, default `jev-1.13`)
- Serper (`SERPER_API_KEY`) for `/ask` only

## 🗄️ Database

Messages and thread metadata live in PostgreSQL (exact schema evolves with migrations in `database.py` / `init_db`). Summarize commands query by `chat_id` and time range; thread chat loads recent turns for the resolved `thread_id`.

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot Token from BotFather | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `MODEL` | Chat model name | Yes |
| `API_KEY` | Chat API key | Yes |
| `BASE_URL` | Chat API base URL | Yes |
| `SERPER_API_KEY` | Serper search API key | Yes (for `/ask` search) |
| `OPENROUTER_API_KEY` | OpenRouter key for Jev; if unset, uses `API_KEY` | Recommended |
| `JEV_BASE_URL` | Jev API base (default `https://openrouter.ai/api`) | No |
| `JEV_MODEL` | Jev model id (default `jev-1.13`) | No |
| `JEV_REJECT_THRESHOLD` | Reject when Jev noul ≥ this (default `0.8`) | No |
| `THREAD_IDLE_MINUTES` | Thread continuity window (default `30`) | No |
| `MAX_THREAD_TURNS` | Max turns loaded per thread (default `20`) | No |

### Bot Permissions

- **Read messages** — Logging and summarize
- **Send messages** — Replies
- **Admin** — Required for `/summarize*` features

## 🎨 Language Style

- Traditional Chinese, Hong Kong Cantonese colloquial tone
- LIHKG / JFFT flavor on summarize and generate commands
- Chat: friendly group assistant; `/ask`: clear factual Cantonese
- Do not mention the user's family (prompt rule); self-harm resources: https://helpline.siuyeong.com/

## 📝 Contributing

Contributions welcome. Open an issue for large changes. Keep summarize/fun command behavior stable unless intentionally changing product scope.

## 🐛 Troubleshooting

**Everything returns `呢條我答唔到。` on chat/`/ask`**
- Check `OPENROUTER_API_KEY` or `API_KEY` and Jev connectivity
- Jev fails closed; logs show `Jev gate failed closed`

**`/ask` never searches**
- Verify `SERPER_API_KEY`
- Search may be refused by the search gate (unsafe query)—model should still reply without Serper

**Summarize empty**
- Bot needs admin in group; ensure messages exist in the requested time range

**Database errors**
- Verify `DATABASE_URL` and PostgreSQL availability

## 📄 License

[MIT License](LICENSE)

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- Hong Kong internet culture & LIHKG community
- [TypeSafe Jev](https://openrouter.ai/) via OpenRouter for input gating

## 📞 Support

Open a GitHub issue or see **Troubleshooting** above.
