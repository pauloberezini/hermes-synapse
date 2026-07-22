"""
ShareGPT format exporter for chat session execution trajectories.
"""
import json
from typing import List, Dict, Any, Union
from backend.exporters.base import BaseExporter


class ShareGPTExporter(BaseExporter):
    """Exports session trajectories in standard ShareGPT format."""

    @property
    def format_name(self) -> str:
        return "sharegpt"

    def _map_role(self, role: str) -> str:
        role_lower = (role or "").lower()
        if role_lower in ("user", "human"):
            return "human"
        elif role_lower in ("assistant", "bot", "gpt"):
            return "gpt"
        elif role_lower == "system":
            return "system"
        elif role_lower in ("thought", "reasoning"):
            return "thought"
        elif role_lower in ("tool_call", "tool"):
            return "tool_call"
        elif role_lower == "tool_response":
            return "tool_response"
        return role_lower or "human"

    def export(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        decision_logs: List[Dict[str, Any]],
        extension: str = "jsonl"
    ) -> Union[str, Dict[str, Any]]:
        conversations = []

        # Index decision logs by user message or sequence to correlate traces
        decision_map = {}
        for log in decision_logs:
            user_msg = (log.get("user_message") or "").strip()
            if user_msg and user_msg not in decision_map:
                decision_map[user_msg] = log

        for msg in messages:
            role = self._map_role(msg.get("role", ""))
            content = msg.get("content", "")

            # If user message has corresponding decision log traces, inject thought/tool traces if available
            if role == "human" and content.strip() in decision_map:
                dec_log = decision_map[content.strip()]
                conversations.append({"from": "human", "value": content})

                traces = dec_log.get("traces") or []
                for trace in traces:
                    if isinstance(trace, dict):
                        t_type = trace.get("type", "thought")
                        t_msg = trace.get("message") or trace.get("content") or json.dumps(trace)
                        conversations.append({
                            "from": self._map_role(t_type),
                            "value": str(t_msg)
                        })
                    elif isinstance(trace, str) and trace:
                        conversations.append({"from": "thought", "value": trace})
                continue

            conversations.append({"from": role, "value": content})

        data = {
            "id": session_id,
            "conversations": conversations
        }

        if extension == "jsonl":
            return json.dumps(data, ensure_ascii=False)
        return data
