#!/usr/bin/env python3
"""Record docs/demo/media/ for the 7-minute stand. Not a Makefile target.

Writes: make-demo.cast, make-demo.gif, make-demo.svg, and four PNGs.
UI shots use Playwright + Chrome against a local uvicorn/Vite stack.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

MEDIA = _ROOT / "docs" / "demo" / "media"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BG = (11, 18, 32)
FG = (200, 208, 220)
CYAN = (0, 240, 255)
GREEN = (16, 185, 129)
RED = (239, 68, 68)
AMBER = (245, 158, 11)


def _venv_py() -> str:
    return str(_ROOT / "backend" / ".venv" / "bin" / "python")


def _run_demo() -> str:
    env = os.environ.copy()
    env["DATABASE_URL"] = ""
    env["PYTHONPATH"] = str(_ROOT)
    env.pop("CODE_AGENTS_ENABLED", None)
    proc = subprocess.run(
        [_venv_py(), str(_ROOT / "scripts" / "demo.py")],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout or "demo failed")
    return proc.stdout.replace("\r\n", "\n")


def _color_for(line: str) -> tuple[int, int, int]:
    if "FAIL" in line or "tamper" in line.lower() and "FAIL" in line:
        return RED
    if "DISABLED" in line or "CODE_AGENTS_ENABLED=false" in line:
        return AMBER
    if "DEMO_OK" in line or line.startswith("ok checked=") or "offline ok" in line:
        return GREEN
    if line.startswith("[demo]") or line.startswith("==="):
        return CYAN
    return FG


def write_cast(text: str, path: Path) -> None:
    lines = text.splitlines()
    header = {
        "version": 2,
        "width": 100,
        "height": 38,
        "timestamp": 0,
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
    }
    t = 0.15
    events: list[list] = [[0.0, "o", "$ make demo\r\n"]]
    for line in lines:
        events.append([round(t, 3), "o", line + "\r\n"])
        t += 0.07
    events.append([round(t + 0.8, 3), "o", ""])
    path.write_text(
        json.dumps(header, separators=(",", ":")) + "\n"
        + "\n".join(json.dumps(ev, separators=(",", ":")) for ev in events)
        + "\n",
        encoding="utf-8",
    )


def _draw_terminal(lines: list[str], *, width: int = 920, pad: int = 16):
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, 13)
    line_h = 18
    height = pad * 2 + max(1, len(lines)) * line_h
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        draw.text((pad, y), line[:118], font=font, fill=_color_for(line))
        y += line_h
    return img


def write_gif(text: str, path: Path) -> None:
    lines = text.splitlines()
    frames = []
    for i in range(1, len(lines) + 1):
        frames.append(_draw_terminal(lines[:i]))
    frames += [_draw_terminal(lines)] * 12
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        optimize=True,
    )


def write_svg(text: str, path: Path) -> None:
    lines = text.splitlines()
    width, line_h, pad = 920, 18, 16
    height = pad * 2 + max(1, len(lines)) * line_h
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="make demo">',
        f'<rect width="100%" height="100%" fill="#0b1220"/>',
        '<style>text{font:13px "DejaVu Sans Mono", ui-monospace, monospace}</style>',
    ]
    y = pad + 13
    for i, line in enumerate(lines):
        rgb = _color_for(line)
        color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        esc = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        delay = round(i * 0.07, 2)
        parts.append(
            f'<text x="{pad}" y="{y}" fill="{color}" xml:space="preserve">'
            f'<animate attributeName="opacity" from="0" to="1" begin="{delay}s" dur="0.01s" fill="freeze"/>'
            f"{esc}</text>"
        )
        y += line_h
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_excerpt_png(text: str, start: str, path: Path, until: str | None = None) -> None:
    lines = text.splitlines()
    try:
        i = next(n for n, line in enumerate(lines) if start in line)
    except StopIteration as exc:
        raise SystemExit(f"no line matching {start!r}") from exc
    j = len(lines)
    if until:
        j = next((n for n, line in enumerate(lines[i + 1 :], i + 1) if until in line), len(lines))
    picked = lines[i:j]
    if not picked:
        raise SystemExit(f"empty excerpt for {start!r}")
    _draw_terminal(picked, width=920).save(path, "PNG", optimize=True)


def _wait_http(url: str, timeout: float = 60) -> None:
    import urllib.request

    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return
        except Exception as exc:
            last = str(exc)
        time.sleep(0.3)
    raise SystemExit(f"timeout waiting for {url}: {last}")


def _demo_mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location("hermes_demo_stand", _ROOT / "scripts" / "demo.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _start_backend() -> tuple[str, object]:
    os.environ["ENV"] = "development"
    os.environ["DATABASE_URL"] = ""
    os.environ.pop("CODE_AGENTS_ENABLED", None)
    os.environ["OPENROUTER_API_KEY"] = "local"
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    os.environ["ALLOW_LOCAL_AUTH_FALLBACK"] = "1"

    from unittest.mock import patch

    demo = _demo_mod()
    demo.reset_demo()
    demo.isolate_demo_db()
    with patch("backend.tools.execute_command"), patch("backend.subagents.requests.post"):
        demo.seed_pending()
    from backend.auth import create_session
    from backend.main import app
    import uvicorn

    token = create_session()
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_http("http://127.0.0.1:8000/api/status", timeout=90)
    return token, server


def _start_frontend() -> subprocess.Popen:
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
        cwd=str(_ROOT / "frontend"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_http("http://127.0.0.1:5173")
    return proc


def capture_ui(token: str) -> None:
    from playwright.sync_api import sync_playwright

    pending = MEDIA / "ui-pending-execute-code.png"
    resolved = MEDIA / "ui-approved-rejected.png"
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.add_init_script(
            f"localStorage.setItem('jarvis_auth_token', {json.dumps(token)});"
        )
        page.goto("http://127.0.0.1:5173", wait_until="domcontentloaded")
        page.wait_for_selector("button.approvals-badge-btn", timeout=20000)
        page.locator("button.approvals-badge-btn").click()
        page.wait_for_selector("text=GOVERNANCE APPROVALS", timeout=10000)
        page.get_by_role("button", name="Show evidence #2").click()
        page.wait_for_timeout(500)
        page.locator("dialog").screenshot(path=str(pending))

        page.get_by_placeholder("resolver note...").fill("Read-only print. OK once.")
        page.get_by_role("button", name="Approve").click()
        page.wait_for_timeout(400)
        page.get_by_role("button", name="Show evidence #1").click()
        page.get_by_placeholder("resolver note...").fill("Destructive delete. Rejected for this session.")
        page.get_by_role("button", name="Reject").click()
        page.wait_for_timeout(400)
        page.get_by_role("button", name="All").click()
        page.wait_for_timeout(500)
        page.locator("dialog").screenshot(path=str(resolved))
        browser.close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Record docs/demo/media for the demo stand")
    parser.add_argument("--terminal-only", action="store_true", help="skip Playwright UI shots")
    args = parser.parse_args(argv)

    MEDIA.mkdir(parents=True, exist_ok=True)
    text = _run_demo()
    write_cast(text, MEDIA / "make-demo.cast")
    write_gif(text, MEDIA / "make-demo.gif")
    write_svg(text, MEDIA / "make-demo.svg")
    write_excerpt_png(
        text,
        "R1-2 kill switch CODE_AGENTS_ENABLED=false",
        MEDIA / "kill-switch-disabled.png",
        until="=== 3:40",
    )
    write_excerpt_png(
        text,
        "Export + offline",
        MEDIA / "verify-ok-tamper-fail.png",
        until="=== 6:40",
    )

    if not args.terminal_only:
        frontend: subprocess.Popen | None = None
        try:
            token, _server = _start_backend()
            frontend = _start_frontend()
            capture_ui(token)
        finally:
            if frontend is not None:
                frontend.terminate()
                try:
                    frontend.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    frontend.kill()

    gif_bytes = (MEDIA / "make-demo.gif").stat().st_size
    if gif_bytes > 3 * 1024 * 1024:
        raise SystemExit(f"GIF too large: {gif_bytes} bytes")
    print(f"[demo-record] wrote {MEDIA} gif={gif_bytes}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
