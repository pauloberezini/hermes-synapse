import logging

from backend.logging_config import SecretRedactingFilter, redact_secrets


def test_redacts_telegram_token_from_httpx_url():
    message = "POST https://api.telegram.org/bot123456:super-secret/getUpdates"
    assert redact_secrets(message) == (
        "POST https://api.telegram.org/bot<redacted>/getUpdates"
    )


def test_filter_redacts_formatted_log_arguments():
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "HTTP Request: %s",
        ("https://api.telegram.org/bot123:secret/getUpdates",),
        None,
    )

    assert SecretRedactingFilter().filter(record) is True
    assert record.args == ()
    assert "123:secret" not in record.getMessage()
