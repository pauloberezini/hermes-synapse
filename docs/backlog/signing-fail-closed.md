# Estimate: fail-closed signing (`HERMES_REQUIRE_SIGNING`)

Internal. Not implemented. Against `origin/main` `e57c345`.

Today `backend/main.py` lifespan calls `ensure_install_key()` and on any exception logs `audit signing key init failed` and continues. `GET /api/governance/decisions/export.signed.json` then calls `ensure_install_key()` again (and will auto-create a key if the data dir is writable). Periodic checkpoints in `_try_checkpoint` swallow errors. The zip export is unchanged either way.

## Default

Keep **off**. `HERMES_REQUIRE_SIGNING` unset or `false` = current warn-and-continue. Opt-in `true` for a buyer who will not ship unsigned JSON.

Compose and `.env.example` must not flip this on. Existing VMs with a read-only or empty data dir would fail to boot.

## What to change

Product code (small):

1. `backend/audit_signing.py` — `require_signing() -> bool` from `HERMES_REQUIRE_SIGNING` (`"true"` / `"1"`). Do not auto-create a key when the flag is on: missing, unreadable, wrong type, or not mode `0600` is a hard error. When the flag is off, keep generate-on-first-use.
2. `backend/main.py` lifespan — if the flag is on, `ensure_install_key()` failure uses the same `os._exit` path as `enforce_runtime_secrets()` (no uvicorn traceback, compose `unless-stopped` still restarts). If off, keep the warning.
3. `export.signed.json` and `GET /api/governance/audit/key` — if the flag is on and there is no valid key, return **503** with a short body (`signing unavailable`), not 500, not a bundle. Zip `/export.zip` stays hash-only.
4. Leave `_try_checkpoint` best-effort. Appends to `approval_decisions` must not fail closed; the signed export is the gate.

No RBAC. No zip-format change.

## Tests

- Flag off, missing key: start continues, warning once (today's test plus an assert the warning still fires).
- Flag on, missing key / corrupt PEM / non-Ed25519: process exits non-zero (lifespan helper, not a live uvicorn if a function extract is easier).
- Flag on, valid `0600` key: start ok, fingerprint logged, signed export 200, `hermes_audit_verify` exit 0.
- Flag on, key later unreadable: `export.signed.json` 503; zip export still 200.
- Flag off: signed export may still create a key (document that).

Reuse `backend/tests/test_signed_audit_log.py` and the temp `HERMES_AUDIT_KEY_PATH` fixture in `conftest.py`.

## Docs / runbook

- `docs/security/signed-audit-log.md` — new "Fail closed" section: env, 503, zip still works, pin the fingerprint after first successful boot with the flag off, then set the flag.
- `docs/pilot-runbook.md` — one paragraph under backups / verify: do not enable on first `compose up`; enable after the key file exists on `backend_data`.
- `.env.example` — commented `HERMES_REQUIRE_SIGNING=false` next to `HERMES_AUDIT_KEY_PATH`.
- `docker-compose.yml` / `docker-compose.dev.yml` — pass through `${HERMES_REQUIRE_SIGNING:-false}` so a buyer can set it in `.env` without editing compose. Default **false**.

## Risks

- Auto-create vs provision: if the flag is on and the volume is empty, boot loops (`restart: unless-stopped`). That is intended; say so in the runbook.
- Read-only container + missing key: already a warning today; with the flag it becomes a crash loop.
- Tests that boot `app` without a key file: `conftest.py` already sets `HERMES_AUDIT_KEY_PATH` under a temp dir; keep the flag unset in tests unless a case sets it.
- Checkpoints on the write path stay best-effort; a buyer who wants fail-closed *appends* is a different, larger change.

## Hours

About **5 hours**: 2 for the flag + lifespan + 503, 1.5 for tests, 1 for docs/compose/`.env.example`, 0.5 for a compose boot check with the flag on and off.
