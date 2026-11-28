---
title: 7-minute demo stand
description: One-command scripted walkthrough of gate_tool, payload-bound approve/reject, and offline SHA-256 decision-log verification. No LLM keys.
---

# 7-minute demo stand

One command: `make demo`. No OpenRouter key, no Docker, no live payments or deletes.

The agent is **scripted**. It calls the same `execute_tool` → `gate_tool` path a model would, with canned payloads. Tool bodies are mocked: `execute_command` never reaches a shell, and `execute_code` never reaches the sandbox container.

Talk track below. Timings are presenter time over the printed output, not wall-clock of the script (it finishes in seconds). Optional: `make demo PAUSE=1` waits for Enter at each beat.

Live dashboard clicks are **optional** and labeled. They need Compose plus a model; `make demo` does not.

## Honesty label (say this first)

- **Real:** `HIGH_RISK_TOOLS`, `gate_tool`, `ApprovalQueue` (one-time, payload-bound), SHA-256 hash-chained `approval_decisions`, `scripts/verify_decision_log.py`.
- **Scripted:** the "agent" is `scripts/demo.py`, not Jarvis + an LLM.
- **Mocked:** shell and sandbox HTTP. The reject payload looks like `rm -rf /var/lib/hermes-demo` and must not run.
- **Missing on purpose:** there is no `send_payment` tool. Delete is `execute_command`; code is `execute_code`.
- **Not claimed:** the log is tamper-evident. It is not a signature scheme. Pin the head hash.

## 0:00–0:30 — Setup

**Do:** from the repo root,

```bash
make demo
```

(`make demo-reset` only deletes `backend/data/demo/`.)

**Say:** We are not calling a model. A scripted Sys Ops and a scripted Code Engineer hit the real gate.

**Expect:**

```text
[demo] SCRIPTED AGENT — no LLM, no API keys
[demo] real modules: gate_tool, HIGH_RISK_TOOLS, ApprovalQueue, decision_log
[demo] mocked: backend.tools.execute_command, sandbox HTTP POST
```

**Optional UI:** Approvals badge in the sidebar. Do not send a live `rm` in Communication Link.

## 0:30–1:30 — Reject path

**Show:** the first PENDING row.

**Say:** Sys Ops tried to delete a resource. The gate stopped it. You see the exact command, the session id, and `bundle_hash`. Nothing has run.

**Expect:**

```text
[demo] scripted Sys Ops → execute_command rm -rf /var/lib/hermes-demo
[demo] request #<id> status=PENDING
[demo]   CLAIM agent='Sys Ops' session='demo-reject'
[demo]   CLAIM action=execute_command payload={"command": "rm -rf /var/lib/hermes-demo"}
[demo]   CLAIM bundle_hash=<64 hex>
[demo]   SOURCE ... flags=['direct_route']
```

**Do (script already does this):** operator rejects with note `Destructive delete. Rejected for this session.` Script retries the identical payload in `demo-reject`.

**Say:** Reject is sticky in that session. Same args, same session, still `REJECTED`. The shell mock still has zero calls.

**Expect:**

```text
[demo] operator REJECTED #<id> ...
[demo] retry status=REJECTED
```

**Optional UI:** Governance Approvals → expand evidence → **Reject**. A live retry needs the model to emit the same tool call again.

## 1:30–3:30 — Approve path (one-time, payload-bound)

**Show:** the second PENDING row, `execute_code` / `print('hermes-demo-ok')`, agent `Code Engineer`, session `demo-approve`. Different payload, different `bundle_hash`.

**Say:** Approve does **not** run the tool. The original call already returned `PENDING_APPROVAL`. The next identical call consumes the row once.

**Expect after Approve, before retry:**

```text
[demo] operator APPROVED #<id> note='Read-only print. OK once.'
[demo] status=APPROVED sandbox_posts=0 (must be 0)
```

**Expect after identical retry:**

```text
[demo] execute_code → success=True stdout='hermes-demo-ok\n'
[demo] request #<id> status=CONSUMED sandbox_posts=1
```

**Expect on a third call:**

```text
[demo] replay status=PENDING_APPROVAL request_id=<new id>
```

**Say:** Consumed approvals are not reused. A new `PENDING` is a new human decision, not a free pass.

**Optional UI:** **Approve** (or `A` when focused) with a resolver note. Re-send the same chat. All tab shows `APPROVED` → `CONSUMED`. A third send is a new badge count.

## 3:30–5:30 — Decision log, export, pin

**Show:** the seq list.

**Say:** Every `REQUESTED` / `REJECTED` / `APPROVED` / `CONSUMED` appends a SHA-256 digest over canonical fields plus `prev_hash`. Genesis is 64 zeros. `APPROVED` is `demo-operator`. `CONSUMED` is `system`.

**Expect:** `verify ok=True checked=N head=<64 hex>` and

```text
ok checked=N head=H
```

from `scripts/verify_decision_log.py <zip> --pin <head>`. Exit 0. The checker is stdlib-only and is **not** inside the zip.

**Optional UI:** there is no hash-chain screen. Use

```bash
curl -f -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:9119/api/governance/decisions/verify
curl -f -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:9119/api/governance/decisions/export.zip -o decisions.zip
python3 scripts/verify_decision_log.py decisions.zip --pin <head_hash>
```

## 5:30–6:40 — Tamper one record

**Show:** the script copies the zip, sets `reason` to `tampered` on the first `decisions.jsonl` row, leaves `entry_hash` as-is.

**Say:** We did not rewrite the digest. The verifier recomputes it.

**Expect:**

```text
FAIL seq=<n> entry_hash mismatch
```

exit 1. In-DB `verify` on the untouched demo DB is still ok — we tampered the export, not the live chain.

## 6:40–7:00 — Close

**Say:**

1. Risky tools stop at the gate.
2. Humans see the payload. Reject sticks. Approve is one-shot and payload-bound.
3. The export is checkable offline. Tampering a row without rewriting the whole chain fails. Pin the head.

**Do not say:** the zip is confidential, the manifest is a signature, or that the chain is unforgeable if the attacker also replaces your pin.

## Commands

| Command | What |
|---|---|
| `make demo` | Isolated SQLite under `backend/data/demo/`, full walkthrough |
| `make demo PAUSE=1` | Same, wait for Enter at each beat |
| `make demo-reset` | Delete the demo DB and leftover zips |
| `python3 scripts/demo.py --seed` | Two PENDING rows only (still mocked) |

Headless check: `cd backend && uv run pytest tests/test_demo_flow.py`.

## Gaps (do not paper over)

| Topic | Status |
|---|---|
| `send_payment` | Does not exist. Not faked. |
| Dashboard hash-chain viewer | API + this script only |
| Live model retry | Not this stand. Guide: [Approvals walkthrough](../guide/approvals.md) |
| RBAC | Untouched. Operator principal is `demo-operator` / `otp` |
| `BudgetGuard` / `PIIGuard` | Real, not exercised here |
| `approval_requests.payload` | Raw in SQLite for matching (R2-4). CLAIM/API are masked |
