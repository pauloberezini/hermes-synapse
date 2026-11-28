---
title: Gateway hook live check (macOS)
description: Fifteen-minute live check of the Claude Code PreToolUse hook against a throwaway Hermes stand. Your login, your laptop, then roll it back.
---

# Gateway hook live check (macOS, ~15 minutes)

Pavel runs this on **his** Mac, logged into Claude Code with **his claude.ai subscription**. Do not copy anyone else's credentials. Do not merge this branch. Do not edit `~/.claude/settings.json`.

**Clone `cursor/gateway-mvp-2164`, not `main`.** This branch is unmerged. It already contains `origin/main` (`CODE_AGENTS_ENABLED=false`, signed checkpoints, demo, evidence pack). The hook script, example settings, docs-only compose override, and this page are **not** on `main`. Step 7 clones this branch.

**Subscription, not API billing.** You already log in with `claude` → `/login` (claude.ai). This check must not use Anthropic API-key billing. Step 4 confirms `claude auth status` shows `"loggedIn": true`. Step 5 unsets `ANTHROPIC_API_KEY` in the shell that launches `claude` so the CLI cannot switch to API billing. Do not set that variable anywhere in this guide.

The Claude prompts below use **a few subscription messages** (one Bash create, one retry after Approve, one reject case, one fail-closed case). That is expected on a Pro/Max/Team plan. Stop if `/login` is not your subscription.

**Ports (read this once).**

| What | URL | Why |
|---|---|---|
| Dashboard / Approvals UI | `http://127.0.0.1:9119` | Pilot compose publishes this. Login and Approve here. |
| Hook API | `http://127.0.0.1:8000/api/gateway/pre-tool` | The hook process POSTs here. |

Pilot `docker-compose.yml` does **not** publish `:8000`. Step 10 adds the docs-only override `docs/gateway/docker-compose.gateway-live.yml` so the Mac can reach the backend on loopback. **Do not** point the hook at `:9119`. Nginx would add `X-Forwarded-For` and a Docker peer; the gateway returns 403.

On Docker Desktop for Mac, a published `127.0.0.1:8000` is reachable from the host as `127.0.0.1`, but **inside** the container `request.client.host` is the compose-network gateway (`172.x`), not `127.0.0.1`. Step 12 sets `HERMES_GATEWAY_BIND` to that gateway. That is expected. It is not a product-code change.

Use `127.0.0.1`, not `localhost`, in every URL below (`localhost` can be IPv6 `::1` on macOS).

First `docker compose up --build` may exceed 15 minutes if images are cold. The operator steps after a healthy stack are short.

**Flags that do not change this hook** (leave the `.env.example` defaults):

| Var | Default | Effect on this check |
|---|---|---|
| `CODE_AGENTS_ENABLED` | `false` | Kill switch for Hermes `execute_code` only. Claude `Bash` still hits PreToolUse. Leave false. |
| `HERMES_REQUIRE_SIGNING` | `false` | Do **not** set true on first boot. The Ed25519 key is created on first use. Zip export still works. Signed JSON export (step 23) also works with generate-on-first-use. |
| `HERMES_AUDIT_KEY_PATH` | `backend/data/audit_ed25519.key` | Compose volume. No extra step. |

---

## 1. Docker Desktop

```bash
docker info >/dev/null && echo "docker ok" && docker compose version
```

**Expect:** `docker ok` and Compose v2 (`Docker Compose version v2…`). If `Cannot connect to the Docker daemon`, start Docker Desktop and retry.

## 2. Node

```bash
node -v && npm -v
```

**Expect:** Node `v22` or newer (Claude Code 2.1.x wants Node ≥ 22).

## 3. Claude Code CLI version

```bash
claude --version
```

**Expect:** a version line such as `2.1.332 (Claude Code)` (any 2.1.x is fine). If `command not found`:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

## 4. Confirm claude.ai subscription login

```bash
claude auth status
```

**Expect:** JSON with `"loggedIn": true`. That is your claude.ai subscription session.

If `"loggedIn": false`, start `claude` in any directory, run **`/login`**, finish the browser claude.ai login, quit that session, and repeat `claude auth status`. Stop if you cannot log in with the subscription. This check does not use, and must not grow, an Anthropic console key.

## 5. Keep this shell off API billing

In **every** terminal you will use for `claude` during this check:

