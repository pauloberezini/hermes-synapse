import os
import re
import sys
import uuid
import random
import logging
import httpx
import tempfile
import subprocess
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


async def call_llm(messages: List[Dict[str, str]], api_key: str, model: str) -> str:
    """Subagent LLM helper.

    Delegates the HTTP call + parsing to the unified normalized client
    (``backend.llm_client``) so subagents inherit timeout, transient retry with
    backoff, secret masking and consistent response handling. Preserves the
    historical ``-> str`` contract and ``Exception`` on hard failure.
    """
    api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    from backend.agent import _local_model_system_hint
    from backend.llm_client import (
        STATUS_PARSE_ERROR,
        STATUS_PROVIDER_ERROR,
        STATUS_TIMEOUT,
        call_llm_normalized,
    )

    local_hint = _local_model_system_hint(model, api_base)
    if local_hint:
        messages = [dict(msg) for msg in messages]
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = (msg.get("content") or "") + local_hint
                break
        else:
            messages.insert(0, {"role": "system", "content": local_hint.strip()})

    result = await call_llm_normalized(
        api_base=api_base,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.2,
    )

    if result.status in (STATUS_TIMEOUT, STATUS_PROVIDER_ERROR, STATUS_PARSE_ERROR):
        # Do not leak provider bodies/secrets; error_message is already masked.
        raise Exception(f"LLM call failed ({result.status}): {result.error_message}")

    return result.content or ""

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
    """Runs Python code using local subprocess.
    (Docker sandbox was removed because the backend is already containerized,
    and sibling containers lack access to volume mounts like uploaded files/plots without complex host-path mapping).
    """
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

    logger.info("Executing generated code via local subprocess...")
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code_str)
        temp_name = f.name
    
    try:
        # Increase timeout slightly for data analysis tasks
        res = subprocess.run(
            [sys.executable, temp_name],
            capture_output=True,
            text=True,
            timeout=15.0
        )
        return {
            "success": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out (15 seconds limit exceeded).",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Failed to execute subprocess: {str(e)}",
            "returncode": -2
        }
    finally:
        try:
            os.remove(temp_name)
        except Exception:
            pass



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
            if search_results and "Не удалось получить результаты поиска." not in search_results:
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
            "attempts": attempts
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
            f"ВАЖНОЕ ПРАВИЛО: Все загруженные пользователем файлы CSV и Excel сохраняются в папке '/app/backend/data/uploads/'.\n"
            f"Если в указаниях написано 'считай sales.csv', ваш скрипт должен прочитать файл из '/app/backend/data/uploads/sales.csv' с помощью pd.read_csv() (или pd.read_excel() для Excel).\n\n"
            f"КРИТИЧЕСКОЕ ТРЕБОВАНИЕ: Скрипт ОБЯЗАТЕЛЬНО должен сохранять сгенерированный график в файл по пути: '{plot_path}' с помощью plt.savefig('{plot_path}').\n"
            f"Используйте plt.style.use('dark_background') для красивого темного оформления графика (под стиль Jarvis!).\n"
            f"Убедитесь, что вы импортировали matplotlib.pyplot as plt и pandas as pd. Не вызывайте plt.show(), только plt.savefig()."
        )
        
        code_agent = CodeAgent(self.api_key, self.model)
        res = await code_agent.run_and_correct(prompt)
        
        if res["success"] and os.path.exists(plot_path):
            logger.info(f"Analyst Agent successfully created chart: {plot_filename}")
            return {
                "success": True,
                "plot_url": f"/api/plots/{plot_filename}",
                "code": res["code"],
                "stdout": res["stdout"]
            }
        else:
            logger.error(f"Analyst Agent failed to create chart. Error: {res['stderr']}")
            return {
                "success": False,
                "error": res["stderr"] or "Файл графика не был создан.",
                "code": res["code"]
            }
