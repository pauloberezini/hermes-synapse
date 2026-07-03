"""
obsidian.py — Jarvis integration with Obsidian via the "Local REST API" community plugin.

Setup:
  1. In Obsidian: Settings → Community Plugins → search "Local REST API" → Install & Enable
  2. Copy the generated API key into .env as OBSIDIAN_API_KEY=...
  3. Optionally set OBSIDIAN_PORT (default: 27123) and OBSIDIAN_VAULT_PATH

The plugin exposes a local HTTPS server (self-signed cert) that Jarvis uses to
read/write vault files and trigger searches without any cloud dependency.
"""

import os
import logging
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger("hermes.obsidian")

# ─── Config ───────────────────────────────────────────────────────────────────

def _get_base_url() -> str:
    host = os.getenv("OBSIDIAN_HOST", "127.0.0.1").strip()
    port = os.getenv("OBSIDIAN_PORT", "27123").strip()
    return f"https://{host}:{port}"

def _get_api_key() -> Optional[str]:
    val = os.getenv("OBSIDIAN_API_KEY", "").strip()
    return val if val and not val.startswith("your_") else None

def _get_vault_path() -> Optional[str]:
    val = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    return val if val else None

def _headers() -> Dict[str, str]:
    key = _get_api_key()
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h

def _client() -> httpx.AsyncClient:
    """Return an async HTTP client that ignores the self-signed cert."""
    return httpx.AsyncClient(
        verify=False,          # Obsidian Local REST API uses self-signed TLS
        timeout=10.0,
        headers=_headers()
    )

# ─── Status ───────────────────────────────────────────────────────────────────

async def is_reachable() -> bool:
    """Return True if the Obsidian Local REST API plugin is running and reachable."""
    if not _get_api_key():
        return False
    try:
        async with _client() as c:
            r = await c.get(f"{_get_base_url()}/")
            return r.status_code < 500
    except Exception:
        return False

# ─── Vault File Operations ────────────────────────────────────────────────────

async def list_notes(folder: str = "") -> List[str]:
    """
    List all markdown files in the vault (or a specific folder), recursively.
    Returns a list of vault-relative file paths, e.g. ["Daily/2026-06-23.md", "Jarvis/Ideas.md"]
    """
    async def _list_dir(c: httpx.AsyncClient, dir_path: str) -> List[str]:
        """Recursively list .md files under dir_path (vault-relative, no leading slash)."""
        url = f"{_get_base_url()}/vault/"
        if dir_path:
            url += dir_path.rstrip("/") + "/"
        try:
            r = await c.get(url)
            if r.status_code != 200:
                return []
            entries = r.json().get("files", [])
        except Exception as e:
            logger.warning(f"Obsidian _list_dir('{dir_path}') failed: {e}")
            return []

        results: List[str] = []
        for entry in entries:
            if entry.endswith("/"):
                # It's a subdirectory — recurse
                sub = (dir_path + "/" + entry.rstrip("/")).lstrip("/")
                results.extend(await _list_dir(c, sub))
            elif entry.endswith(".md"):
                prefix = (dir_path + "/").lstrip("/") if dir_path else ""
                results.append(prefix + entry)
        return results

    try:
        async with _client() as c:
            return await _list_dir(c, folder)
    except Exception as e:
        logger.warning(f"Obsidian list_notes failed: {e}")
    return []



async def read_note(note_path: str) -> Optional[str]:
    """
    Read the raw markdown content of a note by its vault-relative path.
    e.g. read_note("Daily/2026-06-23.md")
    """
    try:
        encoded = note_path.lstrip("/")
        async with _client() as c:
            r = await c.get(f"{_get_base_url()}/vault/{encoded}")
            if r.status_code == 200:
                return r.text
            logger.warning(f"Obsidian read_note '{note_path}' → HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"Obsidian read_note failed: {e}")
    return None


async def create_note(note_path: str, content: str) -> bool:
    """
    Create or overwrite a note in the vault.
    e.g. create_note("Jarvis/Meeting Notes.md", "# Meeting\n...")
    Returns True on success.
    """
    try:
        encoded = note_path.lstrip("/")
        async with httpx.AsyncClient(verify=False, timeout=10.0) as c:
            r = await c.put(
                f"{_get_base_url()}/vault/{encoded}",
                content=content.encode("utf-8"),
                headers={**_headers(), "Content-Type": "text/markdown"},
            )
            if r.status_code in (200, 204):
                logger.info(f"Obsidian note created/updated: {note_path}")
                return True
            logger.warning(f"Obsidian create_note '{note_path}' → HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Obsidian create_note failed: {e}")
    return False


async def delete_note(note_path: str) -> bool:
    """
    Delete a note in the vault by its vault-relative path.
    e.g. delete_note("Daily/2026-06-23.md")
    Returns True on success.
    """
    try:
        encoded = note_path.lstrip("/")
        async with _client() as c:
            r = await c.delete(f"{_get_base_url()}/vault/{encoded}")
            if r.status_code in (200, 204, 404):
                logger.info(f"Obsidian note deleted: {note_path}")
                return True
            logger.warning(f"Obsidian delete_note '{note_path}' → HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Obsidian delete_note failed: {e}")
    return False


async def search_notes(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Full-text search across the vault using the plugin's built-in search.
    Returns a list of {filename, score, content_excerpt} dicts.
    """
    try:
        async with _client() as c:
            r = await c.post(
                f"{_get_base_url()}/search/simple/",
                params={"query": query, "contextLength": 300},
            )
            if r.status_code == 200:
                results = r.json()
                output = []
                for item in results[:limit]:
                    filename = item.get("filename", "")
                    matches = item.get("matches", [])
                    excerpt = ""
                    if matches:
                        excerpt = matches[0].get("context", "")
                    output.append({
                        "filename": filename,
                        "score": item.get("score", 0),
                        "excerpt": excerpt,
                    })
                return output
    except Exception as e:
        logger.warning(f"Obsidian search failed: {e}")
    return []

# ─── Vault → Qdrant RAG Sync ──────────────────────────────────────────────────

async def sync_vault_to_rag(max_notes: int = 500) -> Dict[str, Any]:
    """
    Index the entire Obsidian vault into Qdrant for semantic (RAG) search.
    Reads every .md file and upserts it as a document with source="obsidian".
    Returns a summary dict: {indexed, skipped, errors}.
    """
    from backend.rag import index_document

    notes = await list_notes()
    if not notes:
        return {"indexed": 0, "skipped": 0, "errors": 0,
                "message": "No notes found or Obsidian is not reachable."}

    indexed = 0
    skipped = 0
    errors = 0

    for note_path in notes[:max_notes]:
        try:
            content = await read_note(note_path)
            if not content or len(content.strip()) < 10:
                skipped += 1
                continue

            # Use path as stable doc_id (hash it to be safe for Qdrant)
            import hashlib
            doc_id = "obsidian_" + hashlib.sha1(note_path.encode()).hexdigest()

            # Title = filename without extension
            title = os.path.splitext(os.path.basename(note_path))[0]

            success = index_document(
                doc_id=doc_id,
                title=title,
                text=content,
                source="obsidian",
                note_path=note_path,
            )
            if success:
                indexed += 1
            else:
                errors += 1
        except Exception as e:
            logger.error(f"Error syncing note '{note_path}': {e}")
            errors += 1

    msg = f"Vault sync complete: {indexed} indexed, {skipped} skipped, {errors} errors."
    logger.info(msg)
    return {"indexed": indexed, "skipped": skipped, "errors": errors, "message": msg}
