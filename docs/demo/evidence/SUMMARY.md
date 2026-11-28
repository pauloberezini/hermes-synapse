# Compliance summary

This is not legal advice. This pack does not make you compliant.

This is a sample evidence pack from a scripted Hermes Synapse demo. It shows the format of an export you would build with a buyer in a pilot. Nothing here is a claim that anyone is compliant. This sample pack does not include signed checkpoints; the zip log carries no signatures. Every payload, every name and every file here is synthetic (`partner.example`, `customers.csv`, `demo-operator`).

## What happened (six log rows)

Times are UTC. The role on each row is recorded and not verified.

- Request 1, seq 1. Tool `execute_command`. Event REQUESTED. Actor `agent:demo-reject`, login `agent`, roles `[]`. Time 2026-11-28T16:25:22.858171+00:00. Payload SHA-256 `eef2106a53cce3890254e4b39fe6279ae9d9c78875d1e048e5b5db346e8183f6`. This row did not run.
- Request 2, seq 2. Tool `execute_code`. Event REQUESTED. Actor `agent:demo-approve`, login `agent`, roles `[]`. Time 2026-11-28T16:25:22.957954+00:00. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. This row did not run.
- Request 1, seq 3. Tool `execute_command`. Event REJECTED. Actor `demo-operator`, login `otp`, roles `["admin"]`. Time 2026-11-28T16:25:22.960274+00:00. Payload SHA-256 `eef2106a53cce3890254e4b39fe6279ae9d9c78875d1e048e5b5db346e8183f6`. This row did not run. Reviewer note, quoted from the log: "External customer export. Rejected for this session."
- Request 2, seq 4. Tool `execute_code`. Event APPROVED. Actor `demo-operator`, login `otp`, roles `["admin"]`. Time 2026-11-28T16:25:22.963652+00:00. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. This row did not run. Reviewer note, quoted from the log: "Read-only print. OK once."
- Request 2, seq 5. Tool `execute_code`. Event CONSUMED. Actor `system`, login `system`, roles `[]`. Time 2026-11-28T16:25:22.967033+00:00. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. This row ran once.
- Request 3, seq 6. Tool `execute_code`. Event REQUESTED. Actor `agent:demo-approve`, login `agent`, roles `[]`. Time 2026-11-28T16:25:22.971922+00:00. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. This row did not run.

## Verification

Clean export: `ok checked=6 head=497dffc099f1479e5ae0f39c9e02e6e30aa7ee67c9b7a6814260311cb8d21e8e`.

Negative control (reason of seq 1 edited): `FAIL seq=1 entry_hash mismatch`, exit 1.

From this unzipped folder:

```bash
python3 verifier/verify_decision_log.py decision-log.zip
python3 verifier/verify_decision_log.py decision-log.zip --pin "$(cat pinned-head-hash.txt)"
python3 verifier/verify_decision_log.py decision-log.tampered.zip
```

## Config (one line)

Code agents off by default (`pilot_default` false). The demo pins them on for the approve step and off for the kill-switch step. High-risk tools and MCP writes wait at `gate_tool`.

## Limits (five lines)

- The approve endpoint checks no role. Any logged-in session can approve. The log records the subject and the roles, plus the login method. RBAC is not wired.
- The zip log is tamper-evident with a pinned head hash. This sample pack does not include signed checkpoints; the zip log carries no signatures.
- No SOC 2 and no named customers. Approvals cover agents in Hermes. There is no gateway in front of other clients.
- Code agents are off by default.
- This sample comes from a scripted agent with a mocked shell and sandbox.
