"""
Shared LLM Model Rate-Limit Manager.

Tracks transient upstream rate-limits (HTTP 429 / provider rate-limit messages)
across all subagents, tools, and orchestrator components to eliminate cascading
429 storms and redundant failed roundtrips to rate-limited models.
"""

import os
import json
import socket
import time
import logging
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("hermes.llm_manager")

# Global in-process rate-limit cooldown timestamps: model_name -> expiration timestamp
_MODEL_RATE_LIMIT_COOLDOWNS: Dict[str, float] = {}
_MODEL_CONSECUTIVE_429: Dict[str, int] = {}
_MODEL_LAST_429_AT: Dict[str, float] = {}


def mark_model_rate_limited(model: Optional[str], cooldown_seconds: float = 60.0) -> None:
    """
    Mark an LLM model as rate-limited until the cooldown timestamp expires.
    Applies adaptive exponential backoff for consecutive 429 rate limits.
    """
    if not model or not isinstance(model, str):
        return
    model_clean = model.strip()
    now = time.time()
    last_429 = _MODEL_LAST_429_AT.get(model_clean, 0.0)
    if (now - last_429) < 1800.0:
        consecutive = _MODEL_CONSECUTIVE_429.get(model_clean, 0) + 1
    else:
        consecutive = 1
    _MODEL_CONSECUTIVE_429[model_clean] = consecutive
    _MODEL_LAST_429_AT[model_clean] = now

    multiplier = min(2 ** (consecutive - 1), 8)
    base_cooldown = max(float(cooldown_seconds), 5.0)
    cooldown = min(base_cooldown * multiplier, 1800.0)

    expires_at = now + cooldown
    _MODEL_RATE_LIMIT_COOLDOWNS[model_clean] = expires_at
    logger.info(
        f"Model '{model_clean}' marked rate-limited (streak={consecutive}, mult={multiplier}x). Cooldown for {cooldown:.1f}s until {expires_at:.1f}."
    )


def mark_model_success(model: Optional[str]) -> None:
    """
    Mark an LLM model as having succeeded, resetting consecutive 429 backoff counter.
    """
    if not model or not isinstance(model, str):
        return
    model_clean = model.strip()
    _MODEL_CONSECUTIVE_429.pop(model_clean, None)
    _MODEL_LAST_429_AT.pop(model_clean, None)


def is_model_rate_limited(model: Optional[str]) -> bool:
    """
    Check if a model is currently within an active rate-limit cooldown.
    """
    if not model or not isinstance(model, str):
        return False
    model_clean = model.strip()
    expires_at = _MODEL_RATE_LIMIT_COOLDOWNS.get(model_clean, 0.0)
    return time.time() < expires_at


def get_model_cooldown_remaining(model: Optional[str]) -> float:
    """
    Return remaining seconds in cooldown for a model, or 0.0 if not in cooldown.
    """
    if not model or not isinstance(model, str):
        return 0.0
    model_clean = model.strip()
    return max(0.0, _MODEL_RATE_LIMIT_COOLDOWNS.get(model_clean, 0.0) - time.time())


def reset_model_cooldowns(model: Optional[str] = None) -> None:
    """
    Reset rate-limit cooldown for a specific model or all models.
    """
    if model:
        m = model.strip()
        _MODEL_RATE_LIMIT_COOLDOWNS.pop(m, None)
        _MODEL_CONSECUTIVE_429.pop(m, None)
        _MODEL_LAST_429_AT.pop(m, None)
    else:
        _MODEL_RATE_LIMIT_COOLDOWNS.clear()
        _MODEL_CONSECUTIVE_429.clear()
        _MODEL_LAST_429_AT.clear()


reset_rate_limits = reset_model_cooldowns


def prioritize_healthy_models(models: List[str]) -> List[str]:
    """
    Given a list of candidate model names, partition and order them such that
    healthy (non-cooldown) models come first, and models in active rate-limit
    cooldown are deprioritized to the end of the candidate list.
    Preserves original relative order within each partition.
    """
    healthy = []
    cooling_down = []
    seen = set()

    for m in models:
        if not m or not isinstance(m, str):
            continue
        clean_m = m.strip()
        if clean_m not in seen:
            seen.add(clean_m)
            if is_model_rate_limited(clean_m):
                cooling_down.append(clean_m)
            else:
                healthy.append(clean_m)

    return healthy + cooling_down


# ==============================================================================
# Endpoint Health & Circuit Breaker Manager
# ==============================================================================

_ENDPOINT_CIRCUIT_STATUS: Dict[str, Dict[str, Any]] = {}


def _normalize_endpoint_key(endpoint: Optional[str]) -> str:
    if not endpoint or not isinstance(endpoint, str):
        return ""
    clean = endpoint.strip().rstrip("/").lower()
    if clean.startswith("http://") or clean.startswith("https://"):
        from urllib.parse import urlparse
        parsed = urlparse(clean)
        return parsed.netloc or clean
    return clean


