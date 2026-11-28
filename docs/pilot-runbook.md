---
title: Pilot runbook
description: Install Hermes Synapse on a clean customer VM with Docker Compose, first login, first approval, backup, restore, upgrade, rollback, and offline decision-log verification.
---

# Pilot runbook

Install Hermes Synapse from scratch on a **customer's VM**. Default compose is the pilot stack: required secrets, dashboard on loopback, unpublished Postgres/Qdrant/API, non-root containers, no Docker socket.

This page was written from a clean clone and a real `docker compose up -d --build` (commit `4432e7b`, then re-verified on `007ff9b` after BCM leftover removal). Wall-clock times below are that run, not estimates.

## Israeli-market note (data residency)

**Customer data stays on the customer's VM.** Postgres, Qdrant, and named volumes are unpublished. The dashboard listens on `127.0.0.1:9119` only.

If `LLM_API_BASE` points at OpenRouter or another hosted API, **prompts and tool traces leave the VM**. For residency, point `LLM_API_BASE` at a local OpenAI-compatible endpoint (Ollama, vLLM) and keep `OPENROUTER_API_KEY` as a placeholder.

Do not enable `docker-compose.docker-sock.yml` on a shared or production host.

## Hardware and OS (measured)

Validated on Ubuntu 24.04.5 LTS, 4 vCPU, 15 GiB RAM, 254 GiB disk. Docker Engine 29.x + Compose v2.

| Resource | Measured on the running stack | Plan for a partner VM |
|---|---|---|
| RAM (idle, five containers) | **~350 MiB** (backend ~140, sandbox ~113, Postgres ~50, Qdrant ~30, dashboard ~5) | **4 GiB minimum**, **8 GiB recommended** |
| Sandbox cgroup | `memory: 2G`, `cpus: 1.0`, `pids: 256` | Count that 2 GiB on top of idle if Code Engineer runs |
| CPU (idle) | <1% | 2 vCPU works; 4 vCPU made a cold image build ~2 min |
| Images | backend **1.12 GiB** (`007ff9b`; was 1.37 GiB on `4432e7b` before FIX/grpc/scipy were dropped), sandbox **1.53 GiB**, frontend **74 MiB**, Postgres 16-alpine **295 MiB**, Qdrant v1.13.2 **189 MiB** (~3.2 GiB total) | **20 GiB** free for images + first-build cache (~3 GiB) + volumes |
| Volumes (idle, first boot) | Postgres **49 MiB**, Qdrant **210 MiB**, backend **82 KiB**, sandbox empty | Grows with RAG documents and sandbox files |

`docker stats` after first boot (`4432e7b`):

```text
NAME               CPU %     MEM USAGE / LIMIT
jarvis-backend     0.20%     140MiB / 15.63GiB
jarvis-sandbox     0.24%     112.8MiB / 2GiB
jarvis-db          0.03%     45.77MiB / 15.63GiB
jarvis-qdrant      0.13%     27.54MiB / 15.63GiB
jarvis-dashboard   0.00%     4.875MiB / 15.63GiB
```

OS: Linux x86_64. Docker + Compose v2. `systemd` is the usual way to run `dockerd`; this validator used an already-running engine on `tcp://127.0.0.1:2375` because the guest had no systemd.

## Prerequisites

