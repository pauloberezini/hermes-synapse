import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from telegram.ext import ContextTypes
import os

from backend.bot import admin_only, init_bot

@pytest.mark.asyncio
async def test_admin_only_authorized():
    with patch.dict(os.environ, {"TELEGRAM_ADMIN_ID": "216199859,12345678"}):
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 216199859
        update.message = AsyncMock()
        
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        called = False
        @admin_only
        async def dummy_handler(up, ctx):
            nonlocal called
            called = True
            
        await dummy_handler(update, context)
        assert called is True
        update.message.reply_text.assert_not_called()

@pytest.mark.asyncio
async def test_admin_only_unauthorized():
    with patch.dict(os.environ, {"TELEGRAM_ADMIN_ID": "216199859,12345678"}):
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 999999999
        update.message = AsyncMock()
        
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        called = False
        @admin_only
        async def dummy_handler(up, ctx):
            nonlocal called
            called = True
            
        await dummy_handler(update, context)
        assert called is False
        update.message.reply_text.assert_called_once_with(
            "Access denied. I only respond to my designated Creator."
        )

@pytest.mark.asyncio
async def test_placeholder_telegram_token_logs_disabled_and_does_not_crash(caplog, monkeypatch):
    """`.env.example` stub must not raise during startup (that restart-loops the backend)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "your_telegram_bot_token_here")
    with caplog.at_level(logging.INFO, logger="hermes.bot"):
        result = await init_bot()
    assert result is None
    assert "telegram disabled" in caplog.text.lower()


@pytest.mark.asyncio
async def test_telegram_error_handler_conflict():
    from backend.bot import telegram_error_handler
    from telegram.error import Conflict
    
    update = MagicMock(spec=Update)
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.error = Conflict("Conflict: terminated by other getUpdates request")
    
    # Should catch and log conflict error without raising exception
    await telegram_error_handler(update, context)
