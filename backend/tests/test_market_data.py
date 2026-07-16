"""
Tests for the pluggable MarketDataProvider (backend/market_data.py).

All HTTP calls are mocked — no network needed.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.market_data import (
    HttpProvider,
    MarketDataProvider,
    get_provider,
)


# ---------------------------------------------------------------------------
# HttpProvider tests
# ---------------------------------------------------------------------------

class TestHttpProvider:
    """Tests for the default zero-config HTTP provider."""

    @pytest.mark.asyncio
    async def test_get_price_crypto_returns_float(self):
        provider = HttpProvider()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bitcoin": {"usd": 65432.10}}

        with patch("backend.market_data.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            price = await provider.get_price("bitcoin", is_crypto=True)

        assert price == pytest.approx(65432.10)

    @pytest.mark.asyncio
    async def test_get_price_stock_returns_float(self):
        provider = HttpProvider()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "chart": {
                "result": [{"meta": {"regularMarketPrice": 189.5}}]
            }
        }

        with patch("backend.market_data.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            price = await provider.get_price("AAPL", is_crypto=False)

        assert price == pytest.approx(189.5)

    @pytest.mark.asyncio
    async def test_get_price_returns_none_on_http_error(self):
        provider = HttpProvider()

        with patch("backend.market_data.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            price = await provider.get_price("bitcoin", is_crypto=True)

        assert price is None

    @pytest.mark.asyncio
    async def test_get_price_returns_none_on_404(self):
        provider = HttpProvider()
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("backend.market_data.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            price = await provider.get_price("INVALID", is_crypto=False)

        assert price is None

    def test_name_returns_string(self):
        assert isinstance(HttpProvider().name(), str)


# ---------------------------------------------------------------------------
# get_provider factory tests
# ---------------------------------------------------------------------------

class TestGetProviderFactory:
    """Tests for the get_provider() factory function."""

    def test_default_returns_http_provider(self, monkeypatch):
        monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
        provider = get_provider()
        assert isinstance(provider, HttpProvider)

    def test_http_explicit_returns_http_provider(self, monkeypatch):
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "http")
        provider = get_provider()
        assert isinstance(provider, HttpProvider)

    def test_unknown_value_falls_back_to_http(self, monkeypatch):
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "nonexistent_provider")
        provider = get_provider()
        assert isinstance(provider, HttpProvider)

    def test_ccxt_falls_back_to_http_when_not_installed(self, monkeypatch):
        """When ccxt package is absent the factory must fall back gracefully."""
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "ccxt")
        with patch("backend.market_data.CcxtProvider.__init__",
                   side_effect=RuntimeError("ccxt not installed")):
            provider = get_provider()
        assert isinstance(provider, HttpProvider)

    def test_alpaca_falls_back_to_http_when_not_installed(self, monkeypatch):
        """When alpaca-py is absent the factory must fall back gracefully."""
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "alpaca")
        with patch("backend.market_data.AlpacaProvider.__init__",
                   side_effect=RuntimeError("alpaca-py not installed")):
            provider = get_provider()
        assert isinstance(provider, HttpProvider)


# ---------------------------------------------------------------------------
# ABC compliance test
# ---------------------------------------------------------------------------

def test_http_provider_is_market_data_provider():
    assert issubclass(HttpProvider, MarketDataProvider)
