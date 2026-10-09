import os
import re
import sys
import uuid
import random
import logging
import asyncio
import socket
import httpx
import tempfile
import subprocess
import requests
import base64
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger("hermes.subagents")

# ─── Per-agent model helper ──────────────────────────────────────────────────

def get_agent_model(agent_role: str, fallback_model: str) -> str:
    """
    Returns the model configured for a specific agent role.
    Reads from env: AGENT_MODEL_RESEARCH, AGENT_MODEL_CODE, AGENT_MODEL_ANALYST, AGENT_MODEL_PLANNER.
    Falls back to `fallback_model` (the main LLM_MODEL) if the env var is not set.
    """
    env_map = {
        "research": "AGENT_MODEL_RESEARCH",
        "code":     "AGENT_MODEL_CODE",
        "analyst":  "AGENT_MODEL_ANALYST",
        "planner":  "AGENT_MODEL_PLANNER",
    }
    env_key = env_map.get(agent_role.lower())
    if env_key:
        value = os.getenv(env_key, "").strip()
        if value:
            return value
    return fallback_model


async def call_llm(messages: List[Dict[str, str]], api_key: str, model: str, session_id: Optional[str] = None) -> str:
    from backend.governance import BudgetGuard, LLM_CALL_ESTIMATE_USD, budget_session
    BudgetGuard.check(session_id or budget_session.get(), LLM_CALL_ESTIMATE_USD)

    api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    from backend.llm_model_manager import resolve_provider_model
    model = resolve_provider_model(model, api_base) or model
    is_openmodel = "openmodel.ai" in api_base
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pauloberezini/jarvis",
        "X-Title": "Jarvis Personal Assistant"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }
    
    url = f"{api_base}/messages" if is_openmodel else f"{api_base}/chat/completions"
    
    if is_openmodel:
        from backend.agent import translate_to_anthropic_payload
        actual_payload = translate_to_anthropic_payload(payload)
    else:
        actual_payload = payload
        
    fallback_candidates = []
    for m in [
        os.getenv("LLM_FALLBACK_MODEL"),
        os.getenv("LLM_MODEL"),
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-chat",
    ]:
        m = resolve_provider_model(m, api_base) if m else m
        if m and m.strip() and m not in fallback_candidates:
            fallback_candidates.append(m)

    from backend.llm_model_manager import prioritize_healthy_models, mark_model_rate_limited, is_model_rate_limited
    fallback_candidates = prioritize_healthy_models(fallback_candidates)
    if is_model_rate_limited(model) and fallback_candidates:
        first_healthy = fallback_candidates[0]
        if first_healthy != model:
            logger.info(
                f"call_llm model '{model}' is currently in rate-limit cooldown. Bypassing to healthy model '{first_healthy}'."
            )
            model = first_healthy
            payload["model"] = model
            if is_openmodel:
                from backend.agent import translate_to_anthropic_payload
                actual_payload = translate_to_anthropic_payload(payload)
            else:
                actual_payload = payload

    attempted_models = set()
    max_retries = max(4, len(fallback_candidates) + 1)
    last_err = None
    subagent_timeout = 90.0 if any(k in (model or "").lower() for k in ("deepseek-r1", "r1", "o1", "o3")) else 45.0
    async with httpx.AsyncClient(timeout=subagent_timeout) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    url,
                    json=actual_payload,
                    headers=headers
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as net_err:
                last_err = net_err
                err_desc = f"{type(net_err).__name__}: {net_err}".rstrip(": ")
                logger.warning(f"call_llm transport/timeout error (attempt {attempt+1}/{max_retries}): {err_desc}")
                is_dns_err = (
                    isinstance(net_err, (httpx.ConnectError, socket.gaierror))
                    or any(k in err_desc for k in ("-5", "-2", "-3", "No address associated with hostname", "Name or service not known", "Temporary failure in name resolution", "gaierror"))
                )
                if is_dns_err and len(attempted_models) >= 1:
                    logger.warning(
                        f"call_llm endpoint host DNS resolution failed across fallback models ({err_desc}). "
                        f"Aborting further model fallbacks to avoid redundant connection attempts."
                    )
                    raise
                current_m = payload.get("model")
                if attempt >= 1 or current_m != model:
                    attempted_models.add(current_m)
                    next_model = next((m for m in fallback_candidates if m not in attempted_models), None)
                    if next_model:
                        logger.warning(
                            f"call_llm model '{current_m}' network/timeout error ({err_desc}). Falling back to model '{next_model}'..."
                        )
                        payload["model"] = next_model
                        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                        await asyncio.sleep(0.5)
                        continue
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            if response.status_code != 200:
                if response.status_code in (429, 502, 503, 504, 408):
                    last_err = Exception(f"LLM API error {response.status_code}: {response.text}")
                    current_m = payload.get("model")
                    is_rate_limit = response.status_code == 429 or "rate-limit" in response.text.lower()
                    if is_rate_limit:
                        retry_after = response.headers.get("retry-after")
                        if retry_after and attempt == 0:
                            try:
                                delay = max(float(retry_after), 1.0)
                            except (ValueError, TypeError):
                                delay = 2.0
                            if delay <= 5.0:
                                await asyncio.sleep(delay)
                                continue
                        cooldown_secs = 60.0
                        if retry_after:
                            try:
                                cooldown_secs = max(float(retry_after), 15.0)
                            except (ValueError, TypeError):
                                pass
                        mark_model_rate_limited(current_m, cooldown_secs)

                    attempted_models.add(current_m)
                    next_model = None
                    if is_rate_limit or attempt >= 1 or current_m != model:
                        next_model = next((m for m in fallback_candidates if m not in attempted_models and not is_model_rate_limited(m)), None)
                        if not next_model:
                            next_model = next((m for m in fallback_candidates if m not in attempted_models), None)
                    if next_model:
                        logger.info(
                            f"call_llm model '{current_m}' transient error ({response.status_code}). Falling back to model '{next_model}'..."
                        )
                        payload["model"] = next_model
                        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        if attempt < max_retries - 1 and not is_rate_limit:
                            logger.info(
                                f"call_llm transient HTTP {response.status_code} (attempt {attempt+1}/{max_retries}): {response.text[:200]}"
                            )
                        else:
                            logger.warning(
                                f"call_llm transient HTTP {response.status_code} (attempt {attempt+1}/{max_retries}): {response.text[:200]}"
                            )

                    if attempt == max_retries - 1:
                        raise last_err

                    retry_after = response.headers.get("retry-after")
                    delay = 1.5 * (attempt + 1)
                    if retry_after:
                        try:
                            delay = max(float(retry_after), 1.0)
                        except (ValueError, TypeError):
                            pass
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception(f"LLM API error {response.status_code}: {response.text}")

            raw_data = response.json()
            if is_openmodel:
                from backend.agent import translate_to_openai_response
                data = translate_to_openai_response(raw_data)
            else:
                data = raw_data
                
            if not isinstance(data, dict):
                raise Exception(f"LLM returned non-dict response: {data}")
                
            if "error" in data:
                err_detail = data.get("error", {})
                err_text = err_detail.get("message") if isinstance(err_detail, dict) else str(err_detail)
                err_code = err_detail.get("code") if isinstance(err_detail, dict) else None
                try:
                    numeric_code = int(err_code) if err_code is not None else None
                except (ValueError, TypeError):
                    numeric_code = None

                is_rate_limit = (
                    numeric_code == 429
                    or err_code in (429, "429")
                    or any(ind in str(err_text).lower() for ind in ["rate-limited", "rate limit", "engine_overloaded", "quota"])
                )
                is_timeout_or_5xx = (
                    numeric_code in (504, 502, 503, 500, 408)
                    or err_code in (504, "504", 502, "502", 503, "503", 500, "500", 408, "408")
                    or any(ind in str(err_text).lower() for ind in ["timeout", "timed out", "provider error", "temporarily unavailable", "overloaded", "bad gateway", "service unavailable"])
                    or (isinstance(err_detail, dict) and isinstance(err_detail.get("metadata"), dict) and err_detail.get("metadata", {}).get("error_type") in ("timeout", "provider_error"))
                )

                if is_rate_limit or is_timeout_or_5xx:
                    last_err = Exception(f"LLM API error: {err_text}")
                    current_m = payload.get("model")
                    if is_rate_limit:
                        mark_model_rate_limited(current_m, 60.0)

                    attempted_models.add(current_m)
                    next_model = next((m for m in fallback_candidates if m not in attempted_models and not is_model_rate_limited(m)), None)
                    if not next_model:
                        next_model = next((m for m in fallback_candidates if m not in attempted_models), None)
                    if next_model:
                        reason_desc = (
                            "rate-limited in body"
                            if is_rate_limit
                            else ("provider error/timeout in body" if is_timeout_or_5xx else "API error in body")
                        )
                        log_fn = logger.info if is_rate_limit else logger.warning
                        log_fn(
                            f"call_llm model '{current_m}' {reason_desc} ({str(err_text)[:100]}). Falling back to model '{next_model}'..."
                        )
                        payload["model"] = next_model
                        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        logger.warning(f"call_llm provider rate-limit/timeout in body (attempt {attempt+1}/{max_retries}): {err_text}")
                    if attempt == max_retries - 1:
                        raise last_err
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise Exception(f"LLM API error: {err_text or raw_data}")

            if not data.get("choices") or not isinstance(data.get("choices"), list) or len(data["choices"]) == 0:
                current_m = payload.get("model")
                attempted_models.add(current_m)
                logger.warning(
                    f"call_llm model '{current_m}' returned empty choices in response (attempt {attempt+1}/{max_retries})."
                )
                last_err = Exception(f"LLM API error: Empty choices in response from model '{current_m}'")
                next_model = next((m for m in fallback_candidates if m not in attempted_models and not is_model_rate_limited(m)), None)
                if not next_model:
                    next_model = next((m for m in fallback_candidates if m not in attempted_models), None)
                if next_model:
                    logger.warning(
                        f"call_llm falling back to model '{next_model}' after empty choices..."
                    )
                    payload["model"] = next_model
                    actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                    await asyncio.sleep(0.5)
                    continue
                if attempt == max_retries - 1:
                    raise last_err
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
                
            choice_0 = data["choices"][0] if (isinstance(data.get("choices"), list) and len(data["choices"]) > 0) else {}
            choice_msg = choice_0.get("message") if isinstance(choice_0, dict) else {}
            
            res_content = ""
            if isinstance(choice_msg, dict):
                res_content = choice_msg.get("content") or ""
                if not str(res_content).strip():
                    res_content = choice_msg.get("reasoning") or choice_msg.get("reasoning_content") or ""
            if not str(res_content).strip() and isinstance(choice_0, dict):
                res_content = choice_0.get("text") or ""
                
            if str(res_content).strip():
                return str(res_content)

            # Upstream returned empty or whitespace-only content
            current_m = payload.get("model")
            attempted_models.add(current_m)
            logger.warning(
                f"call_llm model '{current_m}' returned empty content (attempt {attempt+1}/{max_retries})."
            )
            last_err = Exception(f"LLM API returned empty content from model '{current_m}'")
            next_model = next((m for m in fallback_candidates if m not in attempted_models), None)
            if next_model and attempt < max_retries - 1:
                logger.warning(
                    f"call_llm falling back to model '{next_model}' after empty response..."
                )
                payload["model"] = next_model
                actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                await asyncio.sleep(0.5)
                continue
            
    if last_err:
        raise last_err
    raise Exception("call_llm failed without response")

