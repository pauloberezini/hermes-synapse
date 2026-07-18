# Hermes Autonomy Runtime

Hermes uses a bounded autonomy loop inspired by the specialist contracts in
`agency-agents`, the local structural index in `codebase-memory-mcp`, and the
capability doctor/provider fallbacks in `agent-reach`.

## Execution loop

1. The planner emits stable step IDs, expected outputs, and acceptance criteria.
2. A specialist agent executes each step with the minimum available tool set.
3. The verifier rejects exceptions, empty output, and failed structured results.
4. A failed step receives concrete feedback and may retry up to three times.
5. The plan ledger and a compact outcome are retained in project memory.

## Project memory

The repository is mounted read-only at `/workspace`. The local SQLite index
stores file paths, hashes, languages, symbols, imports, and short structural
summaries. It does not persist source contents. Indexing is incremental and
confined to `PROJECT_WORKSPACE_ROOT`.

## Capability safety

The capability doctor uses side-effect-free probes and ordered fallbacks. An
unavailable reviewed capability may create an R3/R4 proposal in Control Plane,
but no package or MCP server is installed automatically. Approval is a review
gate, not an executable command. Installation requires a separate owner action
after version, license, checksum, platform, scope, and rollback checks.

## API

- `GET /api/autonomy/summary`
- `GET /api/autonomy/capabilities`
- `POST /api/autonomy/capabilities/{id}/propose`
- `POST /api/autonomy/index`
- `GET /api/autonomy/memory/search?q=...`
- `POST /api/autonomy/memory`
- `GET|POST /api/autonomy/plans`