```bash
unset ANTHROPIC_API_KEY
env | grep -E '^ANTHROPIC_API_KEY=' || echo "ANTHROPIC_API_KEY is unset (good)"
```

**Expect:** `ANTHROPIC_API_KEY is unset (good)`. If grep prints a value, `unset` it and repeat. A set key makes Claude Code bill the API instead of the subscription. Do not export it. Do not put it in `.env`. `source .env` later (Hermes secrets) must not bring it back — step 16 unsets it again after sourcing.

## 6. Throwaway parent directory

```bash
LIVE="$HOME/hermes-gateway-live"
if [ -e "$LIVE" ]; then echo "REFUSE: $LIVE already exists"; else mkdir "$LIVE" && echo "created $LIVE"; fi
```

**Expect:** `created /Users/<you>/hermes-gateway-live`. If it already exists, pick another name and use that everywhere below.

## 7. Clone this branch (not main)

```bash
LIVE="$HOME/hermes-gateway-live"
git clone -b cursor/gateway-mvp-2164 --single-branch \
  https://github.com/pauloberezini/hermes-synapse.git \
  "$LIVE/hermes-synapse"
git -C "$LIVE/hermes-synapse" rev-parse --short HEAD
git -C "$LIVE/hermes-synapse" branch --show-current
```

**Expect:** clone succeeds. Branch `cursor/gateway-mvp-2164` (not `main`). Record the short SHA for the DoD packet. If `git branch --show-current` prints `main`, you cloned the wrong ref — delete the dir and repeat this step with `-b cursor/gateway-mvp-2164`.

## 8. Throwaway test project (not `~/.claude`)

```bash
LIVE="$HOME/hermes-gateway-live"
mkdir -p "$LIVE/test-project"
# must stay empty of a global settings file
ls -la "$HOME/.claude/settings.json" 2>/dev/null || echo "no global settings.json (good to leave it that way)"
test ! -e "$LIVE/test-project/.claude/settings.json" && echo "test project has no settings yet"
```

**Expect:** `test-project` exists. Do not create or edit `$HOME/.claude/settings.json`. The hook settings go only in `$LIVE/test-project/.claude/settings.json` at step 15.

## 9. Generate secrets and write `.env`

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
cp .env.example .env
python3 << 'PY'
from pathlib import Path
import re
import secrets

p = Path(".env")
text = p.read_text()

