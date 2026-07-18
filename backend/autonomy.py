"""Durable planning, project memory and side-effect-free capability diagnostics."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.database import DB_PATH

logger = logging.getLogger("hermes.autonomy")

INDEX_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".sh": "shell",
    ".dockerfile": "dockerfile",
}
IGNORED_PARTS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "vendor",
}
MAX_FILES = int(os.getenv("AUTONOMY_INDEX_MAX_FILES", "4000"))
MAX_FILE_BYTES = int(os.getenv("AUTONOMY_INDEX_MAX_FILE_BYTES", "750000"))


CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "repository_search": {
        "label": "Repository search",
        "required": True,
        "providers": [
            {"id": "ripgrep", "command": "rg", "probe": ["rg", "--version"]},
            {"id": "python-fallback", "builtin": True},
        ],
        "install": None,
    },
    "version_control": {
        "label": "Version control",
        "required": True,
        "providers": [{"id": "git", "command": "git", "probe": ["git", "--version"]}],
        "install": None,
    },
    "backend_validation": {
        "label": "Backend tests",
        "required": True,
        "providers": [
            {"id": "pytest", "command": "pytest", "probe": ["pytest", "--version"]},
            {"id": "unittest", "builtin": True},
        ],
        "install": None,
    },
    "frontend_validation": {
        "label": "Frontend build and lint",
        "required": False,
        "providers": [
            {"id": "npm", "command": "npm", "probe": ["npm", "--version"]},
            {"id": "node", "command": "node", "probe": ["node", "--version"]},
        ],
        "install": None,
    },
    "visual_validation": {
        "label": "Browser visual validation",
        "required": False,
        "providers": [
            {"id": "playwright", "command": "playwright", "probe": ["playwright", "--version"]},
            {"id": "chromium", "command": "chromium", "probe": ["chromium", "--version"]},
            {"id": "google-chrome", "command": "google-chrome", "probe": ["google-chrome", "--version"]},
        ],
        "install": {
            "mode": "project",
            "ecosystem": "npm",
            "package": "@playwright/test",
            "risk_class": "R3",
            "notes": "Install only with an exact version, disabled lifecycle scripts and owner approval.",
        },
    },
    "containers": {
        "label": "Container validation",
        "required": False,
        "providers": [{"id": "docker", "command": "docker", "probe": ["docker", "--version"]}],
        "install": None,
    },
    "codebase_graph": {
        "label": "Codebase knowledge graph",
        "required": False,
        "providers": [
            {
                "id": "codebase-memory-mcp",
                "command": "codebase-memory-mcp",
                "probe": ["codebase-memory-mcp", "--version"],
            },
            {"id": "hermes-local-index", "builtin": True},
        ],
        "install": {
            "mode": "mcp",
            "source": "https://github.com/DeusData/codebase-memory-mcp",
            "risk_class": "R3",
            "notes": "Verify a signed release checksum and configure a read-only allowed root before activation.",
        },
    },
    "mcp_runtime": {
        "label": "MCP runtime",
        "required": False,
        "providers": [{"id": "hermes-mcp-client", "builtin": True}],
        "install": None,
    },
}

ROLE_CONTRACTS = {
    "scout": {
        "label": "Scout",
        "mission": "Map the relevant code and collect positive evidence without making exhaustive claims.",
        "reads": ["task", "constraints", "project index"],
        "writes": ["relevant files", "symbols", "risks", "unknowns"],
    },
    "implementer": {
        "label": "Implementer",
        "mission": "Make the smallest coherent change that satisfies the accepted plan.",
        "reads": ["scout evidence", "task contract", "repository conventions"],
        "writes": ["code changes", "change summary", "validation targets"],
    },
    "verifier": {
        "label": "Verifier",
        "mission": "Run task-directed checks and verify every claimed result against evidence.",
        "reads": ["changed files", "acceptance criteria", "available validators"],
        "writes": ["checks", "failures", "actionable correction feedback"],
    },
    "auditor": {
        "label": "Auditor",
        "mission": "Bound the inspected scope, challenge negative claims and record unresolved limitations.",
        "reads": ["plan ledger", "verification evidence", "index freshness"],
        "writes": ["final verdict", "residual risks", "memory entries"],
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _init_schema() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS project_memory_files (
                root TEXT NOT NULL,
                path TEXT NOT NULL,
                language TEXT NOT NULL,
                digest TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                symbols TEXT NOT NULL DEFAULT '[]',
                imports TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                indexed_at TEXT NOT NULL,
                PRIMARY KEY (root, path)
            );
            CREATE INDEX IF NOT EXISTS idx_project_memory_language
                ON project_memory_files (root, language);

            CREATE TABLE IF NOT EXISTS project_memory_entries (
                id TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                files TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'agent',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_project_memory_entries_root
                ON project_memory_entries (root, created_at DESC);

            CREATE TABLE IF NOT EXISTS autonomy_plans (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                root TEXT NOT NULL,
                tier TEXT NOT NULL,
                status TEXT NOT NULL,
                capabilities TEXT NOT NULL DEFAULT '[]',
                steps TEXT NOT NULL DEFAULT '[]',
                iteration INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_autonomy_plans_status
                ON autonomy_plans (status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS capability_proposals (
                id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_class TEXT NOT NULL,
                plan TEXT NOT NULL,
                control_task_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def resolve_workspace(root: Optional[str] = None) -> Path:
    configured = os.getenv("PROJECT_WORKSPACE_ROOT", "").strip()
    default = Path("/workspace") if Path("/workspace").is_dir() else Path(__file__).resolve().parents[1]
    allowed = Path(configured).expanduser().resolve() if configured else default.resolve()
    candidate = Path(root).expanduser().resolve() if root else allowed
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"Workspace must stay inside the configured root: {allowed}") from exc
    if not candidate.is_dir():
        raise ValueError(f"Workspace does not exist: {candidate}")
    return candidate


def _iter_source_files(root: Path) -> Iterable[Path]:
    count = 0
    for path in root.rglob("*"):
        if count >= MAX_FILES:
            return
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if path.name.lower() == "dockerfile":
            suffix = ".dockerfile"
        if suffix not in INDEX_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        count += 1
        yield path


def _extract_python(text: str) -> tuple[list[str], list[str]]:
    symbols: list[str] = []
    imports: list[str] = []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return symbols, imports
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return symbols[:160], sorted(set(imports))[:120]


SYMBOL_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:class|interface|type|enum|function|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s*\(\s*|require\s*\(\s*)['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
HEADING_PATTERN = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)


def _extract_structure(path: Path, text: str, language: str) -> tuple[list[str], list[str], str]:
    if language == "python":
        symbols, imports = _extract_python(text)
    elif language in {"typescript", "tsx", "javascript", "jsx"}:
        symbols = SYMBOL_PATTERN.findall(text)[:160]
        imports = sorted(set(IMPORT_PATTERN.findall(text)))[:120]
    elif language == "markdown":
        symbols = HEADING_PATTERN.findall(text)[:100]
        imports = []
    else:
        symbols = []
        imports = []
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    summary = first_line[:240] if first_line else f"{language} file"
    if path.name.lower().startswith("test") or ".test." in path.name or ".spec." in path.name:
        summary = f"Test: {summary}"
    return symbols, imports, summary


def index_project(root: Optional[str] = None) -> dict[str, Any]:
    """Incrementally index safe structural metadata; source text is not persisted."""
    _init_schema()
    workspace = resolve_workspace(root)
    root_key = str(workspace)
    seen: set[str] = set()
    indexed = 0
    unchanged = 0
    skipped = 0
    with _connect() as connection:
        existing = {
            row["path"]: row["digest"]
            for row in connection.execute(
                "SELECT path, digest FROM project_memory_files WHERE root = ?",
                (root_key,),
            )
        }
        for path in _iter_source_files(workspace):
            relative = path.relative_to(workspace).as_posix()
            seen.add(relative)
            try:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if existing.get(relative) == digest:
                    unchanged += 1
                    continue
                text = raw.decode("utf-8", errors="replace")
                suffix = path.suffix.lower() if path.name.lower() != "dockerfile" else ".dockerfile"
                language = INDEX_EXTENSIONS[suffix]
                symbols, imports, summary = _extract_structure(path, text, language)
                connection.execute(
                    """
                    INSERT INTO project_memory_files
                        (root, path, language, digest, size_bytes, symbols, imports, summary, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(root, path) DO UPDATE SET
                        language=excluded.language,
                        digest=excluded.digest,
                        size_bytes=excluded.size_bytes,
                        symbols=excluded.symbols,
                        imports=excluded.imports,
                        summary=excluded.summary,
                        indexed_at=excluded.indexed_at
                    """,
                    (
                        root_key,
                        relative,
                        language,
                        digest,
                        len(raw),
                        json.dumps(symbols, ensure_ascii=False),
                        json.dumps(imports, ensure_ascii=False),
                        summary,
                        _now(),
                    ),
                )
                indexed += 1
            except (OSError, UnicodeError) as exc:
                skipped += 1
                logger.debug("Skipped project file %s: %s", path, exc)
        removed = sorted(set(existing) - seen)
        if removed:
            connection.executemany(
                "DELETE FROM project_memory_files WHERE root = ? AND path = ?",
                [(root_key, path) for path in removed],
            )
    return {
        "root": root_key,
        "indexed": indexed,
        "unchanged": unchanged,
        "removed": len(removed),
        "skipped": skipped,
        "files": len(seen),
        "fresh_at": _now(),
    }


def search_project_memory(query: str, root: Optional[str] = None, limit: int = 8) -> list[dict[str, Any]]:
    _init_schema()
    workspace = resolve_workspace(root)
    terms = [term.lower() for term in re.findall(r"[\w./-]{2,}", query, flags=re.UNICODE)[:16]]
    if not terms:
        return []
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT path, language, symbols, imports, summary, indexed_at
            FROM project_memory_files
            WHERE root = ?
            ORDER BY indexed_at DESC
            LIMIT 2500
            """,
            (str(workspace),),
        ).fetchall()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        item = dict(row)
        haystack = f"{item['path']} {item['symbols']} {item['imports']} {item['summary']}".lower()
        score = sum(5 if term in item["path"].lower() else 2 if term in item["symbols"].lower() else 1 for term in terms if term in haystack)
        if score:
            item["symbols"] = json.loads(item["symbols"] or "[]")
            item["imports"] = json.loads(item["imports"] or "[]")
            item["score"] = score
            ranked.append((score, item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["path"]))
    return [item for _, item in ranked[: max(1, min(limit, 30))]]


