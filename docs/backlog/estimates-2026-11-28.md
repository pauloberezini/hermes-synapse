---
title: Backlog estimates 2026-11-28
description: Hours-only estimates for showing the approver and CONSUMED in the Approvals UI, and for a live MCP tool inventory on the evidence package. Not scheduled. Not implemented.
---

# Backlog estimates (2026-11-28)

Estimate only. No implementation in this change. Hours are engineering effort against the code on `cursor/gateway-mvp-2164` as it stands today, not calendar. That branch is unmerged; `main` is about to receive unrelated `demo-stand` and `signed-audit-log` merges.

| Item | Hours |
|---|---|
| (a) Approver + CONSUMED in the Approvals UI | **4** |
| (b) Live MCP tool inventory in the evidence package | **12** |

---

## (a) Show the approver and CONSUMED in the Approvals UI — 4 hours

### Scope

The queue already stores `APPROVED` / `REJECTED` / `CONSUMED`. The All tab already lists non-pending rows. `CONSUMED` already paints slate (not error red) in `ApprovalsModal.test.tsx`. `GET /api/governance/approvals/{id}` already attaches `decisions` from `decision_log.history`.

What is missing is **display**:

- After Approve, the operator stays on the **Pending** tab, so the row vanishes. CONSUMED only appears if they know to open **All**.
- The CLAIM pane never renders `actor_subject` from the `APPROVED` (or `REJECTED`) decision-log event. The human who clicked Approve is on the chain (`local-admin` for OTP) and not on the card.
- `STATUS_CHIP` has no explicit `CONSUMED` entry (it falls through to slate). Fine visually; easy to miss next to APPROVED.

In scope: surface `actor_subject` (and `auth_method`) on the expanded card from the existing `decisions[]`; label CONSUMED in the chip map; after a resolve (and on `approval_update` with `CONSUMED`), keep the row visible (switch to All or pin the last resolved id). No new approval states. No RBAC change. No “who consumed” fiction — `CONSUMED` is written by `system`.

Out of scope: changing consume-once semantics; adding a `resolved_by` column (join the log instead); a new page.

### Files touched

| File | Why |
|---|---|
| `frontend/src/components/ApprovalsModal.tsx` | Chip map; “Approved by …” / “Rejected by …” from `detail.decisions`; stay on All after resolve |
| `frontend/src/components/ApprovalsModal.test.tsx` | Approver text; CONSUMED visible after consume event |
| `frontend/src/types.ts` | Only if the list endpoint grows a denormalised `resolved_by` |
| `backend/governance.py` | Optional: include latest APPROVED/REJECTED actor on `get_all()` so the list chip does not need a detail fetch |
| `backend/tests/test_evidence_api.py` or a small approvals UI API test | Actor present on detail; CONSUMED status round-trip |

Default path is **frontend-only (~3 h)** using `decisions[]`. Budget **+1 h** if list payloads should show the name without expanding.

### Risks

- Approver is `local-admin` on OTP. Do not invent a display name from the session cookie.
- `resolve()` without `principal` already falls back to `Principal("system", ("admin",))`. Showing that string is correct; do not hide it.
- CONSUMED overwrites `approval_requests.status`. The approver lives only on the `APPROVED` log row. Do not copy it onto the request row unless you add a column (schema + Postgres twin).
- WebSocket `approval_update` already fires on consume. If the modal is on Pending, the list refetch drops the row — that is the UX bug, not a missing event.

### Tests

- Modal: expanded APPROVED row shows `actor_subject` from `decisions`.
- Modal: CONSUMED chip is slate and the label `CONSUMED` is visible on All.
- After resolve, Pending count is 0 and All still contains the id.
- API (if list is extended): `get_all` includes `resolved_by` equal to the APPROVED event actor.
- Existing consume-once and decision-log tests stay green.

### DoD

- [ ] Expanded card shows who approved or rejected (from the chain, not a guess).
- [ ] All tab shows **CONSUMED** after a successful retry, without hunting.
- [ ] Pending tab does not imply the request vanished.
- [ ] No new RBAC roles; no `decision_log` event type changes.
- [ ] Frontend tests + `pytest` green.

---

## (b) Live MCP tool inventory for the evidence package — 12 hours

### Scope

When the stdio proxy (and later any gateway connect) runs `tools/list`, persist a **connect-time snapshot**: server name, each tool name, MCP annotations (`readOnlyHint`, `destructiveHint`, …), and the Hermes risk classification (`needs_approval` true/false and why: `HIGH_RISK_TOOLS` / builtin / annotation default).

That snapshot must be in the **evidence package** (`export.zip`) so an offline reader can see reach-at-connect, not only tools that later hit `gate_tool`.

Recommended shape (smallest that still verifies):

1. Companion table `mcp_inventory_snapshots` (id, server, connected_at, canonical_json, sha256). Not the hash chain. Mutable reconnects insert a **new** row; never UPDATE.
2. One `decision_log` event `INVENTORY` whose `payload_hash` is that sha256, `action_name` like `mcp_inventory:<server>`, `request_id=0`, `bundle_hash` null.
3. `export.zip` grows `inventory/<id>.json` (the canonical snapshot). `verify_decision_log.py` checks: for each `INVENTORY` row, the file exists and `sha256(canonical_json(file)) == payload_hash`.

