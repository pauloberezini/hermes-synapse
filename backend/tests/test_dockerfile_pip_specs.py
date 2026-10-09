"""Dockerfile RUN lines are /bin/sh: unquoted >= is stdout redirection."""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _pip_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("RUN pip install"):
            block = [lines[i]]
            while block[-1].rstrip().endswith("\\"):
                i += 1
                block.append(lines[i])
            blocks.append("\n".join(block))
        i += 1
    return blocks


def test_dockerfiles_quote_pip_version_specs_and_use_psycopg3():
    prod = (BACKEND / "Dockerfile").read_text()
    dev = (BACKEND / "Dockerfile.dev").read_text()
    for text in (prod, dev):
        for block in _pip_blocks(text):
            for line in block.splitlines():
                if ">=" not in line:
                    continue
                spec = line.strip().rstrip("\\").strip()
                assert spec.startswith('"') and spec.endswith('"'), spec
    assert "psycopg2-binary" not in prod
    assert '"psycopg[binary]>=3.1.0"' in prod