def set_key(blob: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pat = re.compile(rf"^(?:#\s*)?{re.escape(key)}=.*$", re.M)
    if pat.search(blob):
        return pat.sub(line, blob, count=1)
    return blob.rstrip() + "\n" + line + "\n"

vals = {
    "POSTGRES_PASSWORD": secrets.token_hex(32),
    "QDRANT_API_KEY": secrets.token_hex(32),
    "JWT_SECRET": secrets.token_hex(32),
    "HERMES_GATEWAY_TOKEN": secrets.token_hex(32),
    "ALLOW_LOCAL_AUTH_FALLBACK": "1",
    "HERMES_GATEWAY_BIND": "127.0.0.1",
    "CODE_AGENTS_ENABLED": "false",
    "HERMES_REQUIRE_SIGNING": "false",
}
for k, v in vals.items():
    text = set_key(text, k, v)
p.write_text(text)
print("wrote .env (do not commit, do not paste)")
print("HERMES_GATEWAY_TOKEN length:", len(vals["HERMES_GATEWAY_TOKEN"]))
PY
```

**Expect:** `wrote .env` and `HERMES_GATEWAY_TOKEN length: 64`. The token stays in `.env` and in your shell (step 16). It must never appear in screenshots, `decision_log`, or the DoD packet. This `.env` is Hermes compose secrets only. It must not contain an Anthropic key.

## 10. Start the stand (pilot compose + docs-only port override)

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
docker compose \
  -f docker-compose.yml \
  -f docs/gateway/docker-compose.gateway-live.yml \
  up -d --build
docker compose ps
curl -sS -o /dev/null -w "dashboard:%{http_code}\n" http://127.0.0.1:9119/
curl -sS http://127.0.0.1:9119/api/status
curl -sS -o /dev/null -w "backend:%{http_code}\n" http://127.0.0.1:8000/api/status
```

**Expect:**

- `jarvis-dashboard` … `127.0.0.1:9119->8080/tcp`
- `jarvis-backend` now also `127.0.0.1:8000->8000/tcp` (this is the override; stock compose does not do this)
- `dashboard:200` (or `304`)
- `/api/status` JSON with `"status":"online"`
- `backend:200` on `:8000`

If `:8000` is `connection refused`, the override file was omitted. Re-run the `docker compose … up` command with both `-f` flags.

## 11. Discover the Docker peer (macOS bind caveat)

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
docker inspect jarvis-backend \
  --format '{{range .NetworkSettings.Networks}}{{.Gateway}} {{end}}'
```

**Expect:** one or two `172.` addresses (compose `hermes-net` / `sandbox-net` gateways). Copy the **first** `172.` address. That is the TCP peer the backend will see when the Mac hook hits `127.0.0.1:8000`.

## 12. Bind that peer and recreate backend

Replace `172.18.0.1` with the address from step 11.

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
GW=172.18.0.1   # <-- paste the first 172.x from step 11
python3 - "$GW" << 'PY'
from pathlib import Path
import re, sys
gw = sys.argv[1]
p = Path(".env")
text = p.read_text()
line = f"HERMES_GATEWAY_BIND=127.0.0.1,{gw}"
text = re.sub(r"^(?:#\s*)?HERMES_GATEWAY_BIND=.*$", line, text, count=1, flags=re.M)
p.write_text(text)
print("HERMES_GATEWAY_BIND=", line.split("=",1)[1])
PY
docker compose \
  -f docker-compose.yml \
  -f docs/gateway/docker-compose.gateway-live.yml \
  up -d --force-recreate --no-deps backend
```

**Expect:** `HERMES_GATEWAY_BIND=127.0.0.1,172.…` and backend healthy again (`docker compose ps`).

## 13. Probe the hook route (before Claude)

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
set -a && source .env && set +a
curl -sS -D - -o /tmp/gw-hook-body.json \
  -H "Authorization: Bearer $HERMES_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"probe","tool_name":"Bash","tool_input":{"command":"echo probe"}}' \
  http://127.0.0.1:8000/api/gateway/pre-tool
echo
cat /tmp/gw-hook-body.json
echo
# token must not appear in the body
python3 -c 'import os,pathlib; t=os.environ["HERMES_GATEWAY_TOKEN"]; b=pathlib.Path("/tmp/gw-hook-body.json").read_text(); assert t not in b; print("token absent from body (good)")'
```

**Expect:** HTTP `200`. JSON with `permissionDecision": "deny"` and a reason containing `Pending approval` and `Retry this tool`. `token absent from body (good)`.

If HTTP `403` and logs say `peer … not in bind list`:

```bash
docker compose logs backend 2>&1 | grep "gateway hook rejected" | tail -5
```

Put **that** peer into `HERMES_GATEWAY_BIND` (step 12) and recreate again.

If HTTP `503`: `HERMES_GATEWAY_TOKEN` did not reach the container. Confirm it is uncommented in `.env` (no leading `#`) and recreate backend.

## 14. Log in to the dashboard (Hermes OTP — not Anthropic)

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
curl -sS -X POST http://127.0.0.1:9119/api/auth/request-code
echo
OTP=$(docker compose exec -T backend cat /app/backend/data/.current_otp)
echo "otp digits only, do not screenshot: ${#OTP} chars"
RESP=$(curl -sS -X POST http://127.0.0.1:9119/api/auth/verify-code \
  -H "Content-Type: application/json" \
  -d "{\"code\":\"$OTP\"}")
echo "$RESP" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("login", "ok" if d.get("token") or d.get("status")=="success" else d)'
# keep the session token in this shell for export later
export HERMES_SESSION=$(python3 -c 'import json,os,sys; print(json.loads(os.environ.get("RESP","{}")).get("token") or "")' 2>/dev/null)
# fallback parse
export HERMES_SESSION=$(printf '%s' "$RESP" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("token") or d.get("access_token") or "")')
echo "session token length: ${#HERMES_SESSION}"
```

**Expect:** `request-code` succeeds with fallback. OTP file exists. `session token length:` 32+. Open **http://127.0.0.1:9119** in the browser and paste the same OTP if the UI login is still sitting there (or you are already in if the curl session is enough for API; the UI needs its own login).

**UI:** Communication Link loads. Top bar **Approvals** badge is `0` or hidden.

If `request-code` is HTTP 400 about Telegram: `.env` still has `ALLOW_LOCAL_AUTH_FALLBACK=0`. Set it to `1`, recreate backend, retry.

## 15. Project-local `.claude/settings.json`

```bash
LIVE="$HOME/hermes-gateway-live"
HOOK="$LIVE/hermes-synapse/scripts/gateway/claude_pre_tool_use.py"
mkdir -p "$LIVE/test-project/.claude"
python3 - "$HOOK" "$LIVE/test-project/.claude/settings.json" << 'PY'
import json, sys
from pathlib import Path
hook, dest = sys.argv[1], Path(sys.argv[2])
dest.write_text(json.dumps({
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Edit|Write|NotebookEdit|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": f"python3 {hook}",
        "timeout": 50,
        "onFailure": "block",
        "statusMessage": "Waiting for Hermes approval"
      }]
    }]
  }
}, indent=2) + "\n")
print("wrote", dest)
print("hook", hook)
PY
# never point this at the global file
test "$(realpath "$LIVE/test-project/.claude/settings.json")" != "$(realpath "$HOME/.claude/settings.json" 2>/dev/null || echo none)" && echo "not the global settings file (good)"
```

**Expect:** `wrote …/test-project/.claude/settings.json`. Command is `python3` plus the clone’s `claude_pre_tool_use.py`. `onFailure` is `block`. **No token** in that file.

```bash
grep -n TOKEN "$HOME/hermes-gateway-live/test-project/.claude/settings.json" || echo "no TOKEN in project settings (good)"
```

## 16. Export hook env in the shell that will launch Claude

```bash
LIVE="$HOME/hermes-gateway-live"
set -a && source "$LIVE/hermes-synapse/.env" && set +a
unset ANTHROPIC_API_KEY
export HERMES_GATEWAY_URL="http://127.0.0.1:8000/api/gateway/pre-tool"
echo "token length ${#HERMES_GATEWAY_TOKEN} url $HERMES_GATEWAY_URL"
env | grep -E '^ANTHROPIC_API_KEY=' || echo "ANTHROPIC_API_KEY is unset (good)"
claude auth status
```

**Expect:** token length 64, URL exactly `http://127.0.0.1:8000/api/gateway/pre-tool`, `ANTHROPIC_API_KEY is unset (good)`, and `"loggedIn": true`. Keep this terminal open. `claude` started from another terminal will not see `HERMES_GATEWAY_TOKEN` and will fail-closed.

