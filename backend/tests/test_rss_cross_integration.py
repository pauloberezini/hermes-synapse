import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import active_sessions
from backend.tools import execute_tool
from backend.database import (
    db_get_rss_node,
    db_get_all_rss_nodes,
    db_get_rss_items,
    db_delete_rss_node,
    save_subagent,
    get_subagent
)
from backend.rss_service import (
    fetch_single_rss_feed,
    fetch_and_save_node_rss,
    fetch_all_active_rss_nodes,
    get_rss_node_output
)


@pytest.fixture
def auth_client():
    c = TestClient(app)
    c.headers = {"Authorization": "Bearer test-cross-token"}
    active_sessions.add("test-cross-token")
    return c


MOCK_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Tech News Feed</title>
    <link>https://example.com/rss</link>
    <item>
      <title>Python 3.14 Alpha Released with Performance Boost</title>
      <link>https://example.com/python-314</link>
      <description>Python 3.14 introduces JIT compiler enhancements and zero-cost exception handling.</description>
      <guid>guid_py_314</guid>
      <pubDate>Sat, 08 Aug 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Artificial Intelligence Models Reach New Benchmark</title>
      <link>https://example.com/ai-benchmark</link>
      <description>New multi-agent AI framework beats existing benchmarks on autonomous code generation.</description>
      <guid>guid_ai_model</guid>
      <pubDate>Sat, 08 Aug 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Cryptocurrency Market Overview 2026</title>
      <link>https://example.com/crypto-market</link>
      <description>Analysis of decentralised finance and web3 protocols.</description>
      <guid>guid_crypto_2026</guid>
      <pubDate>Fri, 07 Aug 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def test_cross_rss_full_workflow(auth_client):
    """
    Cross-Component Integration Test 1:
    Tests RSS Node creation via REST API -> Feed parsing & DB insertion ->
    Ray connection to Agent -> Tool execution (`read_rss_node_feed`) -> Result verification.
    """
    node_id = "cross_rss_node_1"
    agent_id = "cross_agent_worker_1"

    # 1. Create a Worker Subagent in the database
    save_subagent(
        id=agent_id,
        name="Tech Research Agent",
        system_prompt="You summarize tech news.",
        model="google/gemini-2.5-flash"
    )
    assert get_subagent(agent_id) is not None

    # 2. Create RSS Node via REST API
    resp = auth_client.post("/api/rss/nodes", json={
        "id": node_id,
        "name": "Tech News Feed Node",
        "feed_urls": "https://example.com/rss.xml",
        "fetch_interval_minutes": 10,
        "output_limit": 5,
        "date_filter_days": 0,
        "keywords_filter": "",
        "is_active": 1,
        "connected_agents": agent_id
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # 3. Mock urllib network fetch and trigger manual RSS sync via REST API
    mock_resp = MagicMock()
    mock_resp.read.return_value = MOCK_RSS_XML.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        sync_resp = auth_client.post(f"/api/rss/nodes/{node_id}/fetch")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["status"] == "success"
        assert sync_data["total_parsed"] == 3
        assert sync_data["inserted"] == 3

    # 4. Verify articles were stored in database table `rss_feed_items`
    items_resp = auth_client.get(f"/api/rss/nodes/{node_id}/items")
    assert items_resp.status_code == 200
    items_data = items_resp.json()
    assert items_data["count"] == 3

    # 5. Execute Agent Tool Call `read_rss_node_feed` with limit 2 (Cross-component integration)
    tool_output_limited = execute_tool("read_rss_node_feed", {"node_id": node_id, "limit": 2})
    assert "RSS Нода: Tech News Feed Node" in tool_output_limited
    assert "Всего публикаций отдано: 2" in tool_output_limited
    assert "Artificial Intelligence Models" in tool_output_limited

    # Execute Agent Tool Call without limit parameter (returns all 3 items)
    tool_output_all = execute_tool("read_rss_node_feed", {"node_id": node_id})
    assert "Всего публикаций отдано: 3" in tool_output_all
    assert "Python 3.14 Alpha Released" in tool_output_all

    # 6. Test Output Filtering dynamically: Update RSS Node with keywords_filter="Python"
    update_resp = auth_client.put(f"/api/rss/nodes/{node_id}", json={
        "keywords_filter": "Python",
        "output_limit": 1
    })
    assert update_resp.status_code == 200

    # Call agent tool again and verify keyword filtering
    filtered_tool_output = execute_tool("read_rss_node_feed", {"node_id": node_id})
    assert "Python 3.14 Alpha Released" in filtered_tool_output
    assert "Cryptocurrency Market" not in filtered_tool_output

    # 7. Cleanup
    auth_client.delete(f"/api/rss/nodes/{node_id}")
    assert db_get_rss_node(node_id) is None


def test_cross_rss_deduplication_and_polling(auth_client):
    """
    Cross-Component Integration Test 2:
    Tests background polling loop, item deduplication across multiple sync passes,
    position updates, and cascading deletion.
    """
    node_id = "cross_rss_node_dedup"

    # Create node
    auth_client.post("/api/rss/nodes", json={
        "id": node_id,
        "name": "Dedup Test Node",
        "feed_urls": "https://example.com/rss.xml",
        "is_active": 1
    })

    mock_resp = MagicMock()
    mock_resp.read.return_value = MOCK_RSS_XML.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        # First sync pass: 3 items inserted
        res1 = fetch_and_save_node_rss(node_id)
        assert res1["inserted"] == 3

        # Second sync pass with same feed items: 0 new items inserted (deduplicated)
        res2 = fetch_and_save_node_rss(node_id)
        assert res2["inserted"] == 0

        # Run all active nodes poller helper
        poller_results = fetch_all_active_rss_nodes()
        assert any(r.get("node_id") == node_id for r in poller_results)

    # Test batch position update endpoint for canvas
    pos_resp = auth_client.post("/api/rss/nodes/positions", json={
        "positions": [{"id": node_id, "x": 550, "y": 450}]
    })
    assert pos_resp.status_code == 200
    node = db_get_rss_node(node_id)
    assert node["x"] == 550
    assert node["y"] == 450

    # Test cascading deletion of items and node
    auth_client.delete(f"/api/rss/nodes/{node_id}")
    assert db_get_rss_node(node_id) is None
    assert len(db_get_rss_items(node_id)) == 0


if __name__ == "__main__":
    print("Running test_cross_rss_full_workflow()...")
    c = TestClient(app)
    c.headers = {"Authorization": "Bearer test-cross-token"}
    active_sessions.add("test-cross-token")
    test_cross_rss_full_workflow(c)
    print("Running test_cross_rss_deduplication_and_polling()...")
    test_cross_rss_deduplication_and_polling(c)
    print("Cross integration tests completed successfully!")
