"""
Base Exporter interface for exporting chat session trajectories into various dataset formats.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union


class BaseExporter(ABC):
    """Abstract base class for trajectory dataset exporters."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Returns the identifier name of the export format (e.g. 'sharegpt')."""
        pass

    @abstractmethod
    def export(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        decision_logs: List[Dict[str, Any]],
        extension: str = "jsonl"
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Exports messages and decision logs for a given session into the target format.

        :param session_id: The ID of the session being exported.
        :param messages: Chronological list of message dicts ({id, role, content, cost_usd, timestamp}).
        :param decision_logs: List of decision logs ({timestamp, model, traces, user_message, assistant_response, ...}).
        :param extension: 'jsonl' (returns newline-delimited JSON string) or 'json' (returns dict/list structure or JSON string).
        :return: Formatted export representation.
        """
        pass
