```ansi

  ███╗   ███╗ ██████╗ ██████╗ ███████╗██████╗  █████╗ ████████╗ ██████╗ ██████╗
  ████╗ ████║██╔═══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗
  ██╔████╔██║██║   ██║██║  ██║█████╗  ██████╔╝███████║   ██║   ██║   ██║██████╔╝
  ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝  ██╔══██╗██╔══██║   ██║   ██║   ██║██╔══██╗
  ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗██║  ██║██║  ██║   ██║   ╚██████╔╝██║  ██║
  ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝

```

#### BYOK AI content moderation microservice. Bring your own API key, plug it in, get a verdict on every message. That simple.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Haiku-D97757?style=flat-square&logo=anthropic&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat-square&logo=openai&logoColor=white)
![Gemini](https://img.shields.io/badge/Google-Gemini-4285F4?style=flat-square&logo=google&logoColor=white)
![pytest](https://img.shields.io/badge/tested-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)

---

## Architecture

<!-- Replace with your Eraser diagram export -->
<img width="2704" height="1454" alt="01-diagram-export-6-10-2026-4_27_00-PM" src="https://github.com/user-attachments/assets/4ea5281d-56a9-4678-a29b-88ef18c20203" />

---

## What it does

Any app sends `POST /moderate` with a user ID and message. The service runs it through your connected AI provider (Claude, GPT-4o, or Gemini), returns a verdict, and tracks repeat offenders across a persistent strike pipeline. Five strikes and the user is permanently flagged — no more moderating them, no more wasted inference calls.

The key design decision: **you supply the API key**. The service encrypts it with Fernet symmetric encryption and stores it server-side. Your AI usage stays on your billing account. The service just handles the routing, session management, strike tracking, and admin tooling.

---

## Technical decisions worth knowing

**Provider abstraction (Strategy pattern)** — all three AI providers implement a single `AIProvider` ABC with one method: `moderate(message) → ModerationResult`. At request time, `provider_factory.py` resolves the correct provider from the user's stored credentials, decrypts the key, and hands back the right implementation. Swapping providers doesn't touch the moderation logic.

**Fernet encryption for stored keys** — provider API keys are never stored in plaintext. Every key goes through `cryptography.Fernet` before hitting the database. Decryption only happens inside the request cycle, never logged, never returned.

**JWT + server-side session table** — access tokens are signed with HS256 but also hashed (SHA-256) and stored in a `sessions` table. Logout physically revokes the hash, so a stolen token can't be replayed after logout. Standard JWT-only auth doesn't give you this.

**Strike pipeline design** — `UserViolation` tracks strike count per app per user. `ViolationLog` records every individual flagged message with full context. These are separate tables intentionally — you can query aggregate counts without scanning the full log, and you can audit the full log without touching counters.

**Structured output enforcement** — the system prompt forces JSON-only responses and strips markdown fences in all three provider implementations. The fallback on parse failure is `safe=True` (fail open) to avoid false positives on provider glitches.

---

## Quick start

```bash
git clone https://github.com/Yasinyan23/ai-moderation-api.git
cd moderator
cp .env.example .env
# add ANTHROPIC_API_KEY, ADMIN_SECRET, FERNET_SECRET, JWT_SECRET to .env
docker compose up --build
```

Generate the secrets you need:

```bash
# FERNET_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# JWT_SECRET
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Service health check |
| `POST` | `/moderate` | `X-API-Key` | Moderate a message, track strikes |
| `GET` | `/admin/violations` | `X-Admin-Secret` | Full violation log with filters |
| `GET` | `/admin/users` | `X-Admin-Secret` | User strike records |
| `PATCH` | `/admin/users/{id}/unban` | `X-Admin-Secret` | Reset user strikes |
| `POST` | `/auth/register` | None | Create account |
| `POST` | `/auth/login` | None | Get JWT token |
| `POST` | `/providers/connect` | `Bearer JWT` | Encrypt + store provider key |
| `GET` | `/providers/me` | `Bearer JWT` | List connected providers |

### Moderate a message

```bash
curl -X POST http://localhost:8000/moderate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mod_live_yourkey" \
  -d '{"user_id": "user-42", "message": "Hello world"}'
```

**Safe response:**
```json
{"safe": true}
```

**Strike response:**
```json
{
  "safe": false,
  "strike_count": 2,
  "flagged": false,
  "reason": "threat / violent language",
  "severity": "high",
  "warning": "Warning 2/5: threat / violent language"
}
```

**Permanently flagged:**
```json
{
  "safe": false,
  "flagged": true,
  "warning": "Your account has been permanently restricted."
}
```

---

## Strike system

| Count | State | Behaviour |
|-------|-------|-----------|
| 1–4 | Active | Warning returned, message blocked, strike recorded |
| 5 | Flagged | Account permanently restricted — instant block on all future messages, no inference call made |

The permanently-flagged check runs before the AI call. A user at strike 5 costs you zero tokens.

---

## mod-cli

An interactive terminal CLI ships with the service — no Docker needed for local testing.

<img width="1566" height="1056" alt="download" src="https://github.com/user-attachments/assets/c5428048-7ebf-40ad-a691-55b3dd7f4736" />


Full CLI reference in [docs/quickstart.md](docs/quickstart.md).

---

## Tests

```bash
# local
pytest --cov=app -v

# full docker integration
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

Test coverage includes auth flows (register → OTP verify → login → logout), strike accumulation and flagging logic, provider auth and Fernet secret handling, and API key lifecycle.

---

## Project structure

```
moderator/
├── app/
│   ├── main.py                  # FastAPI app, lifespan, router registration
│   ├── config.py                # Pydantic settings, env validation
│   ├── database.py              # Async SQLAlchemy engine + session factory
│   ├── middleware/auth.py       # API key, JWT, admin secret validators
│   ├── models/
│   │   ├── db.py                # SQLAlchemy ORM models
│   │   └── schemas.py           # Pydantic request/response schemas
│   ├── routers/
│   │   ├── moderate.py          # POST /moderate — core pipeline
│   │   ├── admin.py             # Admin endpoints
│   │   ├── auth.py              # Register, verify OTP, login, logout
│   │   └── providers.py         # Provider connect/disconnect/switch
│   └── services/
│       ├── ai.py                # AIProvider ABC + ModerationResult
│       ├── claude.py            # Anthropic implementation
│       ├── openai.py            # OpenAI implementation
│       ├── gemini.py            # Gemini implementation
│       ├── provider_factory.py  # Runtime provider resolution
│       ├── crypto.py            # Fernet encrypt/decrypt
│       ├── jwt_service.py       # Token creation, hashing, validation
│       ├── violations.py        # Strike pipeline helpers
│       └── email.py             # OTP delivery (SMTP or stdout fallback)
├── migrations/                  # Alembic migrations (versioned)
├── tests/                       # pytest suite
├── mod_cli.py                   # Interactive developer CLI
├── docker-compose.yml
├── docker-compose.test.yml
└── docs/
    ├── quickstart.md
```

---

