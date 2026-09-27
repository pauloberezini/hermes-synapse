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
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger("hermes.market_data")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

_LAST_LOGGED_ERRORS: dict[str, float] = {}


def _log_throttled_warning(key: str, msg: str, *args, throttle_sec: float = 300.0) -> None:
    now = time.time()
    last = _LAST_LOGGED_ERRORS.get(key, 0.0)
    if now - last >= throttle_sec:
        _LAST_LOGGED_ERRORS[key] = now
        logger.warning(msg, *args)
    else:
        logger.debug(msg, *args)


def _is_network_or_timeout_error(exc: BaseException) -> bool:
    """Detects network outages, DNS errors, or request timeouts across httpx and stdlib."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, TimeoutError, OSError)):
        return True
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()
    return (
        any(k in exc_type for k in ("Timeout", "Network", "Connect", "Resolution"))
        or any(k in exc_str for k in (
            "timeout",
            "name or service not known",
            "no address associated with hostname",
            "connection refused",
            "connection reset",
            "gaierror",
            "all connection attempts failed",
        ))
    )

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

    def __init__(self) -> None:
        self._last_network_outage_time: float = 0.0

    def name(self) -> str:
        return "HttpProvider (CoinGecko + Yahoo Finance)"

    async def get_price(self, symbol: str, is_crypto: bool) -> Optional[float]:
        # Fast circuit-breaker: if a recent network outage / DNS failure occurred (< 10s ago),
        # skip remote HTTP queries to prevent latency cascades and repetitive connection warnings.
        if (time.time() - getattr(self, "_last_network_outage_time", 0.0)) < 10.0:
            return None

        if is_crypto:
            return await self._fetch_coingecko(symbol)
        
        # Fast, zero-rate-limit Forex provider for currency pairs (EURUSD, GBPUSD, USDJPY, etc.)
        s_clean = symbol.upper().replace("=X", "").strip()
        currencies = {"EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY", "NOK", "SEK"}
        if len(s_clean) == 6 and s_clean[:3] in currencies and s_clean[3:] in currencies:
            fx_price = await self._fetch_forex(s_clean[:3], s_clean[3:])
            if fx_price is not None:
                return fx_price
            if time.time() - getattr(self, "_last_network_outage_time", 0.0) < 5.0:
                return None

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
            err_desc = f"{type(exc).__name__}: {exc}".rstrip(": ") if exc else type(exc).__name__
            _log_throttled_warning(f"forex:{base}:{quote}", "HttpProvider: Forex API error for %s/%s: %s", base, quote, err_desc)
            if _is_network_or_timeout_error(exc):
                self._last_network_outage_time = time.time()
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
            err_desc = f"{type(exc).__name__}: {exc}".rstrip(": ") if exc else type(exc).__name__
            _log_throttled_warning(f"coingecko:{coin_id}", "HttpProvider: CoinGecko error for %s: %s", coin_id, err_desc)
            if _is_network_or_timeout_error(exc):
                self._last_network_outage_time = time.time()
        return None

    async def _fetch_yahoo(self, ticker: str) -> Optional[float]:
        t_clean = ticker.strip().upper()
        
        YAHOO_MAP = {
            "XAUUSD": "GC=F",
            "GOLD": "GC=F",
            "BRENT": "BZ=F",
            "WTI": "CL=F",
            "US500": "^GSPC",
            "SPX": "^GSPC",
            "NDX": "^NDX",
            "US100": "^NDX",
            "DOW": "^DJI",
            "US30": "^DJI"
        }
        
        if t_clean in YAHOO_MAP:
            tickers_to_try = [YAHOO_MAP[t_clean]]
        else:
            tickers_to_try = [t_clean]
            if not t_clean.endswith("=X") and not t_clean.startswith("^") and "=" not in t_clean:
                tickers_to_try.append(f"{t_clean}=X")

        for t in tickers_to_try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{t}"
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
                err_desc = f"{type(exc).__name__}: {exc}".rstrip(": ") if exc else type(exc).__name__
                _log_throttled_warning(f"yahoo:{t}", "HttpProvider: Yahoo Finance error for %s: %s", t, err_desc)
                if _is_network_or_timeout_error(exc):
                    self._last_network_outage_time = time.time()
                    break
        return None


# ---------------------------------------------------------------------------
# Provider 2: CcxtProvider (optional — crypto only)
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Factory — driven by MARKET_DATA_PROVIDER env var
# ---------------------------------------------------------------------------

def get_provider() -> MarketDataProvider:
    """Return the configured MarketDataProvider.

    Reads MARKET_DATA_PROVIDER from the environment. ``http`` is built in;
    any other value is offered to installed plugins via the
    ``market_data_provider(name)`` hook. Falls back to HttpProvider on any
    error so the system is always operational.
    """
    provider_name = os.getenv("MARKET_DATA_PROVIDER", "http").strip().lower()

    if provider_name not in ("http", ""):
        try:
            from backend.plugins import hook
            p = hook("market_data_provider", provider_name)
            if p is not None:
                logger.info("Market data: using %s", p.name())
                return p
            logger.warning(
                "No plugin provides MARKET_DATA_PROVIDER=%r; using HttpProvider.", provider_name
            )
        except Exception as exc:
            logger.warning(
                "Provider %r unavailable (%s); falling back to HttpProvider.", provider_name, exc
            )

    p = HttpProvider()
    logger.info("Market data: using %s", p.name())
    return p