On the customer VM:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 openssl curl python3 git
sudo usermod -aG docker "$USER"   # then log out and back in
docker compose version            # need v2 (`docker compose`, not python docker-compose)
```

Also:

- An LLM: `OPENROUTER_API_KEY` **or** a local OpenAI-compatible `/v1` (Ollama). Chat in the UI needs this. Approvals via the HTTP API do not.
- Telegram bot token + chat id **or** `ALLOW_LOCAL_AUTH_FALLBACK=1` (writes OTP to a 0600 file in the backend volume).
- Outbound HTTPS to pull `postgres:16-alpine` and `qdrant/qdrant:v1.13.2` on first build.

## .env checklist

```bash
git clone https://github.com/pauloberezini/hermes-synapse.git
cd hermes-synapse
cp .env.example .env
```

| Variable | Required? | How to set |
|---|---|---|
| `POSTGRES_PASSWORD` | yes (compose `:?`) | `openssl rand -hex 32` — backend also rejects `postgres` / `password` / `hermes` / empty |
| `QDRANT_API_KEY` | yes, **≥16 chars** | `openssl rand -hex 32` |
| `JWT_SECRET` | yes, **≥32 chars** | `openssl rand -hex 32` — compose only checks the var is set; short values boot then crash-loop (`FATAL: JWT_SECRET … shorter than 32`) |
| `OPENROUTER_API_KEY` | for hosted LLM | from [openrouter.ai/keys](https://openrouter.ai/keys) |
| `LLM_API_BASE` / `LLM_MODEL` | if not OpenRouter | local: `http://host.docker.internal:11434/v1` and `llama3`; key can be `local` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_ADMIN_ID` | production OTP | BotFather + `@userinfobot` |
| `ALLOW_LOCAL_AUTH_FALLBACK` | no Telegram | set `1` so `/api/auth/request-code` writes `/app/backend/data/.current_otp` |
| `CODE_AGENTS_ENABLED` | no | **off by default.** Set `true` only if you want Code Engineer / Data Analyst sandbox execution (still HITL-gated). Unset and unrecognised values fail closed |
| `POSTGRES_USER` / `POSTGRES_DB` | no | default `hermes` / `hermes` |

Generate the three compose secrets (do not reuse the sample output):

```bash
openssl rand -hex 32   # POSTGRES_PASSWORD
openssl rand -hex 32   # QDRANT_API_KEY
openssl rand -hex 32   # JWT_SECRET
```

Paste them into `.env`. Compose interpolation fails if they are **unset**. The backend then refuses known defaults when `ENV=production`.

## Install (target ≤ 30 minutes)

Measured wall-clock on a 4 vCPU VM, cold image pull, commit `4432e7b`. Re-verified `docker compose up -d --build` on `007ff9b` (**36 s** rebuild after BCM leftover removal; backend image 1.12 GiB).

| Step | What | Measured |
|---|---|---|
| 1 | `git clone` + checkout | ~1 s |
| 2 | `cp .env.example .env` + `openssl rand -hex 32` × 3 | ~1 s |
| 3 | `docker compose up -d --build` until backend healthy | **118 s** |
| 4 | dashboard healthy on `127.0.0.1:9119` | &lt; 3 s after step 3 |
| 5 | OTP + login (with fallback=1) | **1 s** |
| 6 | first gated approval (API) | &lt; 1 s |
| **Clone → dashboard** | | **~2 min** |
| **Clone → first approval** | including OTP workaround | **~2.5 min** |

```bash
docker compose up -d --build
docker compose ps
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/
curl -sS http://127.0.0.1:9119/api/status
```

Expect:

- `jarvis-dashboard` published as `127.0.0.1:9119->8080/tcp` only
- `jarvis-backend` `:8000`, `jarvis-db` `:5432`, `jarvis-qdrant` `:6333-6334` **not** published
- `jarvis-sandbox` on the internal `sandbox-net` only
- `/api/status` → `{"status":"online",...}` (this route is public)

Remote operator: SSH tunnel, then open the same URL on the laptop.

```bash
ssh -L 9119:127.0.0.1:9119 user@customer-vm
# browser: http://127.0.0.1:9119
```

Put a TLS reverse proxy on the VM if you must expose the dashboard beyond loopback. Do not publish Postgres or Qdrant.

## First login

Production compose sets `ENV=production`. OTP is a 6-digit code, 5 minute TTL, single use. It is **not** printed in logs.

**Telegram (default):** set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, click login, read the code in Telegram.

**File fallback (no Telegram):** set `ALLOW_LOCAL_AUTH_FALLBACK=1` in `.env`, recreate the backend, then:

```bash
curl -sS -X POST http://127.0.0.1:9119/api/auth/request-code
docker compose exec backend cat /app/backend/data/.current_otp
# POST /api/auth/verify-code  {"code":"<six digits>"}
```

The file is mode `0600`, uid `10001`. Error responses keep `{"status":"error","message":"..."}` but use a real HTTP status: **400** if Telegram is not configured and fallback is off, **503** if the bot is down or Telegram is unreachable, **500** for other send failures. `curl -f` fails those. The dashboard reads `message` on non-2xx.

