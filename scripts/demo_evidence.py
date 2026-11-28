#!/usr/bin/env python3
"""Assemble docs/demo/evidence/ from a finished `make demo` run.

No backend/frontend edits. Uses the demo export zip as-is, plus a byte copy
of scripts/verify_decision_log.py on a clean copy and a tampered copy.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUT_DEFAULT = _ROOT / "docs" / "demo" / "evidence"
SAMPLE_ZIP = "hermes-evidence-sample.zip"
KEEP = frozenset({"SPEC.md"})
DECISION_ZIP = "decision-log.zip"
TAMPER_ZIP = "decision-log.tampered.zip"
BANNED = (
    "/agent/repos",
    "/agent",
    "/home",
    "/workspace",
    "/Users",
    "cursor.com/agents",
    "@gmail.com",
    "sk-",
    "Bearer",
    "token",
    "password",
    "ed25519",
    "audit-log",
)
CALL_FIELDS = (
    "seq",
    "request_id",
    "tool",
    "decision",
    "event",
    "actor_subject",
    "actor_roles",
    "auth_method",
    "reason",
    "occurred_at",
    "payload_sha256",
    "synthetic",
    "role_status",
)
KNOWN_LIMITS = """\
1. RBAC is not wired. The approve endpoint does not check roles. Any logged-in session can approve. Each decision records the approver's subject and login method, with the roles.
2. The log is tamper-evident when you pin its head hash. This sample pack does not include signed checkpoints; the zip log carries no signatures.
3. No SOC 2 or other certification. One maintainer. No named customers.
4. Approvals cover agents running in Hermes, including their calls to external MCP tools. There is no gateway in front of Claude Code or Cursor, or in front of other MCP clients.
5. Code agents are off by default. When switched on, each `execute_code` call waits for an approval tied to the exact source.
6. Raw tool arguments remain in `approval_requests.payload` for matching. Evidence and HTTP responses are masked (R2-4).
7. `bundle_hash` does not cover the description, the links or the excerpts.
8. A rejected call stays rejected for that session with no cooldown (R2-2).
9. Secret redaction matches known formats and nothing else. There is no policy language and no built-in criteria such as order size.
10. The log covers gated actions and approval events, not every conversation turn. Seven-year retention and backups are the buyer's job.
11. The sample is built from a scripted agent with a mocked shell and sandbox.
"""


def demo_export_dir() -> Path:
    raw = os.environ.get("HERMES_DEMO_EXPORT", "").strip()
    return Path(raw) if raw else _ROOT / "backend" / "data" / "demo"


def find_export(export_dir: Path) -> Path:
    zips = sorted(
        (p for p in export_dir.glob("hermes-decisions-*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not zips:
        raise SystemExit("no demo export zip; run `make demo` first")
    return zips[-1]


def _git(ref: str) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    sha = (proc.stdout or "").strip()
    return sha if proc.returncode == 0 and len(sha) == 40 else "not recorded by product"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tamper(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(src) as zin:
        files = {name: zin.read(name) for name in zin.namelist()}
    lines = [line for line in files["decisions.jsonl"].decode().splitlines() if line.strip()]
    row = json.loads(lines[0])
    row["reason"] = "tampered"
    lines[0] = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    files["decisions.jsonl"] = ("\n".join(lines) + "\n").encode()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)


def _verify(verifier: Path, archive: Path, pin: str | None = None) -> tuple[int, str]:
    argv = [sys.executable, str(verifier), str(archive)]
    if pin:
        argv.extend(["--pin", pin])
    proc = subprocess.run(argv, capture_output=True, text=True, check=False, cwd=str(archive.parent))
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text.strip() + "\n"


def _calls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        event = str(row["event"])
        out.append(
            {
                "seq": int(row["seq"]),
                "request_id": int(row["request_id"]),
                "tool": str(row["action_name"]),
                "decision": event,
                "event": event,
                "actor_subject": str(row["actor_subject"]),
                "actor_roles": str(row["actor_roles"]),
                "auth_method": str(row["auth_method"]),
                "reason": str(row.get("reason") or ""),
                "occurred_at": str(row["occurred_at"]),
                "payload_sha256": str(row["payload_hash"]),
                "synthetic": True,
                "role_status": "recorded, not verified",
            }
        )
    return out


def _write_calls(out_dir: Path, calls: list[dict[str, Any]]) -> None:
    folder = out_dir / "approvals"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "calls.json").write_text(
        json.dumps(calls, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(CALL_FIELDS))
    writer.writeheader()
    writer.writerows(calls)
    (folder / "calls.csv").write_text(buf.getvalue(), encoding="utf-8")
    header = (
        "| seq | request_id | tool | decision | event | actor_subject | actor_roles "
        "| auth_method | reason | occurred_at (UTC) | payload_sha256 | synthetic | role_status |"
    )
    sep = "| " + " | ".join("---" for _ in CALL_FIELDS) + " |"
    lines = [header, sep]
    for row in calls:
        lines.append(
            "| "
            + " | ".join(
                "`" + str(row[k]) + "`" if k == "payload_sha256" else str(row[k])
                for k in CALL_FIELDS
            )
            + " |"
        )
    (folder / "calls.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_code_agents_default() -> dict[str, Any]:
    """Read the process default from the files on this commit. Do not invent it."""
    env_line, env_val = None, None
    for i, line in enumerate((_ROOT / ".env.example").read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("CODE_AGENTS_ENABLED="):
            env_line = i
            env_val = line.split("=", 1)[1].strip().strip("\"'").lower()
            break
    compose_line, compose_val = None, None
    for i, line in enumerate((_ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines(), 1):
        match = re.search(r"CODE_AGENTS_ENABLED:\s*\$\{CODE_AGENTS_ENABLED:-([^}]+)\}", line)
        if match:
            compose_line = i
            compose_val = match.group(1).strip().lower()
            break
    sub_src = (_ROOT / "backend" / "subagents.py").read_text(encoding="utf-8")
    match = re.search(
        r'def code_agents_enabled\(\)[\s\S]*?os\.getenv\("CODE_AGENTS_ENABLED"\) or "([^"]+)"',
        sub_src,
    )
    unset = match.group(1).lower() if match else None
    # JSON false means the kill switch defaults off (same as code_agents_enabled()).
    enabled_by_default = unset in ("1", "true", "yes", "on")
    return {
        "pilot_default": enabled_by_default,
        "read_from": {
            ".env.example": {"line": env_line, "value": env_val},
            "docker-compose.yml": {"line": compose_line, "value": compose_val},
            "backend/subagents.py:code_agents_enabled": {"unset_fallback": unset},
        },
    }


def _config_snapshot() -> dict[str, Any]:
    from backend.governance import _high_risk_names
    from backend.mcp_client import mcp_tool_needs_approval

    code_agents = _read_code_agents_default()
    return {
        "commit": _git("HEAD"),
        "CODE_AGENTS_ENABLED": {
            "pilot_default": code_agents["pilot_default"],
            "read_from": code_agents["read_from"],
            "demo_pinned_for_approval_step": "true",
            "demo_pinned_for_kill_switch_step": "false",
            "accepted_on": ["1", "true", "yes", "on"],
        },
        "high_risk_tools": sorted(_high_risk_names()),
        "high_risk_tools_source": "backend.governance._high_risk_names()",
        "mcp_rule": (
            "an MCP tool needs approval unless it is marked readOnlyHint true or "
            "destructiveHint false; omitted annotations follow MCP defaults "
            "(readOnlyHint false, destructiveHint true)"
        ),
        "mcp_rule_source": "backend.mcp_client.mcp_tool_needs_approval",
        "mcp_rule_doc": (mcp_tool_needs_approval.__doc__ or "").strip().splitlines()[0],
    }


def _readme() -> str:
    return """# Hermes Synapse: sample evidence pack