Out of scope: Gateway tab UI, reach-vs-touched matrix, client tokens, HTTP `/mcp` (milestone C / Phase 4 item 10). Those stay in `docs/specs/roadmap/phase-4-ecosystem.md`. This item is the audit pin at connect, not the product inventory.

### Hash-chain implications

| Choice | Effect |
|---|---|
| Full tools/list dumped into `reason` or `payload` of many chain rows | Chain bloat; PII in descriptions; `reason` is stored plaintext; verifier still does not rehash payload bodies (only `payload_hash`). **Do not.** |
| One `INVENTORY` event per tool | `request_id=0` flood, noisy `history()`, no extra proof vs one snapshot hash. **Do not.** |
| Snapshot table only, nothing on the chain | Export can attach files, but a truncated zip still “verifies” today’s chain. Inventory is not attested. Weak. |
| **Snapshot table + one `INVENTORY` event + zip file + verifier rule** | Chain attests the digest. Reconnect = new seq. Old zips without `INVENTORY` still pass (new rule is event-conditional). **Do this.** |

`payload_hash` is already a hashed body field. Putting the snapshot digest there does not require a new `_HASH_FIELDS` column. Changing `_HASH_FIELDS` would invalidate every existing chain — forbidden.

`HOOK` events already use `request_id=0` for fail-closed-before-queue. `INVENTORY` can share 0. `history(0)` becomes a mixed stream; the export/verifier walk is by `seq`, so that is acceptable. Do not overload `HOOK`.

Reconnect: if `tools/list` is identical (same canonical JSON), skip the extra event (or write it anyway — say so in the DoD; skip is better). If annotations change, new snapshot + new `INVENTORY` event. Never UPDATE `approval_decisions`.

PII: tool descriptions can hold URLs and names. Canonical JSON for the hash should be `{name, annotations, classified}` only, not raw `description`, unless the DoD explicitly wants descriptions in the zip (then PIIGuard the text).

### Files touched

| File | Why |
|---|---|
| `backend/database.py` | `mcp_inventory_snapshots` SQLite + Postgres twin |
| `backend/gateway/stdio_proxy.py` | On `tools/list`, classify + persist + maybe `INVENTORY` append |
| `backend/gateway/classify.py` | Reuse; maybe a small `classify_reason(name, annotations)` helper |
| `backend/decision_log.py` | `export_zip` includes `inventory/*.json` |
| `scripts/verify_decision_log.py` | Conditional check for `event == "INVENTORY"` |
| `backend/tests/test_gateway_stdio_proxy.py` | Snapshot on list; skip if unchanged |
| `backend/tests/test_decision_log_api.py` | Zip contains inventory file; pin still works |
| New `backend/tests/test_gateway_inventory_snapshot.py` | Hash stability, no token/PII in snapshot, verifier fail if file missing |
| `docs/gateway/README.md` | One paragraph: what `INVENTORY` means (on the branch that holds gateway docs) |

`backend/mcp_client.py` connect path is optional in this slice if the DoD is “stdio proxy only”. Adding it is **+2 h** (same helper, second caller). Not in the 12 h unless you want Hermes-as-client covered too.

### Risks

- Verifier change is a compatibility contract. The new rule must be **opt-in by event type** so existing `decisions.zip` files keep exiting 0.
- `tools/list` on every MCP initialize. Do not append `INVENTORY` on every `tools/list` from a chatty client; key by `(tenant, server, sha256)` and skip duplicates.
- Canonical JSON must match between writer and verifier (`sort_keys`, same annotation subset). A float/bool drift fails the pin.
- Postgres + SQLite twins. Miss the Postgres DDL and pilots break.
- Classification at connect can disagree with classify-at-call if plugin extras load later. Snapshot should call the same `needs_approval(..., known_mcp=True)` the proxy uses on `tools/call`.
- Zip size: dozens of tools is fine; huge servers need a cap or omit descriptions.

### Tests

- Fake upstream `tools/list` → one snapshot row + one `INVENTORY` event; second identical list → no second event.
- Annotation change → second snapshot + second event; both sha256s in the zip.
- `verify_decision_log.py` exit 0 on a good zip; exit 1 if `inventory/<id>.json` is deleted or mutated.
- Pre-inventory fixture zip (no `INVENTORY` rows) still verifies.
- Snapshot JSON has no `HERMES_GATEWAY_TOKEN` and no `Authorization` header.

### DoD

- [ ] After a proxy `tools/list`, export.zip contains `inventory/<id>.json` and an `INVENTORY` chain event whose `payload_hash` matches.
- [ ] Offline `verify_decision_log.py` checks that digest. `--pin` still works.
- [ ] Old zips without inventory still verify.
- [ ] Snapshot records server, tool names, annotations, and risk classification used at connect.
- [ ] Reconnect with the same list does not append a duplicate event.
- [ ] No RBAC change. No `_HASH_FIELDS` change.
- [ ] `pytest` green.

---

## What these hours are not

- Not milestone C (Streamable HTTP `/mcp`).
- Not the Phase 4 Gateway tab / reach-vs-touched matrix (that is a separate UI slice on top of (b)).
- Not calendar. (a) is one sitting. (b) is a small schema + exporter/verifier change; most of the 12 h is getting the canonical hash and verifier contract right, not drawing a table.
