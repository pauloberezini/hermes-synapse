# Governance Approvals & Audit Decision Log

This guide walks through human-in-the-loop governance in Hermes Synapse, explaining how tool calls requiring authorization capture verifiable evidence bundles, record tamper-evident decision logs, and allow offline compliance verification.

---

## 1. Overview & Architecture

When an autonomous agent invokes a sensitive action (e.g. `execute_command` or filesystem modifications), the execution halts in `PENDING` state and registers an approval request:

1. **Evidence Bundle Capture**: The system captures execution context including:
   - **Plan Context**: The current plan step index, total steps, and step instructions from the orchestrator.
   - **Inputs**: Tool invocation arguments (redacted of API keys and PII tokens).
   - **Upstream Items**: Preceding tool outputs and step outputs, bounded by size caps and marked with truncation chips if truncated.
   - **Canonical Hash**: A deterministic SHA-256 hash calculated over canonical JSON (RFC 8785) after PII redaction.
2. **Operator Review (Claim/Source Split)**:
   - Operators see a badge showing pending authorization requests.
   - Clicking opens the **Approvals Modal** displaying a split view:
     - **CLAIM**: Target tool, agent identity, sanitized arguments, bundle SHA-256 hash, and approval controls.
     - **SOURCE**: Planner step details, upstream tool outputs, and truncation indicators.
3. **Immutable Decision Log**:
   - Every lifecycle transition (`REQUESTED`, `APPROVED`, `REJECTED`, `CONSUMED`) appends to an append-only, tamper-evident hash chain (`approval_decisions`).
   - Each entry links to the previous entry's `entry_hash` (or 64 zeros at genesis), signed with the operator's `Principal` identity.
   - Database triggers enforce append-only guarantees at the storage layer, rejecting any `UPDATE` or `DELETE`.

---

## 2. Interactive Demo Walkthrough

Follow these steps to demonstrate the end-to-end governance lifecycle:

### Step 1: Trigger an Approval Request

From the Web UI Communication Link (or API), instruct the agent to run a shell command:
```text
Please run `ls -la` to list files in the current workspace.
```

The agent attempts to execute `execute_command`. Because `execute_command` is a high-risk tool requiring approval, execution stops:
- The backend creates an `approval_requests` row in `PENDING` status.
- An `approval_evidence` row is created with canonical SHA-256 hash and redacted bundle.
- An event of type `REQUESTED` is appended to `approval_decisions`.
- A real-time WebSocket event `{ "type": "approval_update", "id": <id>, "status": "REQUESTED" }` is broadcast to all connected operators.

### Step 2: Review Evidence in Approvals UI

1. Observe the **Approvals** badge in the sidebar updating to show `1` pending approval.
2. Click the badge to open the **Governance Approvals** modal.
3. Click **Show evidence #<id>** on the pending item:
   - Under **CLAIM**, verify the command payload, agent name (`code`), and evidence SHA-256 hash.
   - Under **SOURCE**, review the planner step context and upstream excerpts.
   - Verify that any sensitive credentials or keys are cleanly redacted (`[REDACTED_API_KEY]`).

### Step 3: Approve the Request

1. In the **resolver note** field, enter:
   ```text
   Approved for directory inspection
   ```
2. Click **Approve** (or press key `A` when row is focused).
3. The request transitions to `APPROVED` atomically:
   - Status updates in the database.
   - An `APPROVED` entry is appended to the decision log with your authenticated `Principal` identity (`local-admin` or JWT subject).
   - The UI reflects the approved status and badge count decrements to 0.

### Step 4: Tool Runs Once (`CONSUMED`)

When the agent resumes or retries the tool invocation:
1. `ApprovalQueue.consume(...)` checks the approved request.
2. The tool executes exactly once.
3. The request transitions to `CONSUMED`.
4. A `CONSUMED` entry is appended to the decision log. Subsequent attempts to reuse the approval are rejected.

---

## 3. Export & Offline Independent Verification

The decision log can be exported as an encrypted or plain zip archive containing a JSONL decision stream, canonical evidence bundles, and a signed manifest.

### Exporting Decisions

Download the compliance archive:
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/governance/decisions/export.zip" \
  -o decision_log_export.zip
```

### Verifying Offline (Zero Third-Party Dependencies)

Run the standalone verification script included in the repository. It uses strictly the Python standard library with no external dependencies:

```bash
python3 scripts/verify_decision_log.py decision_log_export.zip
```

Expected output on a valid, untampered chain:
```text
[VERIFY] Inspecting decision chain for tenant 'default'...
[VERIFY] Checking 4 entries...
[VERIFY] Entry seq=1: REQUESTED (action=execute_command, actor=agent:code) - OK
[VERIFY] Entry seq=2: APPROVED  (action=execute_command, actor=user:local-admin) - OK
[VERIFY] Entry seq=3: CONSUMED  (action=execute_command, actor=agent:code) - OK
[VERIFY] Result: OK (verified 3 entries, chain intact, evidence hashes verified)
```

If any row or hash in the chain was altered, the verifier halts and reports the exact sequence number and mismatch:
```text
[FAIL] Tamper detected at sequence #2: entry_hash mismatch!
```

---

## 4. REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/governance/approvals` | `GET` | List approval summaries (`?pending_only=true`) |
| `/api/governance/approvals/{id}` | `GET` | Fetch approval detail with redacted evidence bundle |
| `/api/governance/approvals/{id}/resolve` | `POST` | Resolve request (`APPROVED` or `REJECTED`) |
| `/api/governance/approvals/count` | `GET` | Get count of pending approvals |
| `/api/governance/decisions` | `GET` | Paginated decision log history (`before_seq`, `limit`) |
| `/api/governance/decisions/verify` | `GET` | Run in-database chain verification |
| `/api/governance/decisions/export.zip` | `GET` | Export audit zip package with manifest and JSONL |
