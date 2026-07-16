"""
Example community skill: GitHub Integration

This file demonstrates how to write a Hermes community skill using
the hermes_sdk decorators. Copy this as a starting template.

To use this skill with Hermes:
1. Place it anywhere in your project
2. Import and register it in backend/tools.py:
   from examples.github_skill import GitHubSkill
3. Or contribute it to the Hermes Skills Marketplace!

OSS Principles demonstrated:
  ✅ API key read from env var (not hardcoded)
  ✅ Graceful degradation when key is missing
  ✅ Self-contained, independently testable
  ✅ No proprietary dependencies (GitHub has a free API)
"""

from hermes_sdk import skill, tool, SkillBase


@skill(
    name="github_integration",
    display_name="GitHub Integration",
    description="Read GitHub issues, pull requests, and repository information",
    version="1.0.0",
    author="your-github-username",
    requires_env=["GITHUB_TOKEN"],
    tags=["development", "productivity"],
)
class GitHubSkill(SkillBase):
    """Community skill for GitHub integration."""

    @tool(description="List open issues in a GitHub repository")
    def list_issues(self, repo: str, state: str = "open") -> str:
        """
        Args:
            repo: Repository in 'owner/repo' format (e.g. 'pauloberezini/hermes-synapse')
            state: Issue state — 'open', 'closed', or 'all'
        """
        import httpx

        token = self.get_env("GITHUB_TOKEN", required=False)
        if not token:
            return self.missing_key_message("GITHUB_TOKEN")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {"state": state, "per_page": 10}

        try:
            response = httpx.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 404:
                return f"❌ Repository '{repo}' not found or no access."
            response.raise_for_status()
            issues = response.json()

            if not issues:
                return f"✅ No {state} issues found in {repo}."

            lines = [f"📋 **{state.title()} Issues in `{repo}`** ({len(issues)} shown):"]
            for issue in issues[:10]:
                lines.append(
                    f"- #{issue['number']} **{issue['title']}** "
                    f"by @{issue['user']['login']}"
                )
            return "\n".join(lines)

        except httpx.HTTPStatusError as e:
            return f"❌ GitHub API error: {e.response.status_code}"
        except Exception as e:
            return f"❌ Failed to fetch issues: {str(e)}"

    @tool(description="Get the README content of a GitHub repository")
    def get_readme(self, repo: str) -> str:
        """
        Args:
            repo: Repository in 'owner/repo' format
        """
        import httpx
        import base64

        token = self.get_env("GITHUB_TOKEN", required=False)
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"https://api.github.com/repos/{repo}/readme"
        try:
            response = httpx.get(url, headers=headers, timeout=10)
            if response.status_code == 404:
                return f"❌ No README found in repository '{repo}'."
            response.raise_for_status()
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            # Truncate to avoid overwhelming the context window
            return content[:3000] + ("\n\n[...truncated]" if len(content) > 3000 else "")
        except Exception as e:
            return f"❌ Failed to fetch README: {str(e)}"
