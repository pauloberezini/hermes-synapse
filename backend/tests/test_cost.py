"""Tests for the centralized cost module (audit P1-4)."""

import pytest

from backend.cost import calculate_cost, get_rates, is_model_priced


def test_gemini_pro_rates():
    assert get_rates("google/gemini-2.5-pro") == (0.075, 0.30)


def test_gemini_flash_rates():
    assert get_rates("google/gemini-2.5-flash") == (0.0375, 0.15)


def test_longest_match_wins():
    # gpt-4o-mini must not be matched by the shorter "gpt-4o" entry.
    assert get_rates("openai/gpt-4o-mini") == (0.15, 0.60)
    assert get_rates("openai/gpt-4o") == (2.50, 10.00)


def test_unknown_model_uses_default():
    assert get_rates("some/unknown-model") == (0.075, 0.30)
    assert is_model_priced("some/unknown-model") is False
    assert is_model_priced("google/gemini-2.5-pro") is True


def test_calculate_cost_math():
    cost = calculate_cost("google/gemini-2.5-pro", 1000, 2000)
    assert cost == pytest.approx((1000 * 0.075 + 2000 * 0.30) / 1_000_000.0)


def test_calculate_cost_handles_none_and_negative():
    assert calculate_cost("m", None, None) == 0.0
    assert calculate_cost("m", -5, -5) == 0.0
