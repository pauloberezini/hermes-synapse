# Hermes Synapse — sample evidence pack

Built from `make demo` (scripted agent, demo seed data only). Hash-chained
decision log, not a signature scheme. No Ed25519 signed-audit-log in this pack.

## What's inside

| File | What |
| --- | --- |
| `decision-log.zip` | Unchanged demo `export_zip` (`decisions.jsonl`, `evidence/*.json`, `manifest.json`) |
| `decision-log.tampered.zip` | Same archive with one `reason` field edited |
| `verifier-ok.txt` | `scripts/verify_decision_log.py` on the clean export |
| `verifier-fail.txt` | Same checker on the tampered copy |
| `calls.json` / `calls.csv` / `calls.md` | APPROVED/REJECTED: tool, decision, timestamp, payload SHA-256 (no raw payloads) |
| `policy.json` | `HIGH_RISK_TOOLS` plus the `CODE_AGENTS_ENABLED` values the demo pins |

## Verify

From the repository root (Python stdlib, no Hermes install, no network):

```bash
python3 scripts/verify_decision_log.py docs/demo/evidence/decision-log.zip
python3 scripts/verify_decision_log.py docs/demo/evidence/decision-log.tampered.zip
```

Expect exit 0 and `ok checked=N head=H` on the first. Expect exit 1 and
`FAIL seq=… entry_hash mismatch` on the second.

Optional pin (head hash is the last token in `verifier-ok.txt`):

```bash
python3 scripts/verify_decision_log.py docs/demo/evidence/decision-log.zip --pin <head>
```

Regenerate: `make evidence`.
