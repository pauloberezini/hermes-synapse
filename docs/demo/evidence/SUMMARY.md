# Compliance summary

This is not legal advice. This pack does not make you compliant.

This is a sample evidence pack from a scripted Hermes Synapse demo.
It shows the format of an export you would build with a buyer in a pilot.
It is not a claim that anyone is compliant. The log carries no signatures.
Every payload, name and file here is synthetic.

## What happened (six log rows)

- Request 1, seq 1: `execute_command` **REQUESTED** by `agent:demo-reject` (login `agent`, roles `[]`, role recorded, not verified) at 2026-11-28T16:23:10.861768+00:00 UTC. Payload SHA-256 `eef2106a53cce3890254e4b39fe6279ae9d9c78875d1e048e5b5db346e8183f6`. did not run in this row.
- Request 2, seq 2: `execute_code` **REQUESTED** by `agent:demo-approve` (login `agent`, roles `[]`, role recorded, not verified) at 2026-11-28T16:23:10.961867+00:00 UTC. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. did not run in this row.
- Request 1, seq 3: `execute_command` **REJECTED** by `demo-operator` (login `otp`, roles `["admin"]`, role recorded, not verified) at 2026-11-28T16:23:10.965297+00:00 UTC. Payload SHA-256 `eef2106a53cce3890254e4b39fe6279ae9d9c78875d1e048e5b5db346e8183f6`. did not run in this row.
  Reviewer note: External customer export. Rejected for this session.
- Request 2, seq 4: `execute_code` **APPROVED** by `demo-operator` (login `otp`, roles `["admin"]`, role recorded, not verified) at 2026-11-28T16:23:10.969796+00:00 UTC. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. did not run in this row.
  Reviewer note: Read-only print. OK once.
- Request 2, seq 5: `execute_code` **CONSUMED** by `system` (login `system`, roles `[]`, role recorded, not verified) at 2026-11-28T16:23:10.972489+00:00 UTC. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. ran once.
- Request 3, seq 6: `execute_code` **REQUESTED** by `agent:demo-approve` (login `agent`, roles `[]`, role recorded, not verified) at 2026-11-28T16:23:10.976400+00:00 UTC. Payload SHA-256 `b7c8dedce8520f2888205523b29766e80fc3d54817833916072e1c75fc70cb8a`. did not run in this row.

## Verification

Clean export: `ok checked=6 head=c120db9708acd73f7c0193b36ed0cf51b3984fa8f89b8e074b76d3301cc94bda`.
Negative control (reason of seq 1 edited): `FAIL seq=1 entry_hash mismatch`, exit 1.

From this unzipped folder:

```bash
python3 verifier/verify_decision_log.py decision-log.zip
python3 verifier/verify_decision_log.py decision-log.zip --pin "$(cat pinned-head-hash.txt)"
python3 verifier/verify_decision_log.py decision-log.tampered.zip
```

## Config (one line)

Code agents off by default (`pilot_default` false); demo pins them on for the approve step and off for the kill-switch step; high-risk tools and MCP writes wait at `gate_tool`.

## Limits (five lines)

- The approve endpoint checks no role. Any logged-in session can approve; the log records subject, roles and login method. RBAC is not wired.
- The log is tamper-evident with a pinned head hash and carries no signatures.
- No SOC 2 and no named customers. Approvals cover agents in Hermes; there is no gateway in front of other clients.
- Code agents are off by default.
- This sample comes from a scripted agent with a mocked shell and sandbox.
