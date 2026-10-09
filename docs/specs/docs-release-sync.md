# Docs & GitHub Pages release sync — spec

Goal: every public release (`vX.Y.Z` pushed by `scripts/export_oss.sh`) ships with a matching CHANGELOG entry and docs that describe the current core. GitHub Pages is rebuilt automatically; the work is keeping the *content* current.

## Context

- Pages source: `main`, build type `workflow` → `.github/workflows/deploy-docs.yml` (VitePress, `docs/`). It runs on every push to `main`, so no manual deploy step exists or is needed.
- Audit after `v1.4.1` (2026-10-09): deploy green, site returns 200, `docs/` has no stale `Serper` / `Sir` / `1.4.0` references.
- Gaps found:
  1. `CHANGELOG.md` stops at `v1.4.0`; no `v1.4.1` entry.
  2. `docs/` never mentions SearXNG, although README and `.env.example` now use it as the search backend.

## Scope

In: `CHANGELOG.md`, `docs/guide/getting-started.md`, release checklist. Out: VitePress theme/config, new guide pages, private plugin docs (they stay under `docs/specs/bcm-*`, excluded from export).

## Tasks

- [x] **1. CHANGELOG `v1.4.1`** — add the entry below above `v1.4.0`.
- [x] **2. SearXNG in getting-started** — short section: set `SEARXNG_URL`, link to the SearXNG project, note that no paid search API key is required.
- [x] **3. Release checklist** — add the checklist below to `CONTRIBUTING.md` (maintainer section).
- [x] **4. Guard test** — extend `backend/tests/test_public_hygiene.py`: fail if the latest `vX.Y.Z` header in `CHANGELOG.md` is missing for the version in `frontend/package.json`.
- [ ] **5. Publish & verify** — private PR → `TAG=v1.4.2 scripts/export_oss.sh --push` → confirm `Deploy VitePress Documentation` is green and the live page shows the new section.

## CHANGELOG draft

```markdown
## 🚀 [v1.4.1] - 2026-10-09

### 🛡️ Resilience
- **Non-blocking tool execution:** synchronous tools run in a worker thread (`asyncio.to_thread`), so long tools no longer starve the event loop or the health endpoints.
- **Telegram polling:** exponential backoff (15s → 300s) on polling conflicts instead of a fixed cooldown.
- **Idempotent client shutdown:** repeated or concurrent `close()` calls no longer raise "cannot reuse already awaited coroutine".

### 🧹 Hygiene & Docs
- Search docs and `.env.example` describe self-hosted SearXNG (`SEARXNG_URL`).
- Removed stray root artifacts; added `test_public_hygiene.py` to keep the public surface clean.
- `export_oss.sh`: fixed `set -e` abort when the leak gate and coupling check find nothing.

### 🧪 Tests
- New core tests: DAG cycle detection, governance wiring, OpenRouter/Ollama model selection.
```

## Release checklist (per `vX.Y.Z`)

1. `CHANGELOG.md` has a header for the new version.
2. New env vars appear in `.env.example` and `docs/guide/getting-started.md`.
3. `grep -rniE "serper|\bSir\b" docs README.md` returns nothing.
4. `bash scripts/export_oss.sh` dry run: no leaks, `Coupling smell: 0`.
5. After `--push`: `gh run list --repo pauloberezini/hermes-synapse --limit 3` shows Release, Hermes CI and Deploy Docs green.
6. Open the live Pages URL and check the changed section.

## Acceptance

- `CHANGELOG.md` top entry equals the published tag.
- Live site mentions SearXNG setup.
- Hygiene test fails when the changelog lags behind the package version.
- Export dry run stays clean (no private tokens in the new text).

## Log

- 2026-10-09 — Spec written after the `v1.4.1` audit. No tasks started.
- 2026-10-09 — Tasks 1–4 completed: added v1.4.1 to CHANGELOG.md, added SearXNG to getting-started.md, added Release checklist to CONTRIBUTING.md, added test_changelog_matches_package_version to test_public_hygiene.py, and bumped package versions to 1.4.1.

