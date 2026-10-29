# Governance Approvals & Audit Decision Log

This guide walks through human-in-the-loop governance in Hermes Synapse: tool calls that need authorization capture evidence bundles, record a tamper-evident decision log, and can be checked offline.

---

## 1. Overview & Architecture

When an autonomous agent invokes a sensitive action (for example `execute_command`), execution halts in `PENDING` and registers an approval request:

1. **Evidence Bundle Capture**: The system captures execution context including:
   - **Plan Context**: The current plan step index, total steps, and step instructions from the orchestrator.
   - **Inputs**: Tool invocation arguments (redacted of API keys and PII tokens).
   - **Upstream Items**: Preceding tool outputs and step outputs, bounded by size caps and marked with truncation chips if truncated.
   - **Canonical Hash**: A deterministic SHA-256 hash over canonical JSON (RFC 8785) after PII redaction.
2. **Operator Review (Claim/Source Split)**:
   - Operators see a badge showing pending authorization requests.
   - Clicking opens the **Approvals Modal** displaying a split view:
   - **CLAIM**: Target tool, the agent name, the session id, sanitized arguments, bundle SHA-256 hash, and approval controls. `agent_id` on the request is the session-scoped match key, not an agent id. An approval granted in one session cannot be spent in another.
   - **SOURCE**: Planner step details, upstream tool outputs, and truncation indicators. A direct chat has no planner. SOURCE still shows the user's instruction, and the bundle carries the flag `direct_route`.
3. **Immutable Decision Log**:
   - Every lifecycle transition (`REQUESTED`, `APPROVED`, `REJECTED`, `CONSUMED`) appends to an append-only, tamper-evident hash chain (`approval_decisions`).
   - Each entry links to the previous entry's `entry_hash` (or 64 zeros at genesis). `APPROVED` records the operator's `Principal` subject. `CONSUMED` is written by `system`.
   - Database triggers reject `UPDATE` and `DELETE` on `approval_decisions`. `approval_evidence` rejects `UPDATE`. `DELETE` on evidence stays allowed so deleting a request can cascade.
   - The log is tamper-evident. A party who rewrites the whole chain and the copy of the head hash you kept still passes the verifier. Pin that head hash with `--pin` so a truncated tail is detected.
   - Identical calls share one `bundle_hash`. The hash binds the redacted bundle content, not the request id.

---

## 2. Interactive Demo Walkthrough

> **Demo hygiene.** Never put real keys or tokens in demo prompts. The masker only catches known formats, and tool arguments are still written to the server log.

### Step 1: Trigger an Approval Request

Use the orchestrator with a Sys Ops step that holds `execute_command`. Do not use the `code` agent: it runs generated Python in a sandbox and never consults the approval gate.

From the Web UI Communication Link, ask the orchestrator to run a shell command:

```text
Please run `uname -a` and tell me the result.
```

A direct chat has no planner. SOURCE shows the user's message and the flag `direct_route`, which means no planner chose the step.

`execute_command` is high-risk, so execution stops:

- The backend creates an `approval_requests` row in `PENDING` status. The raw arguments stay in that row so a later identical call can match. API responses mask them.
- An `approval_evidence` row is created with a SHA-256 hash and a redacted bundle.
- An event of type `REQUESTED` is appended to `approval_decisions`.
- A WebSocket event `{ "type": "approval_update", "id": <id>, "status": "PENDING" }` is broadcast.

### Step 2: Review Evidence in Approvals UI

1. The **Approvals** badge shows `1` within about a second on a healthy socket. If the socket is down, the badge polls every 10 seconds.
2. Click the badge to open the **Governance Approvals** modal.
3. Click **Show evidence #<id>** on the pending item:
   - Under **CLAIM**, verify the command payload, the agent name (for example Sys Ops) beside the session id, and the evidence SHA-256 hash.
   - Under **SOURCE**, review the planner step context and upstream excerpts. `plan` is present for an orchestrator step and for a direct chat (`direct_route`).
   - Keys are redacted in the `[API_KEY_OPENAI_REDACTED]` style.

### Step 3: Approve the Request

1. In the **resolver note** field, enter:

   ```text
   Approved for directory inspection
   ```

2. Click **Approve** (or press key `A` when the row is focused).
3. The request transitions to `APPROVED`:
   - Status updates in the database.
   - An `APPROVED` entry is appended to the decision log with the authenticated `Principal` identity (`local-admin` or JWT subject).
   - The badge count drops to 0.

Nothing runs on Approve. The original tool call already returned `PENDING_APPROVAL` to the model.

### Step 4: Re-send, then the tool runs once (`CONSUMED`)

Re-send the same request. The model must call the tool again with identical arguments. The gate finds the `APPROVED` row, consumes it, and runs the tool once.

1. The operator re-sends the same prompt.
2. `ApprovalQueue.consume` marks the row `CONSUMED` and the tool runs once.
3. A `CONSUMED` entry is appended to the decision log. `CONSUMED` is a normal finished state, shown in a neutral tone.
4. Sending the same prompt again opens a **new** `PENDING` request. The previous approval is not reused, and the new request is not a rejection.

If the model changes the arguments, that is a different call and a new request.

A rejected call stays blocked in that same session. The same call in a new session opens a new request, because the match key is the session.

---

## 3. Export & Offline Independent Verification

Export the decision log as a zip of `decisions.jsonl`, `evidence/<id>.json`, a plain `manifest.json`, and `VERIFY.md`.

### Exporting Decisions

```bash
curl -f -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/governance/decisions/export.zip" \
  -o decisions.zip
```

`-f` makes curl fail on a 401 or 404 instead of saving the error body as a zip. `/api/governance/decisions/export` is the same handler. Optional query: `?from=YYYY-MM-DD&to=YYYY-MM-DD&tenant=`.

The checker is not inside the zip. It lives at `scripts/verify_decision_log.py`.

### Verifying Offline (Zero Third-Party Dependencies)

```bash
python3 scripts/verify_decision_log.py decisions.zip
```

A valid chain prints to stdout and exits 0:

```text
ok checked=N head=H
```

Record that head hash. A later check with `--pin` fails if the tail was dropped and `manifest.json` was rewritten to match:

```bash
python3 scripts/verify_decision_log.py decisions.zip --pin <entry_hash>
```

If a row or hash was altered, the script prints `FAIL seq=N <reason>` to stderr and exits 1. A missing pin prints `pinned entry missing`.

---

## 4. REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/governance/approvals` | `GET` | List approval summaries (`?pending_only=true`). `payload` is masked. |
| `/api/governance/approvals/{id}` | `GET` | Fetch approval detail with redacted evidence bundle |
| `/api/governance/approvals/{id}/resolve` | `POST` | Resolve request (`APPROVED` or `REJECTED`) |
| `/api/governance/approvals/count` | `GET` | Get count of pending approvals |
| `/api/governance/decisions` | `GET` | Paginated decision log history (`before_seq`, `limit`) |
| `/api/governance/decisions/verify` | `GET` | Run in-database chain verification |
| `/api/governance/decisions/export` | `GET` | Export the audit zip (`decisions.jsonl`, evidence, manifest, `VERIFY.md`) |
| `/api/governance/decisions/export.zip` | `GET` | Same archive as `/export` |
