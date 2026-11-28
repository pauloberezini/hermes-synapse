# Hermes Synapse: sample evidence pack

This is not legal advice. This pack does not make you compliant.

This sample pack does not include signed checkpoints. The zip log
carries no signatures. In real use the pin is recorded off-host
(for example in the email that carries the export), and a pin stored
inside the same zip is a demonstration.

Every payload, every name and every file in this pack is synthetic
(`partner.example`, `customers.csv`, `demo-operator`). Nothing came from
a real install or client.

Built from `make demo` (scripted agent, mocked shell and sandbox).
Times in the lists are UTC (`occurred_at`). The role on each row is
recorded and not enforced.

## Known limits (short)

- The approve endpoint checks no role. Any logged-in session can approve, and the log records the subject, the roles and the login method. RBAC is not wired.
- The log in this sample pack is tamper-evident with a pinned head hash and carries no signatures.
- No SOC 2 and no named customers.
- Approvals cover agents running in Hermes, with no gateway in front of other clients.
- Code agents are off by default.
- This sample comes from a scripted agent with a mocked shell and sandbox.

Full list: `limits/known-limits.md`.

## What's inside

| File | What |
| --- | --- |
| `decision-log.zip` | Unchanged demo export (`decisions.jsonl`, `evidence/*.json`, `manifest.json`) |
| `decision-log.tampered.zip` | Same archive with the reason of seq 1 edited to `tampered` |
| `verifier/verify_decision_log.py` | Byte copy of the repository checker |
| `verifier-ok.txt` | Checker output on the clean export |
| `negative-control-expected-output.txt` | Checker output and exit code on the tampered copy |
| `pinned-head-hash.txt` | 64 hex characters, one line, no prefix |
| `approvals/calls.json` / `.csv` / `.md` | All decision rows: tool, event, who, roles, login method, reason, UTC time, payload SHA-256 |
| `config/config-snapshot.json` | `HIGH_RISK_TOOLS` from `_high_risk_names()`, MCP rule, `pilot_default` false, commit |
| `SUMMARY.md` | One-page compliance summary |
| `MANIFEST.json` | SHA-256 and size of every file in this pack |
| `limits/known-limits.md` | Eleven known limits |

The inner `VERIFY.md` still points at the repository copy of the checker, for comparison.

## Verify

From this unzipped folder (Python 3.11+ standard library, no Hermes install, no network):

```bash
python3 verifier/verify_decision_log.py decision-log.zip
python3 verifier/verify_decision_log.py decision-log.zip --pin "$(cat pinned-head-hash.txt)"
python3 verifier/verify_decision_log.py decision-log.tampered.zip
```

Expect exit 0 and `ok checked=N head=H` on the first two. Expect exit 1 and
`FAIL seq=1 entry_hash mismatch` on the third (see `negative-control-expected-output.txt`).

Regenerate from a checkout: `make evidence`.