On this install, default compose (`ALLOW_LOCAL_AUTH_FALLBACK=0`, no Telegram) returned **HTTP 400**:

```json
{"status":"error","message":"TELEGRAM_CHAT_ID is not configured on backend."}
```

and no `.current_otp` file. With `ALLOW_LOCAL_AUTH_FALLBACK=1`, request-code wrote the file (HTTP 200) and login returned a 64-character session token in **1 s**.

Sessions persist in Postgres (`auth_sessions`). A backend restart does not drop them.

## Time to first approval

Approve does **not** run the tool. The next identical payload in that session is consumed once.

### UI (needs an LLM)

1. Open Communication Link. New chat.
2. Send: `Ask Sys Ops to run \`df -h /\` on the server.`
3. Governance Approvals → read CLAIM + SOURCE → Approve with a note.
4. Send the **same** prompt again. Status becomes `CONSUMED`.

Full walkthrough: [Approvals](./guide/approvals).

This validator had **no LLM key**, so the chat path was not timed. The API path below was.

### API (verified, no LLM)

```bash
TOKEN=...   # from verify-code

docker compose exec -T -e PYTHONPATH=/app backend python3 - <<'PY'
from backend.governance import gate_tool
print(gate_tool("pilot-session", "execute_command", {"command": "df -h /"}))
PY
# → {"status":"PENDING_APPROVAL","request_id":1,...}

curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:9119/api/governance/approvals?pending_only=true'

curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"decision":"APPROVED","resolver_note":"Read-only df -h /"}' \
  http://127.0.0.1:9119/api/governance/approvals/1/resolve
```

Measured: PENDING → APPROVED in under a second. Identical `gate_tool` call then returned `None` (consume); `execute_command("df -h /")` ran with `exit_code: 0`. `GET /api/governance/decisions/verify` → `ok checked=3`.

## Enabling code agents (explicit)

Pilot compose and `.env.example` default **`CODE_AGENTS_ENABLED=false`**. Unset and unrecognised values fail closed: no sandbox POST, no approval row, no LLM self-correction. Sys Ops `execute_command` is unrelated and still HITL-gated.

**Risk.** `true` lets the Code Engineer / Data Analyst run operator-approved Python inside `jarvis-sandbox` (1 CPU, 2 GiB, isolated `sandbox-net`, non-root uid 10002). Approve still does not run the tool; the next identical payload is consumed once. Do not enable on a shared host unless that is acceptable.

To turn it on:

```bash
# .env — then recreate backend so the running process sees it
CODE_AGENTS_ENABLED=true
docker compose up -d --force-recreate --no-deps backend
```

To turn it off, set `false` (or anything other than `true`/`1`/`yes`/`on`) and recreate.

| Value | `code_agents_enabled()` | `execute_code` |
|---|---|---|
| unset / `false` / `0` / `off` | false | `status=DISABLED`, no approval row |
| `true` / `1` / `yes` / `on` | true | HITL gate, then sandbox |
| `maybe` (or anything else) | false | same fail-closed |

`docker-compose.dev.yml` (DEV ONLY) hardcodes `CODE_AGENTS_ENABLED=true` so local hot-reload can hit the sandbox. Pilot `docker-compose.yml` defaults to false.

Existing installs that relied on the old default-on behavior must set `CODE_AGENTS_ENABLED=true`.

## Backup (Postgres + Qdrant + volumes)

Named volumes follow the **directory name** you cloned into (`hermes-synapse_*` if the folder is `hermes-synapse`). Check with `docker volume ls`.

Stream tars to stdout (works with a local socket **and** a remote `DOCKER_HOST`; bind-mounting the VM's `/tmp` into a remote engine writes the host's `/tmp`, not yours).

```bash
mkdir -p backup
# Postgres (custom format)
docker compose exec -T db pg_dump -U hermes -d hermes --no-owner --format=custom > backup/hermes.dump
# Qdrant + app volumes
docker run --rm -v hermes-synapse_qdrant_data:/data alpine:3.20 tar czf - -C /data . > backup/qdrant_data.tgz
docker run --rm -v hermes-synapse_backend_data:/data alpine:3.20 tar czf - -C /data . > backup/backend_data.tgz
docker run --rm -v hermes-synapse_sandbox_data:/data alpine:3.20 tar czf - -C /data . > backup/sandbox_data.tgz
```

