import logging
import re
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(https?://api\.telegram\.org/bot)[^/\s\"']+", re.IGNORECASE),
    re.compile(r"(\bAuthorization\s*:\s*Bearer\s+)[^\s,;\"']+", re.IGNORECASE),
    re.compile(
        r"(\b(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;\"']+",
        re.IGNORECASE,
    ),
)


def redact_secrets(value: Any) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1<redacted>", text)
    return text


class SecretRedactingFilter(logging.Filter):
    """Render the record once, redact it, then prevent unsafe arg reformatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.getMessage())
        record.args = ()
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    redactor = SecretRedactingFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, SecretRedactingFilter) for item in handler.filters):
            handler.addFilter(redactor)