## 17. Stdin dry-run (capture the deny JSON)

```bash
LIVE="$HOME/hermes-gateway-live"
# env still from step 16
printf '%s\n' '{"session_id":"dry-run","tool_name":"Bash","tool_input":{"command":"echo dry-run"}}' \
  | python3 "$LIVE/hermes-synapse/scripts/gateway/claude_pre_tool_use.py"
```

**Expect:** one JSON line, `"permissionDecision": "deny"`, reason `Pending approval for Bash (request_id=…). Retry this tool with identical arguments…`. Exit code 0. Save this terminal output for the DoD packet (redact nothing if the token is absent; if it appears, the run is invalid).

## 18. Start Claude Code in the throwaway project

Same shell as step 16 (subscription login, `ANTHROPIC_API_KEY` unset):

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/test-project"
claude
```

**Expect:** Claude starts in `test-project` on the **subscription** session (no API-key banner / API billing). If it asks to trust the folder, trust **this folder only**. Confirm it is not using `~/.claude/settings.json` for this hook (project settings in `.claude/settings.json` in cwd).

The remaining prompts use **a few subscription messages**. Paste **exactly** this first prompt:

```text
Using the Bash tool only, create a file named hello.txt in the current directory
containing the single line gateway-live-check. Do not use the Write tool.
```

**Expect:** PreToolUse runs. Claude reports the tool was blocked / denied. `hello.txt` is **not** created yet:

```bash
test ! -e "$HOME/hermes-gateway-live/test-project/hello.txt" && echo "hello.txt absent (pending)"
```

## 19. PENDING in Approvals UI

Open **http://127.0.0.1:9119**. Click **Approvals**.

**Expect:** badge `1`. One row, status chip **PENDING**. CLAIM shows action `Bash` (or `execute_command` is wrong — that would mean you hit the Hermes chat, not Claude). Args include `hello.txt` / `gateway-live-check`. Screenshot this (no `.env`, no token).

## 20. Approve, then retry once

In the Approvals row: resolver note `live-check approve hello.txt` → **Approve**.

**Expect:** chip **APPROVED**. Badge `0`. `hello.txt` still absent (Approve does not run the tool).

In the Claude session, tell it:

```text
Retry the same Bash command with identical arguments.
```

**Expect:** the hook allows this time. `hello.txt` exists with exactly one line:

```bash
cat "$HOME/hermes-gateway-live/test-project/hello.txt"
```

**Expect:** `gateway-live-check`

In Approvals, switch to **All**. That row is **CONSUMED**. Screenshot (pending-before and approved/consumed). A second retry of the same command becomes a **new** PENDING (consume-once). Stop; do not approve that new row if you do not need it.

## 21. Reject case

New Claude prompt:

```text
Using the Bash tool only, create a file named reject-me.txt containing the
single line should-not-exist.
```

**Expect:** deny / PENDING. Approvals badge `1`. File absent.

In Approvals: **Reject** with note `live-check reject`.

Then in Claude:

```text
Retry the same Bash command with identical arguments.
```

**Expect:** still denied (sticky REJECTED in that session). File still absent:

```bash
test ! -e "$HOME/hermes-gateway-live/test-project/reject-me.txt" && echo "reject-me.txt absent (good)"
```

## 22. Backend-down fail-closed

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
docker compose \
  -f docker-compose.yml \
  -f docs/gateway/docker-compose.gateway-live.yml \
  stop backend
```

