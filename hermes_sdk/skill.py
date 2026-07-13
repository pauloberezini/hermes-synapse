"""
hermes_sdk.skill — Decorator API for authoring Hermes community skills.

Provides @skill and @tool decorators that wrap a Python class into a
Hermes-compatible skill with auto-generated SkillManifest and OpenAI
tool schemas.

OSS Principles enforced:
  - No hardcoded credentials: use self.get_env() with graceful degradation
  - Modular: each skill is an independent, installable Python class
  - Locally testable: see hermes_sdk.testing for MockHermesContext
"""

import os
import inspect
import functools
import logging
from typing import Any, Callable, get_type_hints

from hermes_sdk.types import SkillManifest, ToolSchema, ToolParameter

logger = logging.getLogger("hermes_sdk.skill")

# Global registry: skill_name → SkillManifest
_SKILL_REGISTRY: dict[str, SkillManifest] = {}


def get_registry() -> dict[str, SkillManifest]:
    """Return the global in-memory skill registry."""
    return _SKILL_REGISTRY


def _python_type_to_json_schema_type(annotation) -> str:
    """Map Python type annotations to JSON Schema type strings."""
    if annotation in (str, "str"):
        return "string"
    if annotation in (int, "int"):
        return "integer"
    if annotation in (float, "float"):
        return "number"
    if annotation in (bool, "bool"):
        return "boolean"
    if annotation in (list, "list"):
        return "array"
    if annotation in (dict, "dict"):
        return "object"
    return "string"  # safe default


def tool(
    description: str,
    required_params: list[str] | None = None,
):
    """
    Decorator to mark a SkillBase method as an LLM-callable tool.

    Args:
        description: Human-readable description for the LLM prompt.
        required_params: List of required parameter names. Defaults to all non-self params.

    Example:
        @tool(description="Fetch current weather for a city")
        def get_weather(self, city: str, units: str = "celsius") -> str:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        fn._is_hermes_tool = True
        fn._tool_description = description
        fn._required_params = required_params
        return fn
    return decorator


class SkillBase:
    """
    Base class for all Hermes community skills.

    Subclass this and decorate your methods with @tool to create a skill
    that can be registered with Hermes.

    The class must be decorated with @skill at the class level.

    OSS Best Practices:
        - Use self.get_env("MY_KEY", required=False) for API key access
        - Return a helpful message string (not raise) when keys are missing
        - Keep each tool function focused and independently testable
    """

    _manifest: SkillManifest  # injected by @skill decorator

    def get_env(self, key: str, required: bool = True, default: str = "") -> str:
        """
        Safely read an environment variable.

        If required=True and the key is missing, logs a warning.
        Always returns a string — never raises. Skill methods should
        check the return value and return a user-friendly message.

        Args:
            key: Environment variable name (e.g. "MY_SERVICE_API_KEY")
            required: If True, logs a warning when missing
            default: Value to return if the env var is not set

        Returns:
            The env var value, or `default` if not found.
        """
        value = os.environ.get(key, default).strip()
        if required and not value:
            logger.warning(
                "Skill '%s': required env var '%s' is not set. "
                "Set it in .env to enable this tool.",
                self._manifest.name, key,
            )
        return value

    def missing_key_message(self, key: str) -> str:
        """
        Standard message to return when an API key is missing.
        Use this for consistent user-facing error messages.

        Example:
            def my_tool(self, query: str) -> str:
                api_key = self.get_env("MY_API_KEY", required=False)
                if not api_key:
                    return self.missing_key_message("MY_API_KEY")
                ...
        """
        return (
            f"⚠️ **{self._manifest.display_name}** is not configured. "
            f"Set `{key}` in your `.env` file to enable this tool.\n"
            f"See `.env.example` for instructions."
        )


def skill(
    name: str,
    display_name: str = "",
    description: str = "",
    version: str = "0.1.0",
    author: str = "",
    requires_env: list[str] | None = None,
    optional_env: list[str] | None = None,
    tags: list[str] | None = None,
):
    """
    Class decorator to register a SkillBase subclass as a Hermes skill.

    Automatically inspects all @tool-decorated methods, extracts their
    signatures, and builds a SkillManifest + ToolSchema list.

    Args:
        name: Unique snake_case skill identifier (e.g. "github_integration")
        display_name: Human-readable label shown in the dashboard UI
        description: Short description of what this skill does
        version: Semantic version string
        author: GitHub username of the skill author
        requires_env: List of required environment variable names
        optional_env: List of optional environment variable names
        tags: Categorization tags (e.g. ["productivity", "communication"])

    Example:
        @skill(
            name="slack_notifier",
            display_name="Slack Notifier",
            description="Post messages and files to Slack channels",
            requires_env=["SLACK_BOT_TOKEN"],
            tags=["communication"],
        )
        class SlackNotifierSkill(SkillBase):

            @tool(description="Post a message to a Slack channel")
            def post_message(self, channel: str, message: str) -> str:
                ...
    """
    def decorator(cls):
        if not issubclass(cls, SkillBase):
            raise TypeError(f"@skill can only decorate subclasses of SkillBase, got: {cls}")

        _display_name = display_name or name.replace("_", " ").title()
        _requires_env = requires_env or []
        _optional_env = optional_env or []
        _tags = tags or []

        # Auto-extract @tool methods
        tool_schemas: list[ToolSchema] = []
        for method_name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not getattr(method, "_is_hermes_tool", False):
                continue

            try:
                hints = get_type_hints(method)
            except Exception:
                hints = {}

            sig = inspect.signature(method)
            required_params = method._required_params

            params: list[ToolParameter] = []
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                annotation = hints.get(param_name, str)
                json_type = _python_type_to_json_schema_type(annotation)
                has_default = param.default is not inspect.Parameter.empty
                is_required = (
                    not has_default
                    if required_params is None
                    else param_name in required_params
                )
                params.append(ToolParameter(
                    name=param_name,
                    type=json_type,
                    description=f"Parameter: {param_name}",
                    required=is_required,
                    default=param.default if has_default else None,
                ))

            tool_schemas.append(ToolSchema(
                name=method_name,
                description=method._tool_description,
                parameters=params,
            ))
            logger.debug("Registered tool: %s.%s", name, method_name)

        # Build and attach the manifest
        manifest = SkillManifest(
            name=name,
            display_name=_display_name,
            description=description,
            version=version,
            author=author,
            requires_env=_requires_env,
            optional_env=_optional_env,
            tools=tool_schemas,
            tags=_tags,
        )

        cls._manifest = manifest

        # Register globally
        _SKILL_REGISTRY[name] = manifest
        logger.info(
            "Hermes skill registered: '%s' (%d tools)",
            name, len(tool_schemas),
        )

        return cls

    return decorator
