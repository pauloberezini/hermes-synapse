"""
Shared LLM Model Rate-Limit Manager.

Tracks transient upstream rate-limits (HTTP 429 / provider rate-limit messages)
across all subagents, tools, and orchestrator components to eliminate cascading
429 storms and redundant failed roundtrips to rate-limited models.
"""

import time
import logging
from typing import List, Dict, Optional

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
