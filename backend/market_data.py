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
    "sol": "solana", "solana": "solana", "солаon": "solana",
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
        
        # Fast, zero-rate-limit Forex provider for currency pairs (EURUSD, GBPUSD, USDJPY, etc.)
        s_clean = symbol.upper().replace("=X", "").strip()
        currencies = {"EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY", "NOK", "SEK"}
        if len(s_clean) == 6 and s_clean[:3] in currencies and s_clean[3:] in currencies:
            fx_price = await self._fetch_forex(s_clean[:3], s_clean[3:])
            if fx_price is not None:
                return fx_price

        return await self._fetch_yahoo(symbol)

    async def _fetch_forex(self, base: str, quote: str) -> Optional[float]:
        url = f"https://open.er-api.com/v6/latest/{base}"
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    rates = data.get("rates", {})
                    if quote in rates:
                        return float(rates[quote])
        except Exception as exc:
            logger.warning("HttpProvider: Forex API error for %s/%s: %s", base, quote, exc)
        return None

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
        t_clean = ticker.strip().upper()
        tickers_to_try = [ticker]
        if not t_clean.endswith("=X"):
            tickers_to_try.append(f"{t_clean}=X")

        for t in tickers_to_try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
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
                logger.warning("HttpProvider: Yahoo Finance error for %s: %s", t, exc)
        return None


# ---------------------------------------------------------------------------
# Provider 2: CcxtProvider (optional — crypto only)
# ---------------------------------------------------------------------------





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