Measured backup: **~2 s** (empty-ish volumes; dump ~55 KiB, Qdrant tar ~259 KiB). Also export the decision log (separate from DB backup):

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:9119/api/governance/decisions/export.zip \
  -o backup/decisions.zip
```

## Restore

Stop writers **before** replacing volume contents. Restoring Qdrant while it is running is unsafe.

```bash
docker compose stop frontend backend sandbox qdrant

# Postgres: drop and restore into a running server
docker compose exec -T db psql -U hermes -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='hermes' AND pid <> pg_backend_pid();"
docker compose exec -T db psql -U hermes -d postgres -c "DROP DATABASE hermes;"
docker compose exec -T db psql -U hermes -d postgres -c "CREATE DATABASE hermes OWNER hermes;"
docker compose exec -T db pg_restore -U hermes -d hermes --no-owner --exit-on-error < backup/hermes.dump

# Volumes (extract runs as root — chown afterwards)
docker run --rm -i -v hermes-synapse_qdrant_data:/data alpine:3.20 \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar xzf - -C /data' < backup/qdrant_data.tgz
docker run --rm -i -v hermes-synapse_backend_data:/data alpine:3.20 \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar xzf - -C /data' < backup/backend_data.tgz
docker run --rm -i -v hermes-synapse_sandbox_data:/data alpine:3.20 \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar xzf - -C /data' < backup/sandbox_data.tgz

# Required after every root tar extract (there is no restore script in the repo):
docker run --rm -v hermes-synapse_backend_data:/data alpine:3.20 chown -R 10001:10001 /data
docker run --rm -v hermes-synapse_sandbox_data:/data alpine:3.20 chown -R 10002:10002 /data

docker compose up -d
```

Do **not** skip the two `chown` lines. Alpine extract runs as root; backend is uid **10001**, sandbox uid **10002**. A missing chown shows up as permission errors writing `/app/backend/data` or `/mnt/data`.

Measured restore drill (drop DB, `pg_restore`, retar volumes, wait healthy): **19 s**. After restore, `/api/governance/decisions/verify` still reported `ok checked=4` with the same `head_hash`. The pre-wipe OTP session token still worked (sessions live in Postgres).

**Fresh install** already created `backend_data` as `10001` and `sandbox_data` as `10002`. `chown` is only for **root tar extract** or volumes created as root before non-root compose.

## Upgrade and rollback

Compose builds images named `{directory}-{service}` (for example `hermes-synapse-backend`). Tag a known-good build before you upgrade.

```bash
# pin
git rev-parse --short HEAD
docker tag hermes-synapse-backend:latest  hermes-synapse-backend:007ff9b
docker tag hermes-synapse-frontend:latest hermes-synapse-frontend:007ff9b
docker tag hermes-synapse-sandbox:latest  hermes-synapse-sandbox:007ff9b

# upgrade
git fetch origin
git checkout origin/main    # or a release tag
docker compose up -d --build
```

Rollback:

```bash
# A — git + rebuild (always works)
git checkout 007ff9b
docker compose up -d --build

# B — retag a pinned image, skip the compiler
docker tag hermes-synapse-backend:007ff9b  hermes-synapse-backend:latest
docker tag hermes-synapse-frontend:007ff9b hermes-synapse-frontend:latest
docker tag hermes-synapse-sandbox:007ff9b  hermes-synapse-sandbox:latest
docker compose up -d --no-build
```

Measured image retag + `--no-build`: **3 s**, dashboard 200, verify still `ok`.

Postgres named volumes keep data across image rolls. If a release includes a breaking schema change, restore from `backup/hermes.dump` taken **before** the upgrade.

## Offline verification of the hash-chained log

Two checkers exist. Use the zip one offline.

| Tool | Needs | Use |
|---|---|---|
| `scripts/verify_decision_log.py` | Python 3.11+ **stdlib only**, an `export.zip` | Air-gapped verify. **This is the pilot path.** |
| `scripts/verify_audit_chain.py` | a running backend + `DATABASE_URL` (imports `backend.decision_log.verify`) | Live DB. Not offline. |
| `GET /api/governance/decisions/verify` | logged-in API | Live DB via HTTP |

No extra CLI was added. The zip checker is already the offline verifier.

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:9119/api/governance/decisions/export.zip -o decisions.zip

python3 scripts/verify_decision_log.py decisions.zip
# ok checked=N head=H     ← copy H exactly (64 hex chars, not the "head=" prefix)

python3 scripts/verify_decision_log.py decisions.zip --pin H
```

