# Vexa Safe Autonomy Runtime

## Objective

Vexa may diagnose missing tools, request reviewed capabilities, connect approved OpenAPI services, verify the result and retain evidence. The local model never receives an unrestricted software installer or connection primitive.

## Execution Flow

1. `diagnose_capabilities` probes built-in, system and managed providers without changing state.
2. `request_capability` accepts only an ID from `CAPABILITY_REGISTRY`.
3. The capability broker resolves that ID to a source-controlled recipe and records its SHA-256 digest.
4. Control Plane creates an R3 task. No command is executed before owner approval.
5. After approval, the broker recomputes the digest, runs `npm ci` from a source-controlled lockfile in a staging directory, verifies the lockfile hash, package version, license, npm integrity and executable probe, then activates with an atomic rename.
6. Success or failure is written to the task and Evidence Ledger. A failed staging directory is removed; an existing verified installation is retained.

MCP follows the same pattern with an R4 task and two owner approvals. Autonomous requests can use only the built-in OpenAPI bridge. Arbitrary `npx`, shell interpreters and unmanaged executables are rejected.

## Security Boundaries

- No shell is used by the capability installer.
- Package lifecycle scripts, audit, funding and update checks are disabled.
- Recipes contain exact versions, license declarations and expected registry integrity.
- Installations are confined to `AUTONOMY_CAPABILITY_ROOT`.
- The model cannot supply package names, versions, registries, commands or checksums.
- MCP child processes receive a small environment allowlist, not the backend environment.
- MCP secret values are never persisted. Configuration stores references such as `${STATIC_BEARER_TOKEN}`.
- External OpenAPI endpoints require HTTPS. Private-network HTTP is allowed; link-local and metadata ranges are blocked.
- A changed recipe or MCP configuration invalidates the existing approval.
- The global Control Plane kill switch blocks new execution.

## Configuration

```dotenv
AUTONOMY_INSTALL_ENABLED=false
AUTONOMY_CAPABILITY_ROOT=/app/backend/data/capabilities
AUTONOMY_INSTALL_TIMEOUT_SECONDS=300
```

Production may enable `AUTONOMY_INSTALL_ENABLED=true` after the backend image includes the reviewed package manager. Approval remains mandatory.

## Adding A Capability

A developer must add a recipe to `backend/capability_broker.py`, expose it through `CAPABILITY_REGISTRY`, provide exact integrity metadata, define a deterministic probe and add tests for rejection, verification and rollback ownership. Runtime requests cannot create recipes.

## Current Reviewed Recipe

| Capability | Package | Version | License | Risk |
| --- | --- | --- | --- | --- |
| Browser visual validation | `@playwright/test` | `1.57.0` | Apache-2.0 | R3 |

The recipe installs the Playwright library and CLI. Browser binaries remain a separate reviewed capability and are not downloaded automatically.
