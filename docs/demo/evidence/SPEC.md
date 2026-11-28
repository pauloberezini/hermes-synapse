# Evidence package spec v2 (PMM, 28 Nov 2026)

Internal. Not published. Not included in `hermes-evidence-sample.zip`.
Source: PMM gap list against the Tech lead opening sample (commit ad1305c).

This checkout implements P0 (G1, G2, G3, G4, G5, G6 text, G7, G11) and the
requested P1 items (G9 MANIFEST, G12 negative-control exit code, G14 synthetic
marker). It does not implement G8 directive mapping or any PDF.

## P0

- G1 Disclaimer at the top of README.md and SUMMARY.md: not legal advice; does not make you compliant.
- G2 limits/known-limits.md (11 lines) plus a short list in README.
- G3 approvals/calls.* include every decision row with seq, request id, event, actor, roles, login method, reason, UTC occurred_at, payload hash. Role is recorded, not verified.
- G4 config/config-snapshot.json with pilot_default false, commit, high_risk_tools from `_high_risk_names()`, MCP rule. Demo pins renamed so they are not read as the process default.
- G5 pinned-head-hash.txt (64 hex, one line). Pin-in-zip is a demonstration; real pin is off-host.
- G6 SUMMARY.md one-page compliance summary. No PDF (explicitly out of scope for this pass).
- G7 verifier/verify_decision_log.py byte copy. README commands run from the unzipped folder.
- G11 The log carries no signatures. No Ed25519 / audit-log wording in the zip text files.

## P1 done now

- G9 MANIFEST.json with SHA-256 and size of every other pack file.
- G12 negative-control-expected-output.txt shows the FAIL line, exit 1, and that seq 1 reason was edited.
- G14 synthetic marker on every calls row; README and SUMMARY say every payload, name and file is synthetic.

## Not in this pass

- G8 control mapping
- G6/G18 PDF
- G13 runbook excerpt and screenshots
- G15–G17 polish except where a P0 item already required a wording change