def is_dns_error(exc: Any) -> bool:
    """
    Check if an exception is specifically a DNS name resolution failure.
    Accurately identifies socket.gaierror and OS-level DNS failure markers,
    while explicitly excluding ReadTimeout and general connection/OSError issues.
    """
    if exc is None:
        return False
    if isinstance(exc, socket.gaierror):
        return True

    # Traverse exception chain (__cause__ / __context__)
    cur = exc
    while cur is not None:
        if isinstance(cur, socket.gaierror):
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)

    err_text = str(exc).lower()
    dns_markers = (
        "no address associated with hostname",
        "name or service not known",
        "temporary failure in name resolution",
        "gaierror",
        "getaddrinfo failed",
        "[errno -5]",
        "[errno -2]",
        "[errno -3]",
        "all connection attempts failed",
    )
    return any(marker in err_text for marker in dns_markers)


def is_endpoint_transport_error(exc: Any) -> bool:
    """
    Check if an exception represents a host/transport-level failure
    (DNS failure, connect timeout, read timeout, connection reset/refused).
    """
    if exc is None:
        return False
    if is_dns_error(exc):
        return True
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True

    err_text = str(exc).lower()
    transport_markers = (
        "read timed out",
        "readtimeout",
        "connect timed out",
        "connecttimeout",
        "connection refused",
        "connection reset",
        "connection aborted",
        "connection closed",
        "remoteprotocolerror",
        "network is unreachable",
        "timed out",
        "timeout",
    )
    return any(m in err_text for m in transport_markers)


def _get_circuit_cache_file() -> str:
    """Get path to file-backed circuit status cache for cross-process synchronization."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_dir = os.path.join(repo_root, "backend", "logs")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "llm_endpoint_circuit.json")


def mark_endpoint_unreachable(
    endpoint_or_host: Optional[str],
    reason: str = "",
    cooldown_seconds: float = 120.0,
) -> None:
    """
    Mark an LLM endpoint or host as unreachable until the cooldown expires.
    Trips the circuit breaker to prevent cascading timeouts across roles/agents.
    """
    key = _normalize_endpoint_key(endpoint_or_host)
    if not key:
        return

    now = time.time()
    expires_at = now + max(float(cooldown_seconds), 0.001)
    _ENDPOINT_CIRCUIT_STATUS[key] = {
        "expires_at": expires_at,
        "reason": reason,
        "tripped_at": now,
    }
    logger.warning(
        f"LLM endpoint circuit breaker TRIPPED for '{key}' for {cooldown_seconds:.1f}s until {expires_at:.1f}. Reason: {reason}"
    )

    try:
        cache_file = _get_circuit_cache_file()
        data = {}
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                data = json.load(f)
        data[key] = {
            "expires_at": expires_at,
            "reason": reason,
            "tripped_at": now,
        }
        with open(cache_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def is_endpoint_unreachable(endpoint_or_host: Optional[str]) -> Tuple[bool, str]:
    """
    Check if an LLM endpoint or host is currently in an active circuit breaker cooldown.
    Returns (is_unreachable, failure_reason).
    """
    key = _normalize_endpoint_key(endpoint_or_host)
    if not key:
        return False, ""

    now = time.time()
    # Check in-memory state first
    info = _ENDPOINT_CIRCUIT_STATUS.get(key)
    if info and now < info.get("expires_at", 0.0):
        return True, info.get("reason", "Endpoint in circuit cooldown")

    # Check file cache for cross-process state
    try:
        cache_file = _get_circuit_cache_file()
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                data = json.load(f)
            file_info = data.get(key)
            if file_info and now < file_info.get("expires_at", 0.0):
                # Update in-memory cache
                _ENDPOINT_CIRCUIT_STATUS[key] = file_info
                return True, file_info.get("reason", "Endpoint in circuit cooldown")
    except Exception:
        pass

    return False, ""


# ollama `llama3` is not an OpenRouter route (404 "No endpoints found").
# Closest live slug: Llama 3.1 8B Instruct. Local Ollama keeps the tag.
_OPENROUTER_MODEL_ALIASES = {
    "ollama/llama3": "meta-llama/llama-3.1-8b-instruct",
}


def resolve_provider_model(model: Optional[str], api_base: Optional[str] = None) -> Optional[str]:
    """Map provider-invalid model ids before the chat request. Other ids pass through."""
    if not model or not isinstance(model, str):
        return model
    clean = model.strip()
    base = api_base if api_base is not None else os.getenv("LLM_API_BASE", "")
    if "openrouter.ai" not in str(base).lower():
        return clean
    return _OPENROUTER_MODEL_ALIASES.get(clean, clean)


def resolve_provider_models(models: List[str], api_base: Optional[str] = None) -> List[str]:
    out: List[str] = []
    for model in models:
        resolved = resolve_provider_model(model, api_base)
        if resolved and resolved not in out:
            out.append(resolved)
    return out


def reset_endpoint_cooldowns(endpoint_or_host: Optional[str] = None) -> None:
    """Reset circuit breaker cooldown for a specific endpoint or all endpoints."""
    if endpoint_or_host:
        key = _normalize_endpoint_key(endpoint_or_host)
        _ENDPOINT_CIRCUIT_STATUS.pop(key, None)
    else:
        _ENDPOINT_CIRCUIT_STATUS.clear()

    try:
        cache_file = _get_circuit_cache_file()
        if os.path.exists(cache_file):
            if endpoint_or_host:
                key = _normalize_endpoint_key(endpoint_or_host)
                with open(cache_file, "r") as f:
                    data = json.load(f)
                data.pop(key, None)
                with open(cache_file, "w") as f:
                    json.dump(data, f)
            else:
                os.remove(cache_file)
    except Exception:
        pass

