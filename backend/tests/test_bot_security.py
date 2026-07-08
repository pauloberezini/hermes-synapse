import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from telegram.ext import ContextTypes
import os

from backend.bot import admin_only

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
            "Access denied, Sir. I only respond to my designated Creator."
        )
