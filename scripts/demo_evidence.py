#!/usr/bin/env python3
"""Assemble docs/demo/evidence/ from a finished `make demo` run.

No backend/frontend edits. Uses the demo export zip as-is, plus
scripts/verify_decision_log.py on a clean copy and a tampered copy.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUT_DEFAULT = _ROOT / "docs" / "demo" / "evidence"
SAMPLE_ZIP = "hermes-evidence-sample.zip"
DECISION_ZIP = "decision-log.zip"
TAMPER_ZIP = "decision-log.tampered.zip"
BANNED = (
    "/agent/repos",
    "/home/ubuntu",
    "cursor.com/agents",
    "@gmail.com",
    "sk-",
    "Bearer ",
)
_HUMAN = frozenset({"APPROVED", "REJECTED"})


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


def _verify(path: Path, pin: str | None = None) -> tuple[int, str]:
    argv = [sys.executable, str(_ROOT / "scripts" / "verify_decision_log.py"), str(path)]
    if pin:
        argv.extend(["--pin", pin])
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text.strip() + "\n"


def _calls(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        if row.get("event") not in _HUMAN:
            continue
        out.append(
            {
                "tool": str(row["action_name"]),
                "decision": str(row["event"]),
                "timestamp": str(row["occurred_at"]),
                "payload_sha256": str(row["payload_hash"]),
            }
        )
    return out


def _write_calls(out_dir: Path, calls: list[dict[str, str]]) -> None:
    (out_dir / "calls.json").write_text(
        json.dumps(calls, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=["tool", "decision", "timestamp", "payload_sha256"]
    )
    writer.writeheader()
    writer.writerows(calls)
    (out_dir / "calls.csv").write_text(buf.getvalue(), encoding="utf-8")
    lines = [
        "| tool | decision | timestamp | payload_sha256 |",
        "| --- | --- | --- | --- |",
    ]
    for row in calls:
        lines.append(
            f"| {row['tool']} | {row['decision']} | {row['timestamp']} | `{row['payload_sha256']}` |"
        )
    (out_dir / "calls.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _policy() -> dict[str, Any]:
    from backend.governance import HIGH_RISK_TOOLS

    return {
        "HIGH_RISK_TOOLS": sorted(HIGH_RISK_TOOLS),
        "CODE_AGENTS_ENABLED": {
            "approval_path": "true",
            "kill_switch": "false",
            "accepted": ["1", "true", "yes", "on"],
            "note": "demo pins these explicitly; unrecognised values fail closed",
        },
        "gate": {
            "function": "gate_tool",
            "high_risk_names": "HIGH_RISK_TOOLS",
            "approval": "one-shot, payload-bound, session-keyed",
        },
    }


def _readme() -> str:
    return """# Hermes Synapse — sample evidence pack

Built from `make demo` (scripted agent, demo seed data only). Hash-chained
decision log, not a signature scheme. No Ed25519 signed-audit-log in this pack.

## What's inside

| File | What |
| --- | --- |
| `decision-log.zip` | Unchanged demo `export_zip` (`decisions.jsonl`, `evidence/*.json`, `manifest.json`) |
| `decision-log.tampered.zip` | Same archive with one `reason` field edited |
| `verifier-ok.txt` | `scripts/verify_decision_log.py` on the clean export |
| `verifier-fail.txt` | Same checker on the tampered copy |
| `calls.json` / `calls.csv` / `calls.md` | APPROVED/REJECTED: tool, decision, timestamp, payload SHA-256 (no raw payloads) |
| `policy.json` | `HIGH_RISK_TOOLS` plus the `CODE_AGENTS_ENABLED` values the demo pins |

## Verify

From the repository root (Python stdlib, no Hermes install, no network):

```bash
python3 scripts/verify_decision_log.py docs/demo/evidence/decision-log.zip
python3 scripts/verify_decision_log.py docs/demo/evidence/decision-log.tampered.zip
```

Expect exit 0 and `ok checked=N head=H` on the first. Expect exit 1 and
`FAIL seq=… entry_hash mismatch` on the second.

Optional pin (head hash is the last token in `verifier-ok.txt`):

```bash
python3 scripts/verify_decision_log.py docs/demo/evidence/decision-log.zip --pin <head>
```

Regenerate: `make evidence`.
"""


def _assert_anonymous(path: Path) -> None:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            blob = b"".join(archive.read(name) for name in archive.namelist())
            blob += " ".join(archive.namelist()).encode()
    else:
        blob = path.read_bytes()
    lowered = blob.lower()
    for needle in BANNED:
        if needle.encode() in blob or needle.lower().encode() in lowered:
            raise SystemExit(f"{path.name} contains {needle!r}")


def _zip_sample(out_dir: Path, dest: Path) -> None:
    names = sorted(
        p.name for p in out_dir.iterdir() if p.is_file() and p.name != SAMPLE_ZIP
    )
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(out_dir / name, arcname=name)


def assemble(*, export_dir: Path, out_dir: Path) -> Path:
    """Build the evidence folder from a demo export directory. Returns the sample zip."""
    src = find_export(export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for leftover in out_dir.iterdir():
        if leftover.is_file():
            leftover.unlink()

    dest = out_dir / DECISION_ZIP
    dest.write_bytes(src.read_bytes())
    tampered = out_dir / TAMPER_ZIP
    _tamper(dest, tampered)

    with zipfile.ZipFile(dest) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        rows = [
            json.loads(line)
            for line in archive.read("decisions.jsonl").decode().splitlines()
            if line.strip()
        ]
    pin = str(manifest.get("head_hash") or "")
    ok_code, ok_text = _verify(dest, pin=pin or None)
    fail_code, fail_text = _verify(tampered)
    if ok_code != 0:
        raise SystemExit(f"clean export must verify: {ok_text}")
    if fail_code == 0:
        raise SystemExit("tampered export must fail verification")
    (out_dir / "verifier-ok.txt").write_text(ok_text, encoding="utf-8")
    (out_dir / "verifier-fail.txt").write_text(fail_text, encoding="utf-8")

    _write_calls(out_dir, _calls(rows))
    (out_dir / "policy.json").write_text(
        json.dumps(_policy(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(_readme(), encoding="utf-8")

    sample = out_dir / SAMPLE_ZIP
    _zip_sample(out_dir, sample)
    for path in out_dir.iterdir():
        if path.is_file():
            _assert_anonymous(path)
    return sample


def main(argv: list[str] | None = None) -> int:
    del argv
    sample = assemble(export_dir=demo_export_dir(), out_dir=OUT_DEFAULT)
    print(f"[evidence] wrote {sample} bytes={sample.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
