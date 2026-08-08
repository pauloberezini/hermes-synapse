try:
    import pytest
except ImportError:
    pytest = None
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import (
    db_create_rss_node,
    db_get_all_rss_nodes,
    db_get_rss_node,
    db_update_rss_node,
    db_delete_rss_node,
    db_save_rss_items,
    db_get_rss_items
)
from backend.rss_service import (
    fetch_single_rss_feed,
    get_rss_node_output
)

from backend.auth import active_sessions

@pytest.fixture
def auth_client():
    c = TestClient(app)
    c.headers = {"Authorization": "Bearer test-token"}
    active_sessions.add("test-token")
    return c


def test_rss_node_db_crud():
    node_id = "test_rss_1"
    # 1. Create
    node = db_create_rss_node(
        id=node_id,
        name="Test Habr RSS",
        feed_urls="https://habr.com/ru/rss/news/",
        fetch_interval_minutes=15,
        output_limit=5,
        date_filter_days=0,
        keywords_filter="python",
        is_active=1
    )
    assert node is not None
    assert node["id"] == node_id
    assert node["name"] == "Test Habr RSS"

    # 2. Get all
    all_nodes = db_get_all_rss_nodes()
    assert any(n["id"] == node_id for n in all_nodes)

    # 3. Update
    updated = db_update_rss_node(node_id, name="Updated Habr RSS", output_limit=10)
    assert updated is True
    fetched = db_get_rss_node(node_id)
    assert fetched["name"] == "Updated Habr RSS"
    assert fetched["output_limit"] == 10

    # 4. Save items & filter
    sample_items = [
        {
            "guid": "item_1",
            "title": "Python 3.14 Release Notes",
            "link": "https://habr.com/p/1/",
            "summary": "Everything new in Python 3.14",
            "published_at": "Sat, 08 Aug 2026 12:00:00 GMT"
        },
        {
            "guid": "item_2",
            "title": "JavaScript Ecosystem 2026",
            "link": "https://habr.com/p/2/",
            "summary": "Updates in frontend tools",
            "published_at": "Sat, 08 Aug 2026 11:00:00 GMT"
        }
    ]
    inserted = db_save_rss_items(node_id, sample_items)
    assert inserted == 2

    # Query items with keyword filter 'python'
    items_py = db_get_rss_items(node_id, keywords_filter="python")
    assert len(items_py) == 1
    assert items_py[0]["guid"] == "item_1"

    # 5. Output function
    output = get_rss_node_output(node_id)
    assert output["status"] == "success"
    assert output["count"] == 1  # because keywords_filter='python'

    # 6. Delete
    deleted = db_delete_rss_node(node_id)
    assert deleted is True
    assert db_get_rss_node(node_id) is None


def test_rss_api_endpoints(auth_client):
    node_id = "api_rss_test"
    # Create via API
    resp = auth_client.post("/api/rss/nodes", json={
        "id": node_id,
        "name": "API Test RSS Node",
        "feed_urls": "https://habr.com/ru/rss/news/",
        "output_limit": 5
    })
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "success"

    # List via API
    resp = auth_client.get("/api/rss/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    assert any(n["id"] == node_id for n in nodes)

    # Get items via API
    resp = auth_client.get(f"/api/rss/nodes/{node_id}/items")
    assert resp.status_code == 200
    assert "items" in resp.json()

    # Get output via API
    resp = auth_client.get(f"/api/rss/nodes/{node_id}/output")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Delete via API
    resp = auth_client.delete(f"/api/rss/nodes/{node_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


if __name__ == "__main__":
    print("Running test_rss_node_db_crud()...")
    test_rss_node_db_crud()
    print("Running test_rss_api_endpoints()...")
    test_rss_api_endpoints()
    print("All RSS unit tests passed cleanly!")
