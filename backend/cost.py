"""Centralized cost calculation for LLM usage.

Single source of truth for token pricing so estimates and real usage agree.
Rates are USD per 1,000,000 tokens (prompt_rate, completion_rate).

The previous logic lived inline in ``agent.py`` (``calculate_cost``); it is kept
here and re-exported for backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("hermes.cost")

# model-substring -> (prompt_rate, completion_rate) per 1M tokens.
# Ordered by specificity is not required; longest match wins.
_PRICING: Dict[str, Tuple[float, float]] = {
    "gemini-2.5-pro": (0.075, 0.30),
    "gemini-2.5-flash": (0.0375, 0.15),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-4": (3.00, 15.00),
    "deepseek-r2": (0.55, 2.19),
    "deepseek-r1": (0.55, 2.19),
    "deepseek-v4-flash": (0.07, 0.14),
    "deepseek-v3": (0.14, 0.28),
}

# Default when the model is unknown (Gemini 2.5 Pro pricing, as before).
_DEFAULT_RATES: Tuple[float, float] = (0.075, 0.30)


def get_rates(model: str) -> Tuple[float, float]:
    """Return (prompt_rate, completion_rate) per 1M tokens for a model."""
    model_lower = (model or "").lower()
    best: Optional[Tuple[str, Tuple[float, float]]] = None
    for key, rates in _PRICING.items():
        if key in model_lower:
            if best is None or len(key) > len(best[0]):
                best = (key, rates)
    return best[1] if best else _DEFAULT_RATES


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Cost in USD for a single completion."""
    prompt_rate, completion_rate = get_rates(model)
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    return (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000.0


def is_model_priced(model: str) -> bool:
    """True if we have explicit (non-default) pricing for this model."""
    model_lower = (model or "").lower()
    return any(key in model_lower for key in _PRICING)