In Claude (same project, env still set):

```text
Using the Bash tool only, create a file named down.txt containing the
single line should-be-blocked.
```

**Expect:** hook deny with `backend unreachable` / `fail-closed` (or Claude reports the hook blocked the tool because `onFailure` is `block`). `down.txt` is **not** created. This is the fail-closed check.

```bash
test ! -e "$HOME/hermes-gateway-live/test-project/down.txt" && echo "down.txt absent (fail-closed)"
```

Bring the API back:

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
docker compose \
  -f docker-compose.yml \
  -f docs/gateway/docker-compose.gateway-live.yml \
  start backend
# wait until :8000 answers
until curl -sf http://127.0.0.1:8000/api/status >/dev/null; do sleep 1; done
echo "backend back"
```

## 23. Export and verify the decision log

Need a Hermes dashboard **session** token, not `HERMES_GATEWAY_TOKEN` and not an Anthropic key. If `HERMES_SESSION` from step 14 is empty, log in again (request-code + OTP) and export `token` from the JSON.

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
# if needed, refresh HERMES_SESSION (do not print it)
curl -fsS -H "Authorization: Bearer $HERMES_SESSION" \
  http://127.0.0.1:9119/api/governance/decisions/export.zip \
  -o "$LIVE/decisions.zip"
curl -sS -H "Authorization: Bearer $HERMES_SESSION" \
  http://127.0.0.1:9119/api/governance/decisions/verify
echo
python3 scripts/verify_decision_log.py "$LIVE/decisions.zip"
# Gateway rows on the chain:
python3 - << 'PY'
import zipfile, json
from pathlib import Path
z = zipfile.ZipFile(Path.home() / "hermes-gateway-live" / "decisions.zip")
events = [json.loads(l)["event"] for l in z.read("decisions.jsonl").decode().splitlines() if l.strip()]
print("events", events)
assert "HOOK" in events and "REQUESTED" in events
print("gateway HOOK+REQUESTED present (good)")
PY
```

**Expect:** verify API `"ok": true`. Script prints `ok checked=<N> head=<64 hex>`. Events include `HOOK` and `REQUESTED` (and `APPROVED`/`CONSUMED`/`REJECTED` from the UI steps). Optional pin:

```bash
HEAD=$(python3 scripts/verify_decision_log.py "$LIVE/decisions.zip" | awk -F= '/head=/{print $NF}')
python3 scripts/verify_decision_log.py "$LIVE/decisions.zip" --pin "$HEAD"
```

**Expect:** `ok checked=… head=…` again. Confirm the zip has no token:

```bash
python3 - << 'PY'
from pathlib import Path
import os, zipfile
live = Path.home() / "hermes-gateway-live"
token = None
for line in (live / "hermes-synapse" / ".env").read_text().splitlines():
    if line.startswith("HERMES_GATEWAY_TOKEN="):
        token = line.split("=", 1)[1].strip()
z = live / "decisions.zip"
data = z.read_bytes()
assert token and token.encode() not in data
print("token absent from decisions.zip (good)")
print("zip bytes", z.stat().st_size)
PY
```

