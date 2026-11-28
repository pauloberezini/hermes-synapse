---
title: Signed audit log
description: Ed25519 installation key, signed checkpoints, signed JSON export, and python -m hermes_audit_verify.
---

# Signed audit log

The decision log is still a SHA-256 hash chain (`backend/decision_log.py`). This page covers the extra signatures on that chain: an installation Ed25519 key, checkpoints stored in `decision_log_checkpoints`, a JSON export, and an offline verifier that does not need the server or the database.

Hash-only zip export (`scripts/verify_decision_log.py --pin`) is unchanged.

## How it works

1. **Installation key.** On first start the process generates an Ed25519 keypair if `HERMES_AUDIT_KEY_PATH` (default `backend/data/audit_ed25519.key`) is missing. The private key is written at mode `0600`. A UUID installation id sits next to it in `*.key.id`. Compose already mounts `backend_data` on `/app/backend/data`.
2. **Fingerprint.** `sha256(raw 32-byte public key)` as hex. Logged once at start: `audit signing key fingerprint=… installation_id=…`.
3. **Checkpoints.** Every `HERMES_AUDIT_CHECKPOINT_EVERY` rows (default 100), and always on signed export, the process signs canonical JSON of `{seq, head_hash, timestamp, installation_id}` and stores the row. Inserts are idempotent (`INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`).
4. **Export.** `GET /api/governance/decisions/export.signed.json` returns JSON with `version`, `records`, `checkpoints`, `public_key`, `pubkey_fingerprint`, `installation_id`. The offline checker also accepts JSONL (`type=header|record|checkpoint`).
5. **Verify.** `python -m hermes_audit_verify bundle.json [--pubkey-fingerprint HEX]` walks the hash chain, checks every checkpoint signature, and fails if the last checkpoint does not cover the tail (unsigned tail length is printed). Exit 0 / 1 / 2.

Crypto is `cryptography` (already a transitive dependency; now declared as `cryptography>=42`). No external KMS.

## Pin the fingerprint at install

```bash
# after first boot, while you still trust the host
curl -sS -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:9119/api/governance/audit/key
# or, on the host:
python -m backend.audit_signing
```

Copy `pubkey_fingerprint` into your runbook / password manager / a file **off this machine**. Later:

```bash
curl -sS -H "Authorization: Bearer <TOKEN>" \
  "http://127.0.0.1:9119/api/governance/decisions/export.signed.json" \
  -o hermes-audit-default.json

python -m hermes_audit_verify hermes-audit-default.json \
  --pubkey-fingerprint <hex you pinned at install>
```

A valid bundle prints `ok checked=N head=H unsigned_tail=0 fingerprint=…` and exits 0.

## Key rotation (manual, minimal)

1. Export a signed bundle and store it off-host. Verify it with the **current** fingerprint.
2. Stop the process. Move `audit_ed25519.key` and `audit_ed25519.key.id` aside (keep them if you still need to explain old bundles).
3. Start. A new key and installation id are created. Pin the new fingerprint.
4. Old bundles still verify with the public key **inside that bundle**, or with the old fingerprint. New exports use the new key. There is no dual-sign or grace period.

## Honest limitation

The private key lives on the same host as the log. Signatures stop **post-export tampering** and stop a non-admin user who can read the database but not the key file. They do **not** stop root (or anyone who can read `HERMES_AUDIT_KEY_PATH`) from rewriting the chain and re-signing it.

Mitigation: pin the fingerprint at install, and periodically copy signed checkpoints off-host. A later export that verifies with a *different* fingerprint is a rotation or a compromise; treat it as an incident unless you rotated.

## CLI

```text
python -m hermes_audit_verify bundle.json [--pubkey-fingerprint HEX]
python -m backend.audit_signing
```

| Exit | Meaning |
|---|---|
| 0 | Chain, signatures, fingerprint, and tail coverage all match |
| 1 | Tamper, truncate, reorder, bad signature, or fingerprint mismatch |
| 2 | Usage, missing file, or unreadable bundle |

Env: `HERMES_AUDIT_KEY_PATH`, `HERMES_AUDIT_CHECKPOINT_EVERY` (default 100), `HERMES_REQUIRE_SIGNING` (default false).

## Fail closed

`HERMES_REQUIRE_SIGNING` is **off** unless you set `true` / `1` / `yes`. Off is today's behaviour: missing key is created on first use, and a load failure is a warning, not a crash.

Turn it on only after a successful boot has written `audit_ed25519.key` on `backend_data` and you have pinned `pubkey_fingerprint` off-host. Then:

1. Set `HERMES_REQUIRE_SIGNING=true` in `.env`.
2. Recreate the backend (`docker compose up -d --force-recreate --no-deps backend`).

When the flag is on:

- Startup exits 1 with one `FATAL:` line if the key is missing, unreadable, not Ed25519, or not mode `0600`. Compose `restart: unless-stopped` will crash-loop until you drop a valid key or set the flag back to `false`. That loop is intended.
- `GET /api/governance/decisions/export.signed.json` and `GET /api/governance/audit/key` return **503** `{ "detail": "signing unavailable" }` if the key later disappears. The zip export still works.
- Appends to the decision log still succeed; periodic checkpoints stay best-effort.