# ─── Safety guard ────────────────────────────────────────────────────────────

# Patterns that are dangerous inside the code-execution sandbox.
# Any code matching these is rejected before subprocess execution.
_UNSAFE_PATTERNS: List[tuple] = [
    # Shell execution
    (r"\bos\.system\s*\(",                   "os.system() — shell execution forbidden in sandbox"),
    (r"\bsubprocess\b",                       "subprocess — shell execution forbidden in sandbox"),
    (r"\bos\.popen\s*\(",                     "os.popen() — shell execution forbidden in sandbox"),
    (r"\bos\.exec[a-z]*\s*\(",               "os.exec*() — process spawning forbidden in sandbox"),
    # File system destruction
    (r"\bshutil\.rmtree\s*\(",               "shutil.rmtree() — recursive deletion forbidden"),
    (r"\bos\.remove\s*\(",                    "os.remove() — file deletion forbidden in sandbox"),
    (r"\bos\.unlink\s*\(",                    "os.unlink() — file deletion forbidden in sandbox"),
    (r"\bshutil\.move\s*\(",                  "shutil.move() — file move forbidden in sandbox"),
    # Network access (sandbox should be offline)
    (r"\bsocket\.socket\s*\(",               "socket.socket() — network access forbidden in sandbox"),
    (r"\bhttpx\b",                            "httpx — network requests forbidden in sandbox"),
    (r"\brequests\.get\s*\(",                 "requests.get() — network requests forbidden in sandbox"),
    (r"\burllib\.request",                    "urllib.request — network requests forbidden in sandbox"),
    # Dangerous builtins
    (r"\beval\s*\(",                          "eval() — dynamic code execution forbidden"),
    (r"\bexec\s*\(",                          "exec() — dynamic code execution forbidden"),
    (r"__import__\s*\(",                      "__import__() — dynamic imports forbidden"),
    # Env / credential access
    (r"os\.getenv\s*\(.*(?:KEY|TOKEN|SECRET|PASSWORD)", "os.getenv with credentials — forbidden in sandbox"),
]