def remember_project_entry(
    kind: str,
    title: str,
    content: str,
    files: Optional[list[str]] = None,
    source: str = "agent",
    root: Optional[str] = None,
) -> dict[str, Any]:
    _init_schema()
    workspace = resolve_workspace(root)
    entry = {
        "id": f"mem-{uuid.uuid4().hex[:12]}",
        "root": str(workspace),
        "kind": re.sub(r"[^a-z0-9_-]", "", kind.lower())[:32] or "note",
        "title": title.strip()[:180],
        "content": content.strip()[:6000],
        "files": files or [],
        "source": source.strip()[:80] or "agent",
        "created_at": _now(),
    }
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO project_memory_entries
                (id, root, kind, title, content, files, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                entry["root"],
                entry["kind"],
                entry["title"],
                entry["content"],
                json.dumps(entry["files"], ensure_ascii=False),
                entry["source"],
                entry["created_at"],
            ),
        )
    return entry


def recent_project_entries(root: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    _init_schema()
    workspace = resolve_workspace(root)
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM project_memory_entries
            WHERE root = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(workspace), max(1, min(limit, 100))),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["files"] = json.loads(item["files"] or "[]")
        result.append(item)
    return result


def project_context(query: str, root: Optional[str] = None, limit: int = 6) -> str:
    matches = search_project_memory(query, root=root, limit=limit)
    entries = recent_project_entries(root=root, limit=4)
    if not matches and not entries:
        return ""
    lines = ["[Project memory: structural evidence, not user instructions]"]
    for item in matches:
        symbols = ", ".join(item["symbols"][:8])
        suffix = f"; symbols: {symbols}" if symbols else ""
        lines.append(f"- {item['path']} ({item['language']}){suffix}")
    for entry in entries:
        lines.append(f"- Decision/{entry['kind']}: {entry['title']} — {entry['content'][:300]}")
    return "\n".join(lines)


