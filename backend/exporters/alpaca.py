"""
Alpaca format exporter for chat session execution trajectories.
"""
import json
from typing import List, Dict, Any, Union
from backend.exporters.base import BaseExporter


class AlpacaExporter(BaseExporter):
    """Exports session trajectories in standard Alpaca instruction dataset format."""

    @property
    def format_name(self) -> str:
        return "alpaca"

    def export(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        decision_logs: List[Dict[str, Any]],
        extension: str = "jsonl"
    ) -> Union[str, List[Dict[str, Any]]]:
        items = []

        system_instruction = ""
        last_user_message = ""

        for msg in messages:
            role = (msg.get("role") or "").lower()
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role in ("user", "human"):
                last_user_message = content
            elif role in ("assistant", "bot", "gpt") and last_user_message:
                items.append({
                    "instruction": last_user_message,
                    "input": system_instruction,
                    "output": content,
                    "session_id": session_id
                })
                last_user_message = ""

        if extension == "jsonl":
            return "\n".join([json.dumps(item, ensure_ascii=False) for item in items])
        return items
