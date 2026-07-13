"""
hermes_sdk.types — Core type definitions for Hermes skill authoring.

These types describe the manifest format that Hermes uses to register
community skills and expose their tools to LLM agents.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """A single parameter in a tool's JSON Schema definition."""

    name: str
    type: str  # "string" | "integer" | "number" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    enum: list[str] | None = None
    default: Any = None

    def to_json_schema(self) -> dict:
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class ToolSchema:
    """
    OpenAI-compatible tool schema for a single callable function.
    This is what Hermes registers with the LLM for function calling.
    """

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_openai_schema(self) -> dict:
        """Serialize to OpenAI function-calling format."""
        properties = {p.name: p.to_json_schema() for p in self.parameters}
        required = [p.name for p in self.parameters if p.required]
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class SkillManifest:
    """
    Metadata descriptor for a Hermes community skill.

    This manifest is auto-generated from the @skill decorator and
    registered with Hermes at startup (or via the Skills Marketplace).

    Example:
        SkillManifest(
            name="github_integration",
            display_name="GitHub Integration",
            description="Read/write GitHub issues, PRs, and commits",
            version="1.0.0",
            author="your-github-username",
            requires_env=["GITHUB_TOKEN"],
            tools=[...],
        )
    """

    name: str                          # snake_case skill ID (unique)
    display_name: str                  # Human-readable label in the UI
    description: str                   # Short description shown in dashboard
    version: str = "0.1.0"
    author: str = ""                   # GitHub username or org
    requires_env: list[str] = field(default_factory=list)  # Required env vars
    optional_env: list[str] = field(default_factory=list)  # Optional env vars
    tools: list[ToolSchema] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)          # e.g. ["productivity", "communication"]

    def to_registry_entry(self) -> dict:
        """Serialize to the format expected by backend/tools.py SKILLS_REGISTRY."""
        return {
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "requires_env": self.requires_env,
            "optional_env": self.optional_env,
            "tools": [t.name for t in self.tools],
            "tool_schemas": [t.to_openai_schema() for t in self.tools],
            "tags": self.tags,
        }