Zip layout: `decisions.jsonl`, `evidence/<id>.json`, `manifest.json`, `VERIFY.md`. Exit 0 = chain + evidence hashes match. `--pin` fails if that `entry_hash` is missing (truncated tail). Tamper-evident, not a signature.

Verified here: `ok checked=3` then `--pin` on the 64-char head.

## Troubleshooting (from this install)

| Symptom | Cause | Fix |
|---|---|---|
| `TELEGRAM_CHAT_ID is not configured` and no `.current_otp` | compose default `ALLOW_LOCAL_AUTH_FALLBACK=0` | set `ALLOW_LOCAL_AUTH_FALLBACK=1` in `.env`, `docker compose up -d --force-recreate --no-deps backend` |
| request-code HTTP 400 / 503 | body is still `{"status":"error","message":"..."}` | 400 = not configured; 503 = Telegram down; read `message` |
| dashboard not reachable from your laptop | bound to **127.0.0.1:9119** on the VM | `ssh -L 9119:127.0.0.1:9119 user@vm` |
| backend exits at start, one line `FATAL: invalid production secrets: JWT_SECRET. Fix: openssl rand -hex 32` | compose `:?` only checks the var is set; short/default values fail in the app | `openssl rand -hex 32` into `.env`, recreate backend |
| permission denied writing `/app/backend/data` | volume owned by root from an old install or a root tar restore | `chown -R 10001:10001` on `*_backend_data`, `10002:10002` on `*_sandbox_data` |
| Qdrant log: API key used with an insecure connection | HTTP on the internal compose network | expected; do not publish 6333 |
| `/var/run/docker.sock` in the backend | you passed the opt-in overlay | remove it unless you have a skill that truly needs Docker. Host-root equivalent |
| volume tarballs missing after `docker run -v /tmp/backup:/backup` | `DOCKER_HOST` is a **remote** engine; that bind-mount is the engine host | stream `tar czf -` to stdout, as in Backup |
| UI chat never creates a PENDING row | no working LLM | configure OpenRouter/Ollama, or use the `gate_tool` API path above |
| Code Engineer returns `DISABLED` | `CODE_AGENTS_ENABLED` defaults to false | set `true` in `.env` and `--force-recreate --no-deps backend` (see [Enabling code agents](#enabling-code-agents-explicit)) |
| `.env` change has no effect | env_file is read at **container start** | `--force-recreate --no-deps backend` |

Containers run as `10001` (backend) and `10002` (sandbox). Frontend compose user is `101:101` (nginx). Postgres alpine uses uid `70`. Qdrant in this stack writes its volume as root.

## What this run verified vs skipped

Verified on a clean clone, `docker compose up -d --build`:

- required secrets, fail-fast on short `JWT_SECRET`
- dashboard `127.0.0.1:9119`, data stores unpublished, no docker.sock
- OTP Telegram-only default **and** `.current_otp` with `ALLOW_LOCAL_AUTH_FALLBACK=1`
- first gated `execute_command` PENDING → APPROVE → CONSUME via API
- `CODE_AGENTS_ENABLED` defaults off; true / false / unrecognised fail-closed
- `export.zip` + `scripts/verify_decision_log.py --pin`
- Postgres dump + volume tars, restore, chain still `ok`
- image tag rollback `--no-build`

Not verified:

- UI chat → Sys Ops (no LLM key in this environment)
- Telegram delivery
- TLS reverse proxy in front of 9119
- `docker-compose.docker-sock.yml` (intentionally not enabled)
