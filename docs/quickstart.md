# Moderator — Quick Start Guide

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose v2+
- An [Anthropic API key](https://console.anthropic.com/) for Claude moderation
- `curl` or any HTTP client for testing
- Python 3.12+ with `rich` and `httpx` for the optional CLI (`pip install rich httpx`)

---

## 1. Clone & Configure

```bash
git clone https://github.com/your-org/moderator.git
cd moderator
```

Copy the environment template and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql+asyncpg://moderator:moderator@db:5432/moderator
ANTHROPIC_API_KEY=sk-ant-your-key-here
ADMIN_SECRET=your-strong-admin-secret
APP_ENV=development
LOG_LEVEL=info
```

> **Security**: Never commit your `.env` file. It is git-ignored by default.

---

## 2. Start with Docker Compose

Build and start all services (API + PostgreSQL):

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000` once the startup banner appears.

To run in the background:

```bash
docker compose up --build -d
```

Stop everything:

```bash
docker compose down
```

---

## 3. Apply Database Migrations

Migrations run automatically on startup via the `docker-compose.yml` command. To run manually:

```bash
docker compose exec api alembic upgrade head
```

---

## 4. Create Your First API Key

### Option A — mod-cli (recommended)

If you have the CLI set up (see [section 9](#9-mod-cli-interactive-developer-cli)):

```
mod ❯ set secret your-strong-admin-secret
  ✓  secret saved

mod ❯ key create my-app admin@example.com
  ✓  key created for my-app  /  admin@example.com
     mod_live_abc123XYZdef     ← copy this now, shown once
```

### Option B — script (inside Docker)

Use the included CLI script to generate and store an API key:

```bash
docker compose exec api python scripts/create_api_key.py \
  --app-name "my-app" \
  --owner-email "admin@example.com"
```

Example output:

```
  API Key created for: my-app
  Raw key (copy now — shown once): mod_live_abc123XYZdef
```

> **Important**: The raw key is shown only once. Store it securely (e.g., in a secrets manager or password manager). The database only stores a bcrypt hash.

---

## 5. Check the Health Endpoint

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok", "service": "moderator", "version": "1.0.0"}
```

---

## 6. Make Your First Moderation Request

Pass the raw API key in the `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/moderate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mod_live_abc123XYZdef" \
  -d '{"user_id": "user-42", "message": "Hello, world!"}'
```

Safe message response:

```json
{"safe": true, "strike_count": null, "warning": null, "flagged": false, "reason": null, "severity": null}
```

Unsafe message response (first strike):

```json
{
  "safe": false,
  "strike_count": 1,
  "warning": "Warning 1/5: hate speech detected",
  "flagged": false,
  "reason": "hate speech detected",
  "severity": "high"
}
```

After 5 violations, the user is permanently flagged:

```json
{
  "safe": false,
  "strike_count": 5,
  "warning": "Your account has been permanently restricted.",
  "flagged": true,
  "reason": null,
  "severity": null
}
```

---

## 7. Admin Endpoints

Admin endpoints require the `X-Admin-Secret` header matching `ADMIN_SECRET` in your `.env`.

### List all violation logs

```bash
curl http://localhost:8000/admin/violations \
  -H "X-Admin-Secret: your-strong-admin-secret"
```

### Filter violations by app or user

```bash
curl "http://localhost:8000/admin/violations?app_id=<uuid>&user_id=user-42&limit=20" \
  -H "X-Admin-Secret: your-strong-admin-secret"
```

### List all users with violations

```bash
curl http://localhost:8000/admin/users \
  -H "X-Admin-Secret: your-strong-admin-secret"
```

### List only flagged users

```bash
curl "http://localhost:8000/admin/users?flagged_only=true" \
  -H "X-Admin-Secret: your-strong-admin-secret"
```

---

## 8. Running Tests

### Local (requires Python 3.12+ and dependencies installed)

Install dependencies:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Create a minimal `.env` for tests (SQLite in-memory is used automatically):

```bash
cat > .env <<EOF
DATABASE_URL=sqlite+aiosqlite:///:memory:
ANTHROPIC_API_KEY=sk-ant-test
ADMIN_SECRET=test-secret
APP_ENV=test
EOF
```

Run the test suite:

```bash
pytest --cov=app -v
```

### With Docker (full PostgreSQL integration)

Create `.env.test`:

```bash
cat > .env.test <<EOF
DATABASE_URL=postgresql+asyncpg://moderator:moderator@db:5432/test_moderator
ANTHROPIC_API_KEY=sk-ant-test
ADMIN_SECRET=test-secret
APP_ENV=test
EOF
```

Run:

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

---

## API Reference Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Service health check |
| `POST` | `/moderate` | `X-API-Key` | Moderate a message |
| `GET` | `/admin/violations` | `X-Admin-Secret` | List violation logs |
| `GET` | `/admin/users` | `X-Admin-Secret` | List user violation records |

### POST /moderate

**Request body:**
```json
{"user_id": "string", "message": "string"}
```

**Response:**
```json
{
  "safe": true,
  "strike_count": 0,
  "warning": null,
  "flagged": false,
  "reason": null,
  "severity": null
}
```

### Violation severity levels

| Severity | Description |
|----------|-------------|
| `low` | Mild violations (minor spam, borderline language) |
| `medium` | Moderate violations (harassment, inappropriate content) |
| `high` | Severe violations (hate speech, threats, explicit content) |

---

## 9. mod-cli — Interactive Developer CLI

`mod_cli.py` is a standalone interactive terminal CLI for managing and testing the service.
It requires only Python 3.12+ and two packages — no Docker needed.

### Install CLI dependencies

```bash
pip install rich httpx
```

### Start the CLI

```bash
# default — connects to http://localhost:8000
python mod_cli.py

# point at a deployed instance
python mod_cli.py --url https://mod.souqmobile.online
```

Config (URL, API key, admin secret) is saved to `~/.mod_cli.json` between sessions.

### First-time setup

```
mod ❯ set url http://localhost:8000
  ✓  url → http://localhost:8000

mod ❯ set secret your-strong-admin-secret
  ✓  secret saved
```

### Create an API key

```
mod ❯ key create my-app admin@example.com
  ✓  key created for my-app  /  admin@example.com
     mod_live_xK9aQr2Nz1p     ← copy this now, shown once

mod ❯ set key mod_live_xK9aQr2Nz1p
  ✓  key saved
```

### Check service health

```
mod ❯ health
  ●  moderator v1.0.0  —  ok
```

### Moderate messages

```
mod ❯ mod user-42 hello world
  ✓  safe

mod ❯ mod user-42 i will hurt you
  ⚠  strike 1/5
     reason    threat / violent language
     severity  high
     warning   Warning 1/5: threat / violent language
```

### Admin commands

```
mod ❯ key list
  app        owner              created     active
  my-app     admin@example.com  2025-05-13  ✓

mod ❯ violations --user user-42
  user      sev    reason    message              at
  user-42   high   threat    i will hurt you      2025-05-13 14:32

mod ❯ users --flagged
  (no flagged users)

mod ❯ unban user-42
  unban user-42 from app "my-app"? [y/N] y
  ✓  user-42 unbanned — strikes reset to 0

mod ❯ key revoke my-app
  revoke key for "my-app"? [y/N] y
  ✓  key revoked
```

### All CLI commands

| Command | Description |
|---------|-------------|
| `health` | Ping `/health` |
| `key create <app> <email>` | Create a new API key |
| `key test <raw-key>` | Verify a key is valid |
| `key list` | List all keys |
| `key revoke <app>` | Revoke a key by app name |
| `mod <user-id> <message>` | Moderate a message |
| `violations [--user u] [--app id] [--limit n]` | List violation logs |
| `users [--flagged] [--app id]` | List users with violations |
| `unban <user-id>` | Reset user strikes and clear ban |
| `set url <value>` | Update the moderator URL |
| `set key <value>` | Save the API key |
| `set secret <value>` | Save the admin secret |
| `set show` | Show current config |
| `clear` | Clear the terminal |
| `exit` / `quit` | Exit the CLI |