def safety_check(code_str: str) -> Optional[str]:
    """
    Checks generated code for dangerous patterns before execution.
    Returns an error message string if unsafe, None if safe.
    """
    for pattern, description in _UNSAFE_PATTERNS:
        if re.search(pattern, code_str, re.IGNORECASE):
            return f"🛡️ SAFETY BLOCK: Code contains forbidden pattern — {description}. Execution prevented."
    return None


def execute_code(code_str: str) -> Dict[str, Any]:
    """Runs Python code using the isolated stateful Sandbox container."""
    # ── Safety guard (from Fugu architecture) ──────────────────────
    safety_error = safety_check(code_str)
    if safety_error:
        logger.warning(f"Code execution BLOCKED by safety guard: {safety_error}")
        return {
            "success": False,
            "stdout": "",
            "stderr": safety_error,
            "returncode": -3  # Special code for safety block
        }

    logger.info("Executing generated code via HTTP Sandbox API...")
    try:
        response = requests.post(
            "http://jarvis-sandbox:8080/execute",
            json={"code": code_str, "timeout": 120.0},
            timeout=125.0
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            "success": data.get("success", False),
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", "") + ("\n" + data.get("error", "") if data.get("error") else ""),
            "returncode": 0 if data.get("success", False) else -1,
            "display_data": data.get("display_data", [])
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to connect to Sandbox container: {str(e)}\nMake sure jarvis-sandbox is running.",
            "returncode": -2,
            "display_data": []
        }