This is not legal advice. This pack does not make you compliant.

This sample pack does not include signed checkpoints. The zip log
carries no signatures. In real use the pin is recorded off-host
(for example in the email that carries the export), and a pin stored
inside the same zip is a demonstration.

Every payload, every name and every file in this pack is synthetic
(`partner.example`, `customers.csv`, `demo-operator`). Nothing came from
a real install or client.

Built from `make demo` (scripted agent, mocked shell and sandbox).
Times in the lists are UTC (`occurred_at`). The role on each row is
recorded and not enforced.

## Known limits (short)

- The approve endpoint checks no role. Any logged-in session can approve, and the log records the subject, the roles and the login method. RBAC is not wired.
- The log in this sample pack is tamper-evident with a pinned head hash and carries no signatures.
- No SOC 2 and no named customers.
- Approvals cover agents running in Hermes, with no gateway in front of other clients.
- Code agents are off by default.
- This sample comes from a scripted agent with a mocked shell and sandbox.

Full list: `limits/known-limits.md`.

## What's inside

| File | What |
| --- | --- |
| `decision-log.zip` | Unchanged demo export (`decisions.jsonl`, `evidence/*.json`, `manifest.json`) |
| `decision-log.tampered.zip` | Same archive with the reason of seq 1 edited to `tampered` |
| `verifier/verify_decision_log.py` | Byte copy of the repository checker |
| `verifier-ok.txt` | Checker output on the clean export |
| `negative-control-expected-output.txt` | Checker output and exit code on the tampered copy |
| `pinned-head-hash.txt` | 64 hex characters, one line, no prefix |
| `approvals/calls.json` / `.csv` / `.md` | All decision rows: tool, event, who, roles, login method, reason, UTC time, payload SHA-256 |
| `config/config-snapshot.json` | `HIGH_RISK_TOOLS` from `_high_risk_names()`, MCP rule, `pilot_default` false, commit |
| `SUMMARY.md` | One-page compliance summary |
| `MANIFEST.json` | SHA-256 and size of every file in this pack |
| `limits/known-limits.md` | Eleven known limits |

