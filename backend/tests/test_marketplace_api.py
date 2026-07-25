"""
Unit tests for Stage 14 Community Skills Marketplace API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import create_session

client = TestClient(app)


def test_marketplace_skills_api_and_register():
    token = create_session()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch marketplace skills
    r = client.get("/api/marketplace/skills", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert isinstance(data["skills"], list)

    # 2. Register a new custom community skill
    payload = {
        "name": "custom_github_plugin",
        "display_name": "Custom GitHub Plugin",
        "description": "Community skill for GitHub automation",
        "tools": ["list_issues", "create_pr"],
        "author": "community_dev"
    }
    reg_r = client.post("/api/marketplace/register", json=payload, headers=headers)
    assert reg_r.status_code == 200
    reg_data = reg_r.json()
    assert reg_data["status"] == "success"
    assert reg_data["skill"]["name"] == "custom_github_plugin"

    # 3. Verify it is now returned in marketplace listing
    r_updated = client.get("/api/marketplace/skills", headers=headers)
    assert r_updated.status_code == 200
    updated_skills = r_updated.json()["skills"]
    assert any(s["name"] == "custom_github_plugin" for s in updated_skills)
