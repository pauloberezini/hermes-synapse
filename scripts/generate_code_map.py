#!/usr/bin/env python3
"""
Code Map & Call Graph Generator for Agent Experience (AX).
Scans backend Python files and frontend TS/TSX files to generate `.agents/code_map.md`.
Runs without external dependencies using standard Python libraries.
"""

import ast
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "src"
OUTPUT_FILE = PROJECT_ROOT / ".agents" / "code_map.md"


def parse_python_file(filepath: Path) -> dict:
    """Parses a Python file to extract classes, base classes, functions, and docstrings."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(filepath))
    except Exception as e:
        return {"error": str(e), "classes": [], "functions": [], "docstring": ""}

    docstring = ast.get_docstring(tree) or ""
    classes = []
    functions = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            methods = [
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({"name": node.name, "bases": bases, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)

    return {
        "docstring": docstring.split("\n")[0] if docstring else "",
        "classes": classes,
        "functions": functions,
        "size": len(content.splitlines()),
    }


def parse_ts_file(filepath: Path) -> dict:
    """Extracts exported components, interfaces, and functions from TS/TSX files using regex."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": str(e), "exports": [], "components": []}

    exports = re.findall(r'export\s+(?:const|function|class|interface|type)\s+([A-Za-z0-9_]+)', content)
    components = re.findall(r'export\s+default\s+(?:function|class)?\s*([A-Za-z0-9_]+)?', content)

    return {
        "exports": exports,
        "components": [c for c in components if c],
        "size": len(content.splitlines()),
    }


def generate_code_map() -> str:
    lines = [
        "# 🗺️ Project Architecture Code Map & Call Graph",
        "",
        "> **Auto-generated map for AI agents**. Updated by `scripts/generate_code_map.py`.",
        "",
        "---",
        "",
        "## 🐍 Backend Architecture (`backend/`)",
        "",
    ]

    if BACKEND_DIR.exists():
        py_files = sorted(BACKEND_DIR.rglob("*.py"))
        for py_file in py_files:
            rel_path = py_file.relative_to(PROJECT_ROOT)
            if any(part.startswith(".") or part in ("__pycache__", ".venv") for part in rel_path.parts):
                continue
            info = parse_python_file(py_file)
            lines.append(f"### 📄 [{py_file.name}](file://{py_file}) (`{rel_path}`) — {info.get('size', 0)} lines")
            if info.get("docstring"):
                lines.append(f"> *{info['docstring']}*")
            if info.get("classes"):
                lines.append("  - **Classes:**")
                for cls in info["classes"]:
                    base_str = f" (inherits `{', '.join(cls['bases'])}`)" if cls["bases"] else ""
                    methods_str = f" → methods: `{', '.join(cls['methods'][:8])}`" if cls["methods"] else ""
                    lines.append(f"    - `{cls['name']}`{base_str}{methods_str}")
            if info.get("functions"):
                funcs_preview = ", ".join(info["functions"][:10])
                if len(info["functions"]) > 10:
                    funcs_preview += f" (+{len(info['functions']) - 10} more)"
                lines.append(f"  - **Functions:** `{funcs_preview}`")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## ⚛️ Frontend Architecture (`frontend/src/`)",
        "",
    ])

    if FRONTEND_DIR.exists():
        ts_files = sorted(list(FRONTEND_DIR.rglob("*.ts")) + list(FRONTEND_DIR.rglob("*.tsx")))
        for ts_file in ts_files:
            rel_path = ts_file.relative_to(PROJECT_ROOT)
            if "node_modules" in rel_path.parts:
                continue
            info = parse_ts_file(ts_file)
            lines.append(f"### 📄 [{ts_file.name}](file://{ts_file}) (`{rel_path}`) — {info.get('size', 0)} lines")
            if info.get("exports"):
                lines.append(f"  - **Exports:** `{', '.join(info['exports'][:8])}`")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 🛠️ Key Verification Commands",
        "- **Backend Tests:** `pytest backend/tests/ -q`",
        "- **Frontend Check:** `npm --prefix frontend run build` or `npx tsc --noEmit`",
        "- **Structural Search:** `ast-grep --pattern '...' backend/`",
        "",
    ])

    return "\n".join(lines)


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = generate_code_map()
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(f"✅ Code map successfully generated at: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
