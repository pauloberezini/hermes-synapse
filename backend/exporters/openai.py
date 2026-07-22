"""
OpenAI messages format exporter for chat session execution trajectories.
"""
import json
from typing import List, Dict, Any, Union
from backend.exporters.base import BaseExporter


class OpenAIExporter(BaseExporter):
    """Exports session trajectories in standard OpenAI Messages JSONL format."""

    @property
    def format_name(self) -> str:
        return "openai"

    def _map_role(self, role: str) -> str:
        role_lower = (role or "").lower()
        if role_lower in ("user", "human"):
            return "user"
        elif role_lower in ("assistant", "bot", "gpt"):
            return "assistant"
        elif role_lower == "system":
            return "system"
        return "user"

    def export(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        decision_logs: List[Dict[str, Any]],
        extension: str = "jsonl"
    ) -> Union[str, Dict[str, Any]]:
        formatted_messages = []
        for msg in messages:
            role = self._map_role(msg.get("role", ""))
            content = msg.get("content", "")
            formatted_messages.append({"role": role, "content": content})

        data = {
            "id": session_id,
            "messages": formatted_messages
        }

        if extension == "jsonl":
            return json.dumps(data, ensure_ascii=False)
        return data