# ─── ResearchAgent helpers ────────────────────────────────────────────────────

# Common browser-like headers so servers don't reject us
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# Crypto symbol → CoinGecko id (including Russian word forms)
_CRYPTO_IDS = {
    # Bitcoin
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "биткоин": "bitcoin", "биткоина": "bitcoin", "биткоину": "bitcoin",
    "биткоины": "bitcoin", "биткоином": "bitcoin", "биткоинов": "bitcoin",
    # Ethereum
    "eth": "ethereum", "ethereum": "ethereum",
    "эфир": "ethereum", "эфириум": "ethereum", "эфириума": "ethereum",
    "эфириуме": "ethereum", "эфириумом": "ethereum",
    # BNB
    "bnb": "binancecoin",
    # Solana
    "sol": "solana", "solana": "solana", "солана": "solana",
    # XRP / Ripple
    "xrp": "ripple", "ripple": "ripple", "рипл": "ripple",
    # Cardano
    "ada": "cardano", "cardano": "cardano", "кардано": "cardano",
    # Dogecoin
    "doge": "dogecoin", "dogecoin": "dogecoin", "догекоин": "dogecoin",
    # TON
    "ton": "the-open-network", "тон": "the-open-network",
}

# Public RSS feeds (verified working from Docker, May 2026)
_RSS_FEEDS = [
    ("Habr",        "https://habr.com/ru/rss/news/"),
    ("RBC",         "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    ("Lenta.ru",    "https://lenta.ru/rss/news"),
    ("TASS",        "https://tass.ru/rss/v2.xml"),
    ("BBC World",   "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("CoinDesk",    "https://feeds.feedburner.com/CoinDesk"),
    ("Crypto.news", "https://crypto.news/feed/"),
    ("Forklog",     "https://forklog.com/feed/"),
]


class ResearchAgent:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        # Use per-agent model if configured, otherwise fall back to the passed model
        self.model = get_agent_model("research", model)
        if self.model != model:
            logger.info(f"ResearchAgent using dedicated model: {self.model} (main: {model})")

    # ── 1. CoinGecko – free public API, no key needed ────────────────────────
    async def fetch_crypto_prices(self, ids: List[str]) -> Optional[str]:
        """Fetch current crypto prices from CoinGecko public API."""
        joined = ",".join(ids)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={joined}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true"
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    logger.warning(f"CoinGecko returned {res.status_code}")
                    return None
                data = res.json()
                lines = []
                for coin_id in ids:
                    if coin_id not in data:
                        continue
                    d = data[coin_id]
                    price   = d.get("usd", "N/A")
                    change  = d.get("usd_24h_change", 0.0)
                    mcap    = d.get("usd_market_cap", 0)
                    arrow   = "📈" if change >= 0 else "📉"
                    lines.append(
                        f"{coin_id.upper()} {arrow} ${price:,.2f} | "
                        f"24h: {change:+.2f}% | "
                        f"MCap: ${mcap/1e9:.1f}B"
                    )
                return "\n".join(lines) if lines else None
        except Exception as e:
            logger.warning(f"CoinGecko fetch error: {e}")
            return None

    # ── 2. RSS feeds – work from any IP ──────────────────────────────────────
    async def fetch_rss_news(self, keywords: List[str], max_items: int = 6) -> Optional[str]:
        """Pull latest news from RSS feeds, filter by keywords."""
        kw_lower = [k.lower() for k in keywords]
        collected: List[Dict] = []

        async with httpx.AsyncClient(timeout=12.0, headers=_HEADERS, follow_redirects=True) as client:
            for feed_name, feed_url in _RSS_FEEDS:
                if len(collected) >= max_items:
                    break
                try:
                    res = await client.get(feed_url)
                    if res.status_code != 200:
                        continue
                    root = ET.fromstring(res.text)
                    items = root.findall(".//item")
                    for item in items:
                        title   = (item.findtext("title") or "").strip()
                        desc    = (item.findtext("description") or "").strip()
                        link    = (item.findtext("link") or "").strip()
                        pub     = (item.findtext("pubDate") or "").strip()

                        # Strip HTML from description
                        if "<" in desc:
                            desc = BeautifulSoup(desc, "html.parser").get_text(separator=" ")

                        combined = (title + " " + desc).lower()
                        # If keywords given, filter; if no keywords, take all
                        if kw_lower and not any(k in combined for k in kw_lower):
                            continue

                        collected.append({
                            "source": feed_name,
                            "title":  title,
                            "desc":   desc[:300],
                            "link":   link,
                            "pub":    pub,
                        })
                        if len(collected) >= max_items:
                            break
                except Exception as e:
                    logger.warning(f"RSS {feed_name} error: {e}")

        if not collected:
            return None

        parts = []
        for idx, n in enumerate(collected, 1):
            parts.append(
                f"Новость {idx} [{n['source']}]:\n"
                f"  {n['title']}\n"
                f"  {n['desc']}\n"
                f"  🔗 {n['link']}"
            )
        return "\n\n".join(parts)

    # ── 3. Direct HTTP scrape fallback ────────────────────────────────────────
    async def scrape_page(self, url: str) -> Optional[str]:
        """Scrape a web page and return clean text. Returns None on failure."""
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=_HEADERS, follow_redirects=True) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    return None
                soup = BeautifulSoup(res.text, "html.parser")
                for el in soup(["script", "style", "header", "footer", "nav", "aside", "noscript", "form"]):
                    el.decompose()
                main = soup.find("article") or soup.find("main") or soup.find("body")
                raw  = (main or soup).get_text(separator=" ")
                lines  = (ln.strip() for ln in raw.splitlines())
                chunks = (ph.strip() for ln in lines for ph in ln.split("  "))
                return " ".join(ch for ch in chunks if ch)[:3000]
        except Exception as e:
            logger.warning(f"scrape_page error for {url}: {e}")
            return None

    # ── 4. Smart router: detect topic and pick right sources ─────────────────
    async def run(self, prompt: str) -> str:
        prompt_lower = prompt.lower()

        # Detect crypto coins mentioned in the request
        crypto_ids = []
        for alias, cg_id in _CRYPTO_IDS.items():
            if alias in prompt_lower and cg_id not in crypto_ids:
                crypto_ids.append(cg_id)

        results_parts: List[str] = []

        # 1) Fetch live prices if crypto detected
        if crypto_ids:
            logger.info(f"Research Agent: fetching CoinGecko prices for {crypto_ids}")
            price_data = await self.fetch_crypto_prices(crypto_ids)
            if price_data:
                results_parts.append("💰 **Актуальные цены (CoinGecko):**\n" + price_data)

        # 2) Fetch relevant news from RSS only if crypto detected or news specifically requested
        is_news_requested = any(w in prompt_lower for w in ["новост", "news", "событи", "случил", "произош", "что нового", "хабр", "habr", "рбк", "rbc", "tass", "тасс", "лента", "lenta"])
        if crypto_ids or is_news_requested:
            # Build keyword list from crypto ids + request words
            news_keywords = list(crypto_ids)
            # Add other meaningful words from prompt (>= 4 chars)
            for word in re.findall(r"[a-zа-я]{4,}", prompt_lower):
                if word not in news_keywords and word not in ("найди", "покажи", "расскажи", "сравни", "новост", "цена", "цену", "price"):
                    news_keywords.append(word)

            logger.info(f"Research Agent: fetching RSS news with keywords={news_keywords}")
            news_data = await self.fetch_rss_news(news_keywords, max_items=5)

            # If no filtered results, try without keyword filter ONLY if news/headlines were requested
            if not news_data and is_news_requested:
                logger.info("Research Agent: no filtered news, trying without keyword filter for general news request")
                news_data = await self.fetch_rss_news([], max_items=4)

            if news_data:
                results_parts.append("📰 **Последние новости:**\n" + news_data)

        # 3) Fetch general web search results (up to 2 queries separated by ';')
        logger.info(f"Research Agent: refining search query from instructions: '{prompt[:60]}...'")
        refining_messages = [
            {"role": "system", "content": "Вы — ассистент, который преобразует длинные инструкции в 1-2 эффективных поисковых запроса для поисковых систем (Google/DuckDuckGo). Если запросов два, разделите их точкой с запятой (;). Выводите ТОЛЬКО поисковый(е) запрос(ы), без лишних слов, знаков препинания (кроме точки с запятой), кавычек и преамбул.\n"
                                          "КРИТИЧЕСКОЕ ПРАВИЛО: Категорически запрещено использовать в поисковых запросах слова вроде 'прогноз', 'прогнозы', 'валуйные', 'валуйная', 'value', 'советы', 'ставки от редакции'. Заменяйте их на запросы сырых данных, например: 'коэффициенты', 'odds', 'букмекерские котировки', 'расписание матчей', 'соперники'."},
            {"role": "user", "content": f"Преобразуй следующую инструкцию в 1-2 поисковых запроса (через ';' если два):\n\n\"{prompt}\""}
        ]
        try:
            refined_response = await call_llm(refining_messages, self.api_key, self.model)
            queries = [q.strip().replace('"', '').replace("'", "") for q in refined_response.split(";")]
            queries = [q for q in queries if q]
            logger.info(f"Research Agent: refined queries: {queries}")
        except Exception as ref_err:
            logger.warning(f"Failed to refine query: {ref_err}")
            queries = [prompt]

        from backend.tools import web_search
        for idx, query in enumerate(queries[:2], 1):
            logger.info(f"Research Agent: performing web search ({idx}/{len(queries)}) for '{query}'")
            search_results = web_search(query)
            
            # If search failed on refined query, try a simplified fallback query
            if not search_results or "Не удалось получить результаты поиска." in search_results or "error" in str(search_results).lower():
                simplified_q = re.sub(r'[^\w\s\.\-]', ' ', query).strip()
                if simplified_q and simplified_q != query:
                    logger.info(f"Research Agent: attempting simplified fallback query: '{simplified_q}'")
                    fallback_results = web_search(simplified_q)
                    if fallback_results and "Не удалось получить результаты поиска." not in fallback_results:
                        search_results = fallback_results

            if search_results and "Не удалось получить результаты поиска." not in search_results and not search_results.strip().startswith('{"error":'):
                results_parts.append(f"🌐 **Результаты веб-поиска по запросу '{query}':**\n" + search_results)
                
                # Extract and scrape top URLs to get actual page content
                urls = re.findall(r"https?://[^\s\)\`\]]+", search_results)
                scraped_count = 0
                for url in urls:
                    if scraped_count >= 2:
                        break
                    if any(domain in url for domain in ["google.com", "duckduckgo.com", "bing.com", "yandex.ru", "twitter.com", "facebook.com"]):
                        continue
                    logger.info(f"Research Agent: auto-scraping URL to get full content: {url}")
                    page_text = await self.scrape_page(url)
                    if page_text:
                        results_parts.append(f"📄 **Содержимое страницы {url}:**\n{page_text[:1500]}")
                        scraped_count += 1

        if not results_parts:
            return "Не удалось получить данные из внешних источников. Попробуйте переформулировать запрос."

        return "\n\n" + "\n\n---\n\n".join(results_parts)



class CodeAgent:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        # Use per-agent model if configured, otherwise fall back to the passed model
        self.model = get_agent_model("code", model)
        if self.model != model:
            logger.info(f"CodeAgent using dedicated model: {self.model} (main: {model})")

    def extract_code(self, text: str) -> str:
        match = re.search(r"```python(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    async def run_and_correct(self, prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": "Вы — Code Agent. Напишите чистый Python код для решения задачи. "
                                          "КРИТИЧЕСКОЕ ТРЕБОВАНИЕ: Вы категорически не имеете права выдумывать демонстрационные, вымышленные или фейковые спортивные матчи! "
                                          "Используйте исключительно реальные данные о командах и матчах, переданные вам в тексте инструкции из результатов поиска предыдущих шагов. "
                                          "Для спортивного анализа и поиска валуйных ставок: вы должны написать Python-скрипт, который рассчитывает валуйность математически. Например, считывает коэффициенты исходов (1, X, 2), вычисляет маржу букмекера по формуле (1/K1 + 1/KX + 1/K2 - 1), определяет реальные вероятности, а затем находит недооцененные букмекером котировки (математическое ожидание EV = P * Odds - 1 > 0). "
                                          "Вы не имеете права лениться: если точных числовых коэффициентов букмекерских контор для найденных реальных матчей в результатах поиска нет, ваш код ОБЯЗАН провести математическое моделирование (например, рассчитать вероятности победы/ничьей/поражения по распределению Пуассона на основе средней результативности/статистики голов команд в лиге/сезоне, или оценить вероятности по последним встречам) и вывести результаты расчетов математического ожидания для этих команд, используя расчетные вероятности и стандартный диапазон коэффициентов (например, 1.8 - 2.5), а не просто отказываться от расчетов. "
                                          "Выводите ТОЛЬКО выполняемый Python код в разметке ```python ... ``` без лишних слов, комментариев и форматирования вне блока кода."},
            {"role": "user", "content": prompt}
        ]
        code_response = await call_llm(messages, self.api_key, self.model)
        code_str = self.extract_code(code_response)
        
        exec_result = execute_code(code_str)
        attempts = 1
        
        # Self-correction loop: retry up to 2 corrections
        while not exec_result["success"] and attempts < 3:
            logger.info(f"Code Agent execution failed (Attempt {attempts}). Triggering self-correction...")
            correction_messages = [
                {"role": "system", "content": "Вы — Code Agent. Код, который вы написали, завершился ошибкой. Исправьте его. Выведите исправленный Python код ТОЛЬКО в разметке ```python ... ``` без дополнительных объяснений."},
                {"role": "user", "content": f"Задача: {prompt}\n\nНеисправный код:\n```python\n{code_str}\n```\n\nРезультат выполнения:\nSTDOUT:\n{exec_result['stdout']}\nSTDERR:\n{exec_result['stderr']}\n\nИсправьте ошибку в коде."}
            ]
            corrected_response = await call_llm(correction_messages, self.api_key, self.model)
            code_str = self.extract_code(corrected_response)
            exec_result = execute_code(code_str)
            attempts += 1
            
        return {
            "code": code_str,
            "success": exec_result["success"],
            "stdout": exec_result["stdout"],
            "stderr": exec_result["stderr"],
            "attempts": attempts,
            "display_data": exec_result.get("display_data", [])
        }

