"""Approved, isolated capability installation for the autonomy runtime."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECIPES: dict[str, dict[str, Any]] = {
    "visual_validation": {
        "manager": "npm",
        "package": "@playwright/test",
        "version": "1.57.0",
        "license": "Apache-2.0",
        "integrity": "sha512-6TyEnHgd6SArQO8UO2OMTxshln3QMWBtPGrOCgs3wVEmQmwyuNtB10IZMfmYDE0riwNR1cu4q+pPcxMVtaG3TA==",
        "lockfile_sha256": "fdb304e6af930a505bf8433a226c2dc905cee9d7d250f57de724841bdc56dd87",
        "registry": "https://registry.npmjs.org/",
        "command": "node_modules/.bin/playwright",
        "probe_args": ["--version"],
    },
}

_SAFE_ENV_KEYS = {
    "LANG",
    "LC_ALL",
    "PATH",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def install_root() -> Path:
    configured = os.getenv("AUTONOMY_CAPABILITY_ROOT", "").strip()
    default = Path(__file__).resolve().parent / "data" / "capabilities"
    return Path(configured).expanduser().resolve() if configured else default.resolve()


def recipe_for(capability_id: str) -> dict[str, Any]:
    recipe = RECIPES.get(capability_id)
    if not recipe:
        raise KeyError(capability_id)
    return dict(recipe)


def recipe_digest(capability_id: str) -> str:
    canonical = json.dumps(
        recipe_for(capability_id),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def installation_enabled() -> bool:
    return os.getenv("AUTONOMY_INSTALL_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def build_install_plan(capability_id: str) -> dict[str, Any]:
    recipe = recipe_for(capability_id)
    target = install_root() / capability_id
    return {
        "capability_id": capability_id,
        "recipe": recipe,
        "recipe_digest": recipe_digest(capability_id),
        "target": str(target),
        "enabled": installation_enabled(),
        "automatic_execution": False,
        "isolation": {
            "shell": False,
            "lifecycle_scripts": False,
            "privilege_escalation": False,
            "secret_environment": False,
            "atomic_activation": True,
        },
        "preflight": [
            f"Install exact package {recipe['package']}@{recipe['version']}",
            f"Require declared license {recipe['license']} and pinned registry integrity",
            "Run without a shell and with package lifecycle scripts disabled",
            "Expose no application credentials to the installer process",
            "Activate atomically only after package and executable verification",
        ],
        "rollback": "Remove only the managed capability directory whose manifest matches this recipe digest.",
    }


def inspect_managed_provider(capability_id: str) -> dict[str, Any]:
    try:
        recipe = recipe_for(capability_id)
    except KeyError:
        return {"status": "missing", "detail": "No managed recipe"}
    target = install_root() / capability_id
    manifest_path = target / "hermes-capability.json"
    command_path = target / recipe["command"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"status": "missing", "detail": "Not installed"}
    if (
        manifest.get("capability_id") != capability_id
        or manifest.get("recipe_digest") != recipe_digest(capability_id)
        or not command_path.is_file()
    ):
        return {"status": "broken", "detail": "Manifest or executable verification failed"}
    return {
        "status": "ready",
        "detail": f"Managed {recipe['package']} {recipe['version']}",
        "command": str(command_path),
    }


def _restricted_env(home: Path, recipe: dict[str, Any]) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key in _SAFE_ENV_KEYS}
    environment.update(
        {
            "HOME": str(home),
            "NO_COLOR": "1",
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_CACHE": str(home / ".npm-cache"),
            "NPM_CONFIG_FUND": "false",
            "NPM_CONFIG_IGNORE_SCRIPTS": "true",
            "NPM_CONFIG_REGISTRY": recipe["registry"],
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        }
    )
    return environment


def _verify_npm_install(staging: Path, capability_id: str, recipe: dict[str, Any]) -> dict[str, Any]:
    package_path = staging / "node_modules" / recipe["package"] / "package.json"
    command_path = staging / recipe["command"]
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package.get("version") != recipe["version"]:
        raise RuntimeError("Installed package version does not match the approved recipe")
    if package.get("license") != recipe["license"]:
        raise RuntimeError("Installed package license does not match the approved recipe")
    lock_path = staging / "package-lock.json"
    lock_bytes = lock_path.read_bytes()
    if hashlib.sha256(lock_bytes).hexdigest() != recipe["lockfile_sha256"]:
        raise RuntimeError("Installed dependency lockfile does not match the approved recipe")
    lock = json.loads(lock_bytes)
    lock_entry = lock.get("packages", {}).get(f"node_modules/{recipe['package']}", {})
    if lock_entry.get("integrity") != recipe["integrity"]:
        raise RuntimeError("Installed package integrity does not match the approved recipe")
    if not command_path.is_file():
        raise RuntimeError("Installed capability executable is missing")
    completed = subprocess.run(
        [str(command_path), *recipe["probe_args"]],
        cwd=staging,
        env=_restricted_env(staging, recipe),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Capability probe failed with exit code {completed.returncode}")
    return {
        "capability_id": capability_id,
        "provider": recipe["package"],
        "version": recipe["version"],
        "probe": (completed.stdout or completed.stderr).strip()[:240],
    }


def install_capability(capability_id: str, expected_digest: str) -> dict[str, Any]:
    """Install one registry recipe after the Control Plane approved its digest."""
    if not installation_enabled():
        raise RuntimeError("Capability installation is disabled by AUTONOMY_INSTALL_ENABLED")
    recipe = recipe_for(capability_id)
    actual_digest = recipe_digest(capability_id)
    if not expected_digest or expected_digest != actual_digest:
        raise RuntimeError("Approved recipe changed; create a new proposal")
    if recipe["manager"] != "npm":
        raise RuntimeError("Unsupported package manager")
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("The reviewed npm installer is unavailable in this runtime")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is unavailable in this runtime")
    node_version = subprocess.run(
        [node, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        shell=False,
    )
    match = re.match(r"^v?(\d+)", (node_version.stdout or "").strip())
    if node_version.returncode != 0 or not match or int(match.group(1)) < 18:
        raise RuntimeError("The reviewed Playwright recipe requires Node.js 18 or newer")

    root = install_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".install.lock"
    target = root / capability_id
    staging = root / f".staging-{capability_id}-{uuid.uuid4().hex[:10]}"
    backup = root / f".backup-{capability_id}-{uuid.uuid4().hex[:10]}"
    timeout = max(30, min(int(os.getenv("AUTONOMY_INSTALL_TIMEOUT_SECONDS", "300")), 900))
    recipe_source = Path(__file__).resolve().parent / "capability_recipes" / capability_id

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        existing = inspect_managed_provider(capability_id)
        if existing["status"] == "ready":
            return {"status": "already_installed", **existing}
        staging.mkdir(mode=0o750)
        try:
            for filename in ("package.json", "package-lock.json"):
                source = recipe_source / filename
                if not source.is_file():
                    raise RuntimeError(f"Reviewed recipe file is missing: {filename}")
                shutil.copy2(source, staging / filename)
            completed = subprocess.run(
                [
                    npm,
                    "ci",
                    "--prefix",
                    str(staging),
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                ],
                cwd=staging,
                env=_restricted_env(staging, recipe),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
                start_new_session=True,
            )
            output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()[-6000:]
            if completed.returncode != 0:
                raise RuntimeError(f"npm exited with {completed.returncode}: {output}")
            result = _verify_npm_install(staging, capability_id, recipe)
            manifest = {
                "capability_id": capability_id,
                "recipe_digest": actual_digest,
                "recipe": recipe,
                "installed_at": _now(),
            }
            (staging / "hermes-capability.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if target.exists():
                target.rename(backup)
            staging.rename(target)
            if backup.exists():
                shutil.rmtree(backup)
            return {"status": "installed", "target": str(target), **result}
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise


def rollback_capability(capability_id: str, expected_digest: str) -> dict[str, Any]:
    target = install_root() / capability_id
    manifest_path = target / "hermes-capability.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Managed installation manifest is missing") from exc
    if (
        manifest.get("capability_id") != capability_id
        or manifest.get("recipe_digest") != expected_digest
        or expected_digest != recipe_digest(capability_id)
    ):
        raise RuntimeError("Rollback ownership verification failed")
    shutil.rmtree(target)
    return {"status": "rolled_back", "capability_id": capability_id}
