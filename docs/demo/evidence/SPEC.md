# Evidence package spec v2 (PMM, 28 Nov 2026)

Internal. Not published. Not included in `hermes-evidence-sample.zip`.
Source: PMM gap list against the Tech lead opening sample (commit ad1305c).

This checkout implements P0 (G1, G2, G3, G4, G5, G6 text + PDF, G7, G11)
and the requested P1 items (G9 MANIFEST, G12 negative-control exit code,
G14 synthetic marker). G6 PDF is the PMM-authored `SUMMARY.pdf`, copied
byte-identical. Product code is unchanged.

`origin/main` (2267e46) is the base: demo-stand plus signed-audit-log.
`CODE_AGENTS_ENABLED` default is false in `.env.example`, `docker-compose.yml`,
and `code_agents_enabled()`. The evidence snapshot reads those files. The
demo still pins true/false per step. This sample pack does not include
signed checkpoints.

## Rebuild the zip and MANIFEST

After replacing `README.md`, `SUMMARY.md`, and/or `SUMMARY.pdf`:

```bash
python3 scripts/demo_evidence.py --repack
```

or `make evidence-repack`. That rewrites only `MANIFEST.json` and
`hermes-evidence-sample.zip` from files already in this folder. It does
not touch `decision-log.zip` or `decision-log.tampered.zip`.

`make evidence` still runs `make demo` then assemble. assemble keeps
`README.md`, `SUMMARY.md`, `SUMMARY.pdf`, and the decision-log zips when
they already exist, so it cannot overwrite the PMM copies or re-export
the log. `src/` (stylesheet used to render the PDF) stays out of the zip.

## P0

- G1 Disclaimer at the top of README.md and SUMMARY.md: not legal advice; does not make you compliant.
- G2 limits/known-limits.md (11 lines) plus a short list in README.
- G3 approvals/calls.* include every decision row with seq, request id, event, actor, roles, login method, reason, UTC occurred_at, payload hash. Role is recorded, not verified.
- G4 config/config-snapshot.json with pilot_default false, commit, high_risk_tools from `_high_risk_names()`, MCP rule. Demo pins renamed so they are not read as the process default.
- G5 pinned-head-hash.txt (64 hex, one line). Pin-in-zip is a demonstration; real pin is off-host.
- G6 SUMMARY.md one-page compliance summary, plus SUMMARY.pdf (PMM file, one A4 page).
- G7 verifier/verify_decision_log.py byte copy. README commands run from the unzipped folder.
- G11 This sample pack does not include signed checkpoints. No Ed25519 / audit-log wording in the zip text files.

## P1 done now

- G9 MANIFEST.json with SHA-256 and size of every other pack file.
- G12 negative-control-expected-output.txt shows the FAIL line, exit 1, and that seq 1 reason was edited.
- G14 synthetic marker on every calls row; README and SUMMARY say every payload, name and file is synthetic.

## Closed by merging origin/main

- G4 product gap: `.env.example:47`, `docker-compose.yml` compose default, and
  `code_agents_enabled()` unset fallback are all `false` on this branch after
  the merge. `config-snapshot.json` records the values read from those files,
  not an intended override.

## Not in this pass

- G8 control mapping
- G13 runbook excerpt and screenshots
- G15–G17 polish except where a P0 item already required a wording change