Signed checkpoints (same chain; `HERMES_REQUIRE_SIGNING` stays false). Run the verifier **in the backend container** so the Mac does not need `cryptography` or any Anthropic key:

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
curl -fsS -H "Authorization: Bearer $HERMES_SESSION" \
  http://127.0.0.1:9119/api/governance/decisions/export.signed.json \
  -o "$LIVE/hermes-audit-default.json"
docker cp "$LIVE/hermes-audit-default.json" jarvis-backend:/tmp/hermes-audit-default.json
docker compose exec -T backend python3 -m hermes_audit_verify /tmp/hermes-audit-default.json
python3 - << 'PY'
import json
from pathlib import Path
b = json.loads((Path.home() / "hermes-gateway-live" / "hermes-audit-default.json").read_text())
events = [r["event"] for r in b["records"]]
assert "HOOK" in events and "REQUESTED" in events
assert b["checkpoints"], "export must include a checkpoint"
print("signed bundle covers gateway events; checkpoints", len(b["checkpoints"]))
PY
```

**Expect:** `ok checked=N head=… unsigned_tail=0 fingerprint=…` and `signed bundle covers gateway events`.

---

## Rollback

Do this even if a middle step failed.

### 24. Remove project-local settings

```bash
LIVE="$HOME/hermes-gateway-live"
rm -rf "$LIVE/test-project/.claude"
# do not touch $HOME/.claude/settings.json
```

**Expect:** `$LIVE/test-project/.claude` gone. Global Claude settings unchanged.

### 25. Compose down and delete volumes

```bash
LIVE="$HOME/hermes-gateway-live"
cd "$LIVE/hermes-synapse"
docker compose \
  -f docker-compose.yml \
  -f docs/gateway/docker-compose.gateway-live.yml \
  down -v
docker compose ps
```

**Expect:** no `jarvis-*` containers. Named volumes for this project directory removed.

### 26. Delete the throwaway tree and unset the token

```bash
unset HERMES_GATEWAY_TOKEN HERMES_GATEWAY_URL HERMES_SESSION HERMES_GATEWAY_BIND
LIVE="$HOME/hermes-gateway-live"
rm -rf "$LIVE"
test ! -e "$LIVE" && echo "removed $LIVE"
```

**Expect:** directory gone. `echo $HERMES_GATEWAY_TOKEN` empty. Quit the Claude session that had the token in its environment.

---

## What to send back for DoD

Do **not** send `.env`, OTP, `HERMES_GATEWAY_TOKEN`, `HERMES_SESSION`, or any screenshot that shows them.

1. **CLI version + subscription** — paste `claude --version` and `claude auth status` with `"loggedIn": true` (no tokens in that JSON). Also paste `ANTHROPIC_API_KEY is unset (good)` from step 5 or 16.
2. **SHA** — `git -C … rev-parse HEAD` of the clone. Branch must be `cursor/gateway-mvp-2164`, not `main`.
3. **Screenshot: PENDING** — Approvals UI at `http://127.0.0.1:9119` with the Bash `hello.txt` row PENDING.
4. **Screenshot: APPROVED then CONSUMED** — same request after Approve; All tab after the successful retry (CONSUMED).
5. **Terminal: hook deny** — the JSON from step 17 (stdin dry-run) showing `permissionDecision: deny` and `Pending approval`.
6. **Terminal: fail-closed** — step 22, `down.txt absent (fail-closed)` plus Claude’s blocked-tool message (or the hook JSON if you re-ran stdin against `:8000` while backend was stopped: `backend unreachable`).
7. **Verifier output** — `ok checked=N head=…` from `python3 scripts/verify_decision_log.py`, plus `HOOK` in the zip events.
8. **`decisions.zip`** — the export from step 23. Confirm locally that the gateway token is not in the zip before sending. Optional: container `python3 -m hermes_audit_verify` of `export.signed.json` (`unsigned_tail=0`, `HOOK` in records).
9. **Reject proof** — `reject-me.txt absent (good)` plus a screenshot of the REJECTED chip, or the All-tab row.
10. **Notes** — Claude Code version, macOS version, the `HERMES_GATEWAY_BIND` value you used (IPs only, no token), and anything that did not match **Expect**.
