"""
Marketplace Skill Lifecycle & Registry Manager (Phases 1 & 2)

Handles persistent skill registry, 1-click installation, uninstallation,
environment variable configuration, and status verification.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.database import _execute

logger = logging.getLogger(__name__)


class MarketplaceSkillManifest(BaseModel):
    id: str
    name: str
    display_name: str
    description: str = ""
    author: str = "community"
    version: str = "1.0.0"
    category: str = "general"
    tools: List[str] = Field(default_factory=list)
    price_type: str = "free"  # free | pay_per_use | subscription
    price_usd: float = 0.0
    is_installed: bool = False
    created_at: Optional[str] = None


class LifecycleManager:
    """Manages skill persistence and lifecycle states in database."""

    @staticmethod
    def list_skills() -> List[Dict[str, Any]]:
        """Return all skills in marketplace registry from database."""
        rows = _execute(
            "SELECT id, name, display_name, description, author, version, category, tools, price_type, price_usd, is_installed, created_at FROM marketplace_skills ORDER BY name ASC"
        )
        skills = []
        for r in rows:
            # Handle tuple or dict row
            if isinstance(r, (list, tuple)):
                s_id, name, display_name, desc, author, ver, cat, tools_raw, price_type, price_usd, is_inst, created_at = r[:12]
            else:
                s_id = r["id"]
                name = r["name"]
                display_name = r["display_name"]
                desc = r.get("description", "")
                author = r.get("author", "community")
                ver = r.get("version", "1.0.0")
                cat = r.get("category", "general")
                tools_raw = r.get("tools", "[]")
                price_type = r.get("price_type", "free")
                price_usd = r.get("price_usd", 0.0)
                is_inst = r.get("is_installed", 0)
                created_at = r.get("created_at")

            tools_list = []
            if tools_raw:
                try:
                    tools_list = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
                except Exception:
                    tools_list = []
            skills.append({
                "id": s_id,
                "name": name,
                "display_name": display_name,
                "description": desc or "",
                "author": author or "community",
                "version": ver or "1.0.0",
                "category": cat or "general",
                "tools": tools_list,
                "price_type": price_type or "free",
                "price_usd": float(price_usd or 0.0),
                "is_installed": bool(is_inst),
                "created_at": str(created_at) if created_at else None
            })
        return skills

    @staticmethod
    def get_skill(skill_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single skill details by ID."""
        rows = _execute(
            "SELECT id, name, display_name, description, author, version, category, tools, price_type, price_usd, is_installed, created_at FROM marketplace_skills WHERE id = ?",
            (skill_id,)
        )
        if not rows:
            return None
        r = rows[0]
        if isinstance(r, (list, tuple)):
            s_id, name, display_name, desc, author, ver, cat, tools_raw, price_type, price_usd, is_inst, created_at = r[:12]
        else:
            s_id = r["id"]
            name = r["name"]
            display_name = r["display_name"]
            desc = r.get("description", "")
            author = r.get("author", "community")
            ver = r.get("version", "1.0.0")
            cat = r.get("category", "general")
            tools_raw = r.get("tools", "[]")
            price_type = r.get("price_type", "free")
            price_usd = r.get("price_usd", 0.0)
            is_inst = r.get("is_installed", 0)
            created_at = r.get("created_at")

        tools_list = []
        if tools_raw:
            try:
                tools_list = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
            except Exception:
                tools_list = []
        return {
            "id": s_id,
            "name": name,
            "display_name": display_name,
            "description": desc or "",
            "author": author or "community",
            "version": ver or "1.0.0",
            "category": cat or "general",
            "tools": tools_list,
            "price_type": price_type or "free",
            "price_usd": float(price_usd or 0.0),
            "is_installed": bool(is_inst),
            "created_at": str(created_at) if created_at else None
        }

    @staticmethod
    def upsert_skill(manifest: MarketplaceSkillManifest) -> Dict[str, Any]:
        """Insert or update a skill in marketplace DB."""
        tools_json = json.dumps(manifest.tools)
        _execute("""
            INSERT INTO marketplace_skills (id, name, display_name, description, author, version, category, tools, price_type, price_usd, is_installed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                display_name = excluded.display_name,
                description = excluded.description,
                author = excluded.author,
                version = excluded.version,
                category = excluded.category,
                tools = excluded.tools,
                price_type = excluded.price_type,
                price_usd = excluded.price_usd
        """, (
            manifest.id, manifest.name, manifest.display_name, manifest.description,
            manifest.author, manifest.version, manifest.category, tools_json,
            manifest.price_type, manifest.price_usd, 1 if manifest.is_installed else 0
        ))
        return LifecycleManager.get_skill(manifest.id) or {}

    @staticmethod
    def install_skill(skill_id: str) -> Dict[str, Any]:
        """Mark skill as installed and create installation record."""
        _execute("UPDATE marketplace_skills SET is_installed = 1 WHERE id = ?", (skill_id,))
        _execute("""
            INSERT INTO marketplace_installations (id, skill_id, status)
            VALUES (?, ?, 'active')
            ON CONFLICT(id) DO UPDATE SET status = 'active', installed_at = CURRENT_TIMESTAMP
        """, (skill_id, skill_id))
        logger.info(f"Skill '{skill_id}' successfully installed.")
        return LifecycleManager.get_skill(skill_id) or {"id": skill_id, "is_installed": True}

    @staticmethod
    def uninstall_skill(skill_id: str) -> Dict[str, Any]:
        """Uninstall skill and remove active status."""
        _execute("UPDATE marketplace_skills SET is_installed = 0 WHERE id = ?", (skill_id,))
        _execute("UPDATE marketplace_installations SET status = 'uninstalled' WHERE id = ?", (skill_id,))
        logger.info(f"Skill '{skill_id}' uninstalled.")
        return LifecycleManager.get_skill(skill_id) or {"id": skill_id, "is_installed": False}

    @staticmethod
    def save_skill_config(skill_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Save skill configuration (e.g. API keys / environment settings)."""
        config_str = json.dumps(config)
        _execute("""
            UPDATE marketplace_installations SET config_json = ? WHERE id = ?
        """, (config_str, skill_id))
        return {"status": "success", "skill_id": skill_id, "config": config}

    @staticmethod
    def get_skill_for_tool(tool_name: str) -> Optional[str]:
        """Finds which skill ID provides a given tool name."""
        skills = LifecycleManager.list_skills()
        for s in skills:
            if tool_name in s.get("tools", []):
                return s["id"]
        return None
