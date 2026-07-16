"""
market_data.py — Pluggable Market Data Provider for Hermes Synapse
==================================================================

OSS-first design:
  • Default 'HttpProvider' uses CoinGecko (crypto) + Yahoo Finance (stocks)
    over plain HTTPS — zero dependencies, zero API keys.
  • 'CcxtProvider' is an optional swap-in for real-time crypto data via
    any CCXT-supported exchange. Requires: uv sync --group market-ccxt
  • 'AlpacaProvider' is an optional swap-in for US equities. Requires an
    Alpaca paper-trading account and: uv sync --group market-alpaca

Usage
-----
Set MARKET_DATA_PROVIDER in .env:
  http    → HttpProvider (default, always works)
  ccxt    → CcxtProvider (crypto only; falls back to HttpProvider for stocks)
  alpaca  → AlpacaProvider (stocks only; falls back to HttpProvider for crypto)
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger("hermes.market_data")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    )
}

# ---------------------------------------------------------------------------
# Crypto symbol normalisation map (shared with price_monitor / tools)
# ---------------------------------------------------------------------------

CRYPTO_MAP: dict[str, str] = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "биткоин": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "эфир": "ethereum", "эфириум": "ethereum",
    "bnb": "binancecoin",
    "sol": "solana", "solana": "solana", "солана": "solana",
    "xrp": "ripple", "ripple": "ripple", "рипл": "ripple",
    "ton": "the-open-network", "тон": "the-open-network",
}


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class MarketDataProvider(ABC):
    """Base interface for all market data backends.

    Implementations must be safe to call concurrently from asyncio tasks.
    They should never raise — return None on transient failures so callers
    can decide how to handle missing data.
    """

    @abstractmethod
    async def get_price(self, symbol: str, is_crypto: bool) -> Optional[float]:
        """Fetch the current USD price for *symbol*.

        Args:
            symbol:    For crypto — CoinGecko coin ID (e.g. 'bitcoin').
                       For stocks — ticker string (e.g. 'AAPL').
            is_crypto: True when symbol is a cryptocurrency.

        Returns:
            Current price in USD, or None if unavailable.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (used in logs)."""
        ...


# ---------------------------------------------------------------------------
# Provider 1: HttpProvider (default — zero config, zero extra packages)
# ---------------------------------------------------------------------------

class HttpProvider(MarketDataProvider):
    """OSS default implementation.

    Crypto  → CoinGecko public REST API (no API key, rate-limited at ~30 rpm).
    Stocks  → Yahoo Finance chart API   (no API key).

    This provider is always available and requires no installation beyond
    the core ``httpx`` dependency already present in the project.
    """

    def name(self) -> str:
        return "HttpProvider (CoinGecko + Yahoo Finance)"

    async def get_price(self, symbol: str, is_crypto: bool) -> Optional[float]:
        if is_crypto:
            return await self._fetch_coingecko(symbol)
        return await self._fetch_yahoo(symbol)

    async def _fetch_coingecko(self, coin_id: str) -> Optional[float]:
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin_id}&vs_currencies=usd"
        )
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    if coin_id in data:
                        return float(data[coin_id]["usd"])
        except Exception as exc:
            logger.warning("HttpProvider: CoinGecko error for %s: %s", coin_id, exc)
        return None

    async def _fetch_yahoo(self, ticker: str) -> Optional[float]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    meta = (
                        data.get("chart", {})
                        .get("result", [{}])[0]
                        .get("meta", {})
                    )
                    price = meta.get("regularMarketPrice")
                    if price is not None:
                        return float(price)
        except Exception as exc:
            logger.warning("HttpProvider: Yahoo Finance error for %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Provider 2: CcxtProvider (optional — crypto only)
# ---------------------------------------------------------------------------

class CcxtProvider(MarketDataProvider):
    """Real-time crypto prices via any CCXT-supported exchange.

    Install: uv sync --group market-ccxt
    Config:  CCXT_EXCHANGE=binance  (default: binance)

    For stock symbols this provider transparently delegates to HttpProvider
    so mixed alert lists (crypto + stocks) keep working out of the box.
    """

    def __init__(self) -> None:
        try:
            import ccxt  # noqa: F401 — intentional lazy import
            exchange_id = os.getenv("CCXT_EXCHANGE", "binance")
            exchange_cls = getattr(ccxt, exchange_id, None)
            if exchange_cls is None:
                raise ValueError(f"Unknown CCXT exchange: {exchange_id!r}")
            self._exchange = exchange_cls({"enableRateLimit": True})
            self._http_fallback = HttpProvider()
            logger.info("CcxtProvider initialised (exchange=%s)", exchange_id)
        except ImportError:
            raise RuntimeError(
                "ccxt is not installed. Run: uv sync --group market-ccxt"
            )

    def name(self) -> str:
        return f"CcxtProvider ({os.getenv('CCXT_EXCHANGE', 'binance')})"

    async def get_price(self, symbol: str, is_crypto: bool) -> Optional[float]:
        if not is_crypto:
            # Delegate stocks to the zero-config HTTP fallback
            return await self._http_fallback.get_price(symbol, is_crypto=False)
        return await self._fetch_ccxt(symbol)

    async def _fetch_ccxt(self, coin_id: str) -> Optional[float]:
        """Map CoinGecko coin_id to CCXT trading pair and fetch ticker."""
        _COINGECKO_TO_BASE: dict[str, str] = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "binancecoin": "BNB",
            "solana": "SOL",
            "ripple": "XRP",
            "the-open-network": "TON",
        }
        base = _COINGECKO_TO_BASE.get(coin_id, coin_id.upper())
        quote = os.getenv("CCXT_QUOTE", "USDT")
        pair = f"{base}/{quote}"
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(
                None, self._exchange.fetch_ticker, pair
            )
            last = ticker.get("last")
            if last is not None:
                return float(last)
        except Exception as exc:
            logger.warning("CcxtProvider: error for %s: %s", pair, exc)
        return None


# ---------------------------------------------------------------------------
# Provider 3: AlpacaProvider (optional — stocks only)
# ---------------------------------------------------------------------------

class AlpacaProvider(MarketDataProvider):
    """Real-time US equity prices via the Alpaca Market Data API.

    Install:  uv sync --group market-alpaca
    Config:   ALPACA_API_KEY, ALPACA_API_SECRET
              ALPACA_BASE_URL (default: https://data.alpaca.markets)

    Paper-trading credentials from https://alpaca.markets work for data.
    For crypto symbols this provider delegates to HttpProvider.
    """

    def __init__(self) -> None:
        try:
            from alpaca.data import StockHistoricalDataClient  # noqa: F401
            from alpaca.data.requests import StockLatestTradeRequest  # noqa: F401
            api_key = os.getenv("ALPACA_API_KEY")
            api_secret = os.getenv("ALPACA_API_SECRET")
            if not api_key or not api_secret:
                raise RuntimeError(
                    "ALPACA_API_KEY and ALPACA_API_SECRET must be set "
                    "when MARKET_DATA_PROVIDER=alpaca"
                )
            self._client = StockHistoricalDataClient(api_key, api_secret)
            self._http_fallback = HttpProvider()
            logger.info("AlpacaProvider initialised")
        except ImportError:
            raise RuntimeError(
                "alpaca-py is not installed. Run: uv sync --group market-alpaca"
            )

    def name(self) -> str:
        return "AlpacaProvider (alpaca-py)"

    async def get_price(self, symbol: str, is_crypto: bool) -> Optional[float]:
        if is_crypto:
            return await self._http_fallback.get_price(symbol, is_crypto=True)
        return await self._fetch_alpaca(symbol)

    async def _fetch_alpaca(self, ticker: str) -> Optional[float]:
        from alpaca.data.requests import StockLatestTradeRequest
        import asyncio
        try:
            req = StockLatestTradeRequest(symbol_or_symbols=ticker.upper())
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_stock_latest_trade, req
            )
            trade = result.get(ticker.upper())
            if trade is not None:
                return float(trade.price)
        except Exception as exc:
            logger.warning("AlpacaProvider: error for %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Factory — driven by MARKET_DATA_PROVIDER env var
# ---------------------------------------------------------------------------

def get_provider() -> MarketDataProvider:
    """Return the configured MarketDataProvider.

    Reads MARKET_DATA_PROVIDER from the environment. Falls back to
    HttpProvider on any error so the system is always operational.

    Valid values: 'http' (default), 'ccxt', 'alpaca'
    """
    provider_name = os.getenv("MARKET_DATA_PROVIDER", "http").strip().lower()

    if provider_name == "ccxt":
        try:
            p = CcxtProvider()
            logger.info("Market data: using %s", p.name())
            return p
        except Exception as exc:
            logger.warning(
                "CcxtProvider unavailable (%s); falling back to HttpProvider.", exc
            )
    elif provider_name == "alpaca":
        try:
            p = AlpacaProvider()
            logger.info("Market data: using %s", p.name())
            return p
        except Exception as exc:
            logger.warning(
                "AlpacaProvider unavailable (%s); falling back to HttpProvider.", exc
            )
    elif provider_name not in ("http", ""):
        logger.warning(
            "Unknown MARKET_DATA_PROVIDER=%r; using HttpProvider.", provider_name
        )

    p = HttpProvider()
    logger.info("Market data: using %s", p.name())
    return p
