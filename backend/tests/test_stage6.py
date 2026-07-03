import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend import tools
from backend.price_monitor import price_monitor

@pytest.fixture(autouse=True)
def mock_external_apis():
    # Make sure we don't fetch real keys from env which might trigger real calls
    with patch("backend.tools._env", return_value=None), \
         patch("httpx.AsyncClient") as mock_class:
         
        client_inst = AsyncMock()
        mock_class.return_value.__aenter__.return_value = client_inst
        
        def mock_get(url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            
            # 1. DuckDuckGo Search
            if "duckduckgo.com" in url:
                mock_resp.text = """
                <div class="result">
                    <a class="result__a" href="http://example.com/winner">Кто выиграл матч</a>
                    <a class="result__snippet">Вчерашний матч выиграла команда А со счетом 3:1.</a>
                </div>
                """
            # 2. CoinGecko Price
            elif "coingecko.com" in url:
                if "bitcoin" in url:
                    mock_resp.json.return_value = {"bitcoin": {"usd": 65000.0}}
                elif "the-open-network" in url:
                    mock_resp.json.return_value = {"the-open-network": {"usd": 7.2}}
                else:
                    mock_resp.json.return_value = {}
            # 3. GitHub API
            elif "api.github.com" in url:
                if "pulls" in url:
                    mock_resp.json.return_value = [
                        {"number": 42, "title": "Test PR", "user": {"login": "test_user"}, "html_url": "http://github.com/pr/42"}
                    ]
                elif "issues" in url:
                    mock_resp.json.return_value = [
                        {"number": 10, "title": "Test Issue", "state": "open", "html_url": "http://github.com/issue/10"}
                    ]
                elif "releases" in url:
                    mock_resp.json.return_value = [
                        {"name": "v1.0.0", "tag_name": "v1.0.0", "published_at": "2026-07-03T12:00:00Z"}
                    ]
                else:
                    mock_resp.json.return_value = []
            # 4. RSS Feed
            elif "habr.com" in url:
                mock_resp.text = """<?xml version="1.0" encoding="UTF-8" ?>
                <rss version="2.0">
                <channel>
                    <title>Habr News</title>
                    <link>https://habr.com</link>
                    <item>
                        <title>Тестовая новость Habr</title>
                        <description>Описание тестовой новости</description>
                        <link>https://habr.com/post/1</link>
                    </item>
                </channel>
                </rss>"""
            else:
                mock_resp.text = ""
                mock_resp.json.return_value = {}
                
            return mock_resp
            
        client_inst.get.side_effect = mock_get
        yield client_inst

def test_web_search_ddg_mock():
    # Verify web_search works and returns a string
    res_str = tools.execute_tool("web_search", {"query": "Кто выиграл матч вчера?"})
    assert isinstance(res_str, str)
    assert len(res_str) > 0
    assert "Кто выиграл матч" in res_str

def test_add_price_alert():
    # Verify adding a price alert
    res_str = tools.execute_tool("add_price_alert", {"symbol": "TON", "target_price": 6.5, "condition": "above"})
    data = json.loads(res_str)
    assert data["status"] == "success"
    assert "Оповещение установлено" in data["message"]
    assert data["alert"]["symbol"] == "the-open-network"
    assert data["alert"]["target_price"] == 6.5
    assert data["alert"]["condition"] == "above"
    
    # Cancel alert to cleanup
    alert_id = data["alert"]["id"]
    price_monitor.cancel_alert(alert_id)

def test_get_market_prices():
    # Verify market prices are queried
    res_str = tools.execute_tool("get_market_prices", {"symbols": "BTC, TON"})
    data = json.loads(res_str)
    assert "BTC" in data
    assert "TON" in data
    assert data["BTC"] == 65000.0
    assert data["TON"] == 7.2

def test_get_github_summary():
    # Verify github summary returns a result
    res_str = tools.execute_tool("get_github_summary", {"repo_name": "pauloberezini/jarvis", "request_type": "all"})
    assert isinstance(res_str, str)
    assert len(res_str) > 0
    assert "Test PR" in res_str
    assert "Test Issue" in res_str
    assert "v1.0.0" in res_str

def test_get_rss_digest():
    # Verify rss digest works
    res_str = tools.execute_tool("get_rss_digest", {"feed_source": "habr", "limit": 2})
    assert isinstance(res_str, str)
    assert len(res_str) > 0
    assert "Тестовая новость Habr" in res_str
