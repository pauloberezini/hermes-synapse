"""
Exporters module for trajectory dataset export.
"""
from typing import Dict, Type
from backend.exporters.base import BaseExporter
from backend.exporters.sharegpt import ShareGPTExporter
from backend.exporters.openai import OpenAIExporter
from backend.exporters.alpaca import AlpacaExporter

_EXPORTERS: Dict[str, Type[BaseExporter]] = {
    "sharegpt": ShareGPTExporter,
    "openai": OpenAIExporter,
    "alpaca": AlpacaExporter,
}


def get_exporter(format_name: str = "sharegpt") -> BaseExporter:
    """
    Factory function to retrieve an exporter instance by format name.
    Defaults to ShareGPTExporter if format is unknown or unsupported.
    """
    key = (format_name or "sharegpt").lower().strip()
    exporter_cls = _EXPORTERS.get(key, ShareGPTExporter)
    return exporter_cls()