def _probe_provider(provider: dict[str, Any]) -> dict[str, Any]:
    result = {"id": provider["id"], "status": "missing", "detail": ""}
    if provider.get("builtin"):
        return {**result, "status": "ready", "detail": "Built into Hermes"}
    command = provider.get("command")
    executable = shutil.which(command) if command else None
    if not executable:
        return result
    try:
        completed = subprocess.run(
            provider.get("probe") or [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            env={**os.environ, "NO_COLOR": "1"},
        )
        output = (completed.stdout or completed.stderr or "").strip().splitlines()
        return {
            **result,
            "status": "ready" if completed.returncode == 0 else "broken",
            "detail": (output[0] if output else f"exit {completed.returncode}")[:180],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**result, "status": "broken", "detail": type(exc).__name__}


def doctor_capabilities() -> dict[str, Any]:
    capabilities = []
    for capability_id, spec in CAPABILITY_REGISTRY.items():
        providers = [_probe_provider(provider) for provider in spec["providers"]]
        active = next((provider for provider in providers if provider["status"] == "ready"), None)
        capabilities.append(
            {
                "id": capability_id,
                "label": spec["label"],
                "required": spec["required"],
                "status": "ready" if active else "missing",
                "active_provider": active["id"] if active else None,
                "providers": providers,
                "install_available": bool(spec.get("install")),
            }
        )
    ready = sum(item["status"] == "ready" for item in capabilities)
    return {
        "status": "ready" if all(not item["required"] or item["status"] == "ready" for item in capabilities) else "degraded",
        "ready": ready,
        "total": len(capabilities),
        "capabilities": capabilities,
        "checked_at": _now(),
    }


def _infer_capabilities(goal: str) -> list[str]:
    text = goal.lower()
    result = ["repository_search", "version_control"]
    if re.search(r"frontend|react|ui|интерфейс|визуал|css|браузер", text):
        result.extend(["frontend_validation", "visual_validation"])
    if re.search(r"backend|api|python|бэк|бэкенд|сервер", text):
        result.append("backend_validation")
    if re.search(r"docker|deploy|контейнер|деплой", text):
        result.append("containers")
    if re.search(r"memory|codebase|graph|памят|кодовой баз", text):
        result.append("codebase_graph")
    return list(dict.fromkeys(result))


def _plan_tier(goal: str) -> str:
    signals = len(re.findall(r"\b(?:and|also|then|после|также|и)\b", goal.lower()))
    if len(goal) > 900 or signals >= 6:
        return "auditor"
    if len(goal) > 260 or signals >= 2:
        return "verify"
    return "scout"


def build_plan(goal: str, root: Optional[str] = None) -> dict[str, Any]:
    _init_schema()
    workspace = resolve_workspace(root)
    tier = _plan_tier(goal)
    capabilities = _infer_capabilities(goal)
    steps = [
        {
            "id": "discover",
            "agent": "scout",
            "title": "Map scope and constraints",
            "status": "pending",
            "input": ["goal", "project memory", "repository state"],
            "expected_output": ["relevant files", "existing conventions", "risk list"],
            "acceptance": ["Every proposed file is backed by source evidence", "Unknowns are explicit"],
            "attempts": 0,
        },
        {
            "id": "implement",
            "agent": "implementer",
            "title": "Implement the bounded change",
            "status": "pending",
            "input": ["accepted discovery", "task constraints"],
            "expected_output": ["code changes", "changed-file ledger"],
            "acceptance": ["Change matches repository conventions", "No unrelated files are modified"],
            "attempts": 0,
        },
        {
            "id": "verify",
            "agent": "verifier",
            "title": "Validate and correct",
            "status": "pending",
            "input": ["changed files", "acceptance criteria", "available capabilities"],
            "expected_output": ["test evidence", "lint/build evidence", "correction feedback"],
            "acceptance": ["Required checks pass", "Failures are corrected or explicitly blocked"],
            "max_attempts": 3,
            "attempts": 0,
        },
    ]
    if tier == "auditor":
        steps.append(
            {
                "id": "audit",
                "agent": "auditor",
                "title": "Audit scope and retain lessons",
                "status": "pending",
                "input": ["complete plan ledger", "verification evidence"],
                "expected_output": ["verdict", "residual risks", "memory entries"],
                "acceptance": ["Index freshness is stated", "Negative claims have bounded coverage"],
                "attempts": 0,
            }
        )
    plan = {
        "id": f"plan-{uuid.uuid4().hex[:12]}",
        "goal": goal.strip()[:8000],
        "root": str(workspace),
        "tier": tier,
        "status": "planned",
        "capabilities": capabilities,
        "steps": steps,
        "iteration": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "role_contracts": {key: ROLE_CONTRACTS[key] for key in {step["agent"] for step in steps}},
    }
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO autonomy_plans
                (id, goal, root, tier, status, capabilities, steps, iteration, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan["id"],
                plan["goal"],
                plan["root"],
                plan["tier"],
                plan["status"],
                json.dumps(capabilities, ensure_ascii=False),
                json.dumps(steps, ensure_ascii=False),
                plan["iteration"],
                plan["created_at"],
                plan["updated_at"],
            ),
        )
    return plan