The inner `VERIFY.md` still points at the repository copy of the checker, for comparison.

## Verify

From this unzipped folder (Python 3.11+ standard library, no Hermes install, no network):

```bash
python3 verifier/verify_decision_log.py decision-log.zip
python3 verifier/verify_decision_log.py decision-log.zip --pin "$(cat pinned-head-hash.txt)"
python3 verifier/verify_decision_log.py decision-log.tampered.zip
```

Expect exit 0 and `ok checked=N head=H` on the first two. Expect exit 1 and
`FAIL seq=1 entry_hash mismatch` on the third (see `negative-control-expected-output.txt`).

Regenerate from a checkout: `make evidence`.
"""


def _summary(calls: list[dict[str, Any]], ok_text: str) -> str:
    lines = [
        "# Compliance summary",
        "",
        "This is not legal advice. This pack does not make you compliant.",
        "",
        "This is a sample evidence pack from a scripted Hermes Synapse demo.",
        "It shows the format of an export you would build with a buyer in a pilot.",
        "It is not a claim that anyone is compliant. This sample pack does not include signed checkpoints; the zip log carries no signatures.",
        "Every payload, name and file here is synthetic.",
        "",
        "## What happened (six log rows)",
        "",
    ]
    for row in calls:
        ran = "ran once" if row["event"] == "CONSUMED" else "did not run in this row"
        lines.append(
            f"- Request {row['request_id']}, seq {row['seq']}: `{row['tool']}` "
            f"**{row['event']}** by `{row['actor_subject']}` "
            f"(login `{row['auth_method']}`, roles `{row['actor_roles']}`, "
            f"role recorded, not verified) at {row['occurred_at']} UTC. "
            f"Payload SHA-256 `{row['payload_sha256']}`. {ran}."
        )
        if row["reason"]:
            lines.append(f"  Reviewer note: {row['reason']}")
    lines += [
        "",
        "## Verification",
        "",
        f"Clean export: `{ok_text.strip()}`.",
        "Negative control (reason of seq 1 edited): `FAIL seq=1 entry_hash mismatch`, exit 1.",
        "",
        "From this unzipped folder:",
        "",
        "```bash",
        "python3 verifier/verify_decision_log.py decision-log.zip",
        'python3 verifier/verify_decision_log.py decision-log.zip --pin "$(cat pinned-head-hash.txt)"',
        "python3 verifier/verify_decision_log.py decision-log.tampered.zip",
        "```",
        "",
        "## Config (one line)",
        "",
        "Code agents off by default (`pilot_default` false); demo pins them on for the approve step and off for the kill-switch step; high-risk tools and MCP writes wait at `gate_tool`.",
        "",
        "## Limits (five lines)",
        "",
        "- The approve endpoint checks no role. Any logged-in session can approve; the log records subject, roles and login method. RBAC is not wired.",
        "- The log in this sample pack is tamper-evident with a pinned head hash and carries no signatures.",
        "- No SOC 2 and no named customers. Approvals cover agents in Hermes; there is no gateway in front of other clients.",
        "- Code agents are off by default.",
        "- This sample comes from a scripted agent with a mocked shell and sandbox.",
        "",
    ]
    return "\n".join(lines)


def _pack_paths(out_dir: Path) -> list[Path]:
    paths = []
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in KEEP or path.name == SAMPLE_ZIP:
            continue
        paths.append(path)
    return paths


def _write_manifest(out_dir: Path, files: list[Path]) -> None:
    listed = {}
    for path in files:
        rel = path.relative_to(out_dir).as_posix()
        listed[rel] = {"sha256": _sha256(path), "size": path.stat().st_size}
    body = {
        "package": "hermes-evidence-sample",
        "build_time_utc": datetime.now(UTC).isoformat(),
        "main_commit": _git("origin/main"),
        "demo_commit": _git("HEAD"),
        "generator": "scripts/demo_evidence.py",
        "data_source": "scripted demo, mocked shell and sandbox",
        "python": sys.version.split()[0],
        "files": listed,
    }
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _assert_anonymous(path: Path) -> None:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            blob = b"".join(archive.read(name) for name in archive.namelist())
            blob += " ".join(archive.namelist()).encode()
    else:
        blob = path.read_bytes()
    lowered = blob.lower()
    for needle in BANNED:
        raw = needle.encode()
        if raw in blob or raw.lower() in lowered:
            raise SystemExit(f"{path} contains {needle!r}")


def _zip_sample(out_dir: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _pack_paths(out_dir):
            archive.write(path, arcname=path.relative_to(out_dir).as_posix())


def _clear(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in out_dir.iterdir():
        if item.name in KEEP:
            continue
        if item.is_file():
            item.unlink()
        else:
            shutil.rmtree(item)


def assemble(*, export_dir: Path, out_dir: Path) -> Path:
    """Build the evidence folder from a demo export directory. Returns the sample zip."""
    src = find_export(export_dir)
    _clear(out_dir)

    dest = out_dir / DECISION_ZIP
    dest.write_bytes(src.read_bytes())
    tampered = out_dir / TAMPER_ZIP
    _tamper(dest, tampered)

    verifier = out_dir / "verifier" / "verify_decision_log.py"
    verifier.parent.mkdir(parents=True, exist_ok=True)
    source_verifier = _ROOT / "scripts" / "verify_decision_log.py"
    verifier.write_bytes(source_verifier.read_bytes())

    with zipfile.ZipFile(dest) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        rows = [
            json.loads(line)
            for line in archive.read("decisions.jsonl").decode().splitlines()
            if line.strip()
        ]
    pin = str(manifest.get("head_hash") or "")
    if len(pin) != 64 or any(ch not in "0123456789abcdef" for ch in pin.lower()):
        raise SystemExit("export head hash is not 64 hex")
    (out_dir / "pinned-head-hash.txt").write_text(pin + "\n", encoding="utf-8")

    ok_code, ok_text = _verify(verifier, dest, pin=pin)
    fail_code, fail_text = _verify(verifier, tampered)
    if ok_code != 0:
        raise SystemExit(f"clean export must verify: {ok_text}")
    if fail_code == 0:
        raise SystemExit("tampered export must fail verification")
    (out_dir / "verifier-ok.txt").write_text(ok_text, encoding="utf-8")
    (out_dir / "negative-control-expected-output.txt").write_text(
        fail_text.rstrip() + f"\nexit {fail_code}\nedited: the reason of seq 1\n",
        encoding="utf-8",
    )

    calls = _calls(rows)
    _write_calls(out_dir, calls)
    (out_dir / "config").mkdir(parents=True, exist_ok=True)
    (out_dir / "config" / "config-snapshot.json").write_text(
        json.dumps(_config_snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "limits").mkdir(parents=True, exist_ok=True)
    (out_dir / "limits" / "known-limits.md").write_text(KNOWN_LIMITS, encoding="utf-8")
    (out_dir / "README.md").write_text(_readme(), encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(_summary(calls, ok_text), encoding="utf-8")

    hashed = [p for p in _pack_paths(out_dir) if p.name != "MANIFEST.json"]
    _write_manifest(out_dir, hashed)

    sample = out_dir / SAMPLE_ZIP
    _zip_sample(out_dir, sample)
    for path in _pack_paths(out_dir):
        _assert_anonymous(path)
    return sample


def main(argv: list[str] | None = None) -> int:
    del argv
    sample = assemble(export_dir=demo_export_dir(), out_dir=OUT_DEFAULT)
    print(f"[evidence] wrote {sample} bytes={sample.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
