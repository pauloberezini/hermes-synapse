"""
Hermes SDK — Community Plugin & Skill Authoring Library

Write your own Hermes skills (tool sets) with a simple decorator API,
then contribute them to the Hermes Skills Marketplace.

Usage example:
    from hermes_sdk import skill, tool, SkillBase

    @skill(name="my_integration", description="My custom integration")
    class MyIntegrationSkill(SkillBase):

        @tool(description="Fetch something from my service")
        def fetch_data(self, query: str) -> str:
            api_key = self.get_env("MY_SERVICE_API_KEY", required=False)
            if not api_key:
                return "⚠️ MY_SERVICE_API_KEY is not configured. Set it in .env to enable this tool."
            # ... your implementation
            return f"Result for {query}"

Installation (once published):
    pip install hermes-sdk

For local development, add to PYTHONPATH:
    export PYTHONPATH=/path/to/hermes-synapse
    from hermes_sdk import skill, tool, SkillBase
"""

from hermes_sdk.skill import skill, tool, SkillBase
from hermes_sdk.types import SkillManifest, ToolSchema, ToolParameter

__all__ = [
    "skill",
    "tool",
    "SkillBase",
    "SkillManifest",
    "ToolSchema",
    "ToolParameter",
]

__version__ = "0.1.0"