class AnalystAgent:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        # Use per-agent model if configured, otherwise fall back to the passed model
        self.model = get_agent_model("analyst", model)
        if self.model != model:
            logger.info(f"AnalystAgent using dedicated model: {self.model} (main: {model})")

    async def run(self, instructions: str) -> Dict[str, Any]:
        plot_filename = f"plot_{uuid.uuid4().hex[:8]}.png"
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        plots_dir = os.path.join(base_dir, "data", "plots")
        os.makedirs(plots_dir, exist_ok=True)
        plot_path = os.path.join(plots_dir, plot_filename)
        
        prompt = (
            f"Напишите Python скрипт с использованием pandas, numpy и matplotlib, который считывает данные из таблицы и строит график.\n"
            f"Указания Сэра: \"{instructions}\"\n\n"
            f"ВАЖНОЕ ПРАВИЛО: Все загруженные пользователем файлы CSV и Excel находятся в текущей директории ('/mnt/data').\n"
            f"Используйте plt.style.use('dark_background') для красивого темного оформления графика (под стиль Jarvis!).\n"
            f"Убедитесь, что вы импортировали matplotlib.pyplot as plt и pandas as pd. Выведите график в Jupyter (например, просто не пишите ничего в конце или напишите plt.show()). Не используйте plt.savefig()."
        )
        
        code_agent = CodeAgent(self.api_key, self.model)
        res = await code_agent.run_and_correct(prompt)
        
        if res["success"] and res.get("display_data"):
            image_saved = False
            for data in res["display_data"]:
                if "image/png" in data:
                    png_data = base64.b64decode(data["image/png"])
                    with open(plot_path, "wb") as f:
                        f.write(png_data)
                    image_saved = True
                    break
            
            if image_saved:
                logger.info(f"Analyst Agent successfully created chart: {plot_filename}")
                return {
                    "success": True,
                    "plot_url": f"/api/plots/{plot_filename}",
                    "code": res["code"],
                    "stdout": res["stdout"]
                }
            else:
                return {
                    "success": False,
                    "error": "График не был сгенерирован (в выводе нет image/png).",
                    "code": res["code"]
                }
        else:
            logger.error(f"Analyst Agent failed to create chart. Error: {res['stderr']}")
            return {
                "success": False,
                "error": res["stderr"] or "Файл графика не был создан.",
                "code": res["code"]
            }
