"""
backend/tools/github_ci.py — Open-Source Git / GitHub CI Action Tool

Provides a safe, local wrapper around Git CLI and open REST APIs
to allow DevOps agents to inspect code, commit, and create PRs autonomously.
"""

import os
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("hermes.github_ci")

class GitCIWrapper:
    
    @staticmethod
    def _run_git(command: list, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Runs a git CLI command safely."""
        try:
            cmd = ["git"] + command
            result = subprocess.run(
                cmd,
                cwd=cwd or os.getcwd(),
                capture_output=True,
                text=True,
                check=False
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "code": result.returncode
            }
        except Exception as e:
            logger.error(f"[GitCIWrapper] Execution error: {e}")
            return {"status": "error", "error": str(e)}

    @classmethod
    def get_status(cls, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Gets the git status."""
        return cls._run_git(["status", "-s"], cwd)

    @classmethod
    def get_diff(cls, cached: bool = False, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Gets the git diff (unstaged or staged)."""
        cmd = ["diff"]
        if cached:
            cmd.append("--cached")
        return cls._run_git(cmd, cwd)

    @classmethod
    def create_branch(cls, branch_name: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Creates and checks out a new branch."""
        return cls._run_git(["checkout", "-b", branch_name], cwd)

    @classmethod
    def commit_changes(cls, message: str, add_all: bool = True, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Commits changes (optionally adding all modifications first)."""
        if add_all:
            add_res = cls._run_git(["add", "."], cwd)
            if add_res["status"] == "error":
                return add_res
        return cls._run_git(["commit", "-m", message], cwd)

    @classmethod
    def push_branch(cls, branch_name: str, remote: str = "origin", cwd: Optional[str] = None) -> Dict[str, Any]:
        """Pushes a branch to the remote."""
        return cls._run_git(["push", "-u", remote, branch_name], cwd)