def save_runtime_plan(goal: str, steps: list[dict[str, Any]], root: Optional[str] = None) -> dict[str, Any]:
    plan = build_plan(goal, root=root)
    normalized = []
    for index, step in enumerate(steps):
        normalized.append(
            {
                "id": step.get("id") or f"step-{index + 1}",
                "agent": step.get("agent", "unknown"),
                "title": step.get("title") or step.get("instructions", "")[:120],
                "instructions": step.get("instructions", ""),
                "expected_output": step.get("expected_output", []),
                "acceptance": step.get("acceptance", []),
                "status": "pending",
                "attempts": 0,
            }
        )
    return update_plan(plan["id"], steps=normalized, status="running")


def update_plan(
    plan_id: str,
    *,
    status: Optional[str] = None,
    steps: Optional[list[dict[str, Any]]] = None,
    iteration: Optional[int] = None,
) -> dict[str, Any]:
    _init_schema()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM autonomy_plans WHERE id = ?", (plan_id,)).fetchone()
        if not row:
            raise KeyError(plan_id)
        item = dict(row)
        next_status = status or item["status"]
        next_steps = steps if steps is not None else json.loads(item["steps"] or "[]")
        next_iteration = int(iteration if iteration is not None else item["iteration"])
        updated_at = _now()
        connection.execute(
            """
            UPDATE autonomy_plans
            SET status = ?, steps = ?, iteration = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_status, json.dumps(next_steps, ensure_ascii=False), next_iteration, updated_at, plan_id),
        )
    return get_plan(plan_id)


def update_runtime_step(
    plan_id: str,
    step_index: int,
    *,
    status: str,
    result_summary: str = "",
    feedback: str = "",
) -> dict[str, Any]:
    plan = get_plan(plan_id)
    if not plan:
        raise KeyError(plan_id)
    steps = plan["steps"]
    if step_index < 0 or step_index >= len(steps):
        raise IndexError(step_index)
    step = steps[step_index]
    step["status"] = status
    step["attempts"] = int(step.get("attempts", 0)) + (1 if status in {"running", "retrying"} else 0)
    if result_summary:
        step["result_summary"] = result_summary[:1200]
    if feedback:
        step["feedback"] = feedback[:1200]
    return update_plan(plan_id, steps=steps, iteration=plan["iteration"] + (1 if status == "retrying" else 0))


def get_plan(plan_id: str) -> Optional[dict[str, Any]]:
    _init_schema()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM autonomy_plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["capabilities"] = json.loads(item["capabilities"] or "[]")
    item["steps"] = json.loads(item["steps"] or "[]")
    return item


def list_plans(limit: int = 30) -> list[dict[str, Any]]:
    _init_schema()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM autonomy_plans ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["capabilities"] = json.loads(item["capabilities"] or "[]")
        item["steps"] = json.loads(item["steps"] or "[]")
        result.append(item)
    return result


def propose_capability(capability_id: str) -> dict[str, Any]:
    _init_schema()
    spec = CAPABILITY_REGISTRY.get(capability_id)
    if not spec:
        raise KeyError(capability_id)
    health = next(item for item in doctor_capabilities()["capabilities"] if item["id"] == capability_id)
    if health["status"] == "ready":
        return {"status": "already_available", "capability": health}
    install = spec.get("install")
    if not install:
        return {
            "status": "manual",
            "capability": health,
            "reason": "No reviewed automatic installation path is registered.",
        }
    proposal_id = f"cap-{uuid.uuid4().hex[:12]}"
    plan = {
        "capability_id": capability_id,
        "label": spec["label"],
        "preflight": [
            "Pin an exact version or signed release",
            "Verify license, checksum and platform compatibility",
            "Use project/user scope; never request root",
            "Disable package lifecycle scripts during inspection",
            "Run doctor and regression checks after activation",
        ],
        "install": install,
        "automatic_execution": False,
    }
    from backend.control_plane import create_review_task

    control_task = create_review_task(
        goal=f"Review capability installation: {spec['label']}",
        arguments=plan,
        risk_class=install.get("risk_class", "R3"),
        acceptance=plan["preflight"],
        rollback="Remove only exact-owned files/configuration, then re-run capability doctor.",
        requester="autonomy",
    )
    now = _now()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO capability_proposals
                (id, capability_id, status, risk_class, plan, control_task_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                capability_id,
                "awaiting_approval",
                install.get("risk_class", "R3"),
                json.dumps(plan, ensure_ascii=False),
                control_task["id"],
                now,
                now,
            ),
        )
    return {
        "id": proposal_id,
        "status": "awaiting_approval",
        "plan": plan,
        "control_task": control_task,
    }


def autonomy_summary(root: Optional[str] = None) -> dict[str, Any]:
    _init_schema()
    workspace = resolve_workspace(root)
    with _connect() as connection:
        file_row = connection.execute(
            """
            SELECT COUNT(*) AS files, COALESCE(SUM(size_bytes), 0) AS bytes, MAX(indexed_at) AS fresh_at
            FROM project_memory_files
            WHERE root = ?
            """,
            (str(workspace),),
        ).fetchone()
        memory_count = connection.execute(
            "SELECT COUNT(*) FROM project_memory_entries WHERE root = ?",
            (str(workspace),),
        ).fetchone()[0]
        proposal_rows = connection.execute(
            """
            SELECT id, capability_id, status, risk_class, control_task_id, created_at
            FROM capability_proposals
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "workspace": str(workspace),
        "capabilities": doctor_capabilities(),
        "memory": {
            "files": file_row["files"],
            "bytes": file_row["bytes"],
            "fresh_at": file_row["fresh_at"],
            "entries": memory_count,
        },
        "plans": list_plans(limit=20),
        "proposals": [dict(row) for row in proposal_rows],
        "role_contracts": ROLE_CONTRACTS,
    }


_init_schema()
