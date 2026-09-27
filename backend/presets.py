"""
backend/presets.py — Team Archetype Presets (Paperclip-inspired Blueprints)

Provides 1-click multi-agent team setups for Hermes Synapse.
"""

from typing import List, Dict, Any

TEAM_PRESETS: Dict[str, Dict[str, Any]] = {
    "engineering_shop": {
        "id": "engineering_shop",
        "title": "Full-Stack Software Engineering Shop",
        "description": "An autonomous engineering desk featuring Tech Lead, Python Engineer, Frontend Developer, and Security Auditor.",
        "icon": "Code",
        "agents": [
            {
                "id": "tech_lead",
                "name": "Software Tech Lead",
                "system_prompt": "You are the Technical Architect. Break down software requirements into modules, review code PRs, and ensure system scalability.",
                "model": "ollama/llama3",
                "agent_type": "sub-orchestrator",
                "parent_id": "jarvis",
                "skills": "python_sandbox,shell_execution",
                "x": 200, "y": 450, "temperature": 0.4
            },
            {
                "id": "backend_dev",
                "name": "Backend Python Developer",
                "system_prompt": "You write clean, modular Python backend code. Implement APIs, database models, and write comprehensive pytest test suites.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "tech_lead",
                "skills": "python_sandbox,shell_execution",
                "x": 450, "y": 400, "temperature": 0.3
            },
            {
                "id": "security_auditor",
                "name": "Security & Code Auditor",
                "system_prompt": "You audit code for vulnerability vectors, static analysis lint issues, and verify compliance with open-source guardrails.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "tech_lead",
                "skills": "shell_execution",
                "x": 450, "y": 550, "temperature": 0.1
            }
        ]
    },
    "osint_bureau": {
        "id": "osint_bureau",
        "title": "OSINT & Research Intelligence Bureau",
        "description": "A deep research team for real-time web intelligence gathering, news digests, and knowledge vault archiving.",
        "icon": "Search",
        "agents": [
            {
                "id": "intel_director",
                "name": "Intelligence Director",
                "system_prompt": "You direct open-source intelligence gathering. Cross-examine findings across multiple news feeds and archive structured briefings in Obsidian.",
                "model": "ollama/llama3",
                "agent_type": "sub-orchestrator",
                "parent_id": "jarvis",
                "skills": "web_search,obsidian_rag",
                "x": 200, "y": 750, "temperature": 0.3
            },
            {
                "id": "news_scout",
                "name": "Web OSINT Scout",
                "system_prompt": "You scrape public RSS feeds, web articles, and search engines for real-time breaking news and domain updates.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "intel_director",
                "skills": "web_search",
                "x": 450, "y": 700, "temperature": 0.5
            },
            {
                "id": "obsidian_archivist",
                "name": "Obsidian Vault Archivist",
                "system_prompt": "You index research notes into Obsidian markdown notes with structured tags and taxonomy folders.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "intel_director",
                "skills": "obsidian_rag",
                "x": 450, "y": 850, "temperature": 0.2
            }
        ]
    },
    "devops_desk": {
        "id": "devops_desk",
        "title": "DevOps & QA Engineering Desk",
        "description": "An autonomous CI/CD, issue triage, and test automation team with Issue Triager, Unit Test Generator, and PR Code Reviewer.",
        "icon": "GitPullRequest",
        "agents": [
            {
                "id": "devops_lead",
                "name": "DevOps Team Lead",
                "system_prompt": "You are the DevOps & QA Team Lead. Coordinate continuous integration, issue triage, test generation, and pull request audits. Delegate tasks to specialized DevOps sub-agents.",
                "model": "ollama/llama3",
                "agent_type": "sub-orchestrator",
                "parent_id": "jarvis",
                "skills": "shell_execution,python_sandbox",
                "x": 200, "y": 1050, "temperature": 0.3
            },
            {
                "id": "issue_triager",
                "name": "GitHub Issue Triager",
                "system_prompt": "You analyze bug reports and feature requests. Categorize issues, score severity, reproduce errors, and suggest targeted fixes.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "devops_lead",
                "skills": "web_search,shell_execution",
                "x": 450, "y": 1000, "temperature": 0.2
            },
            {
                "id": "test_generator",
                "name": "Automated Test Generator",
                "system_prompt": "You generate comprehensive unit, integration, and regression test suites using pytest and vitest. Ensure high coverage and verify edge cases.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "devops_lead",
                "skills": "python_sandbox,shell_execution",
                "x": 450, "y": 1150, "temperature": 0.2
            },
            {
                "id": "pr_reviewer",
                "name": "PR Code Reviewer",
                "system_prompt": "You perform rigorous code reviews on diffs and pull requests. Audit for code quality, architectural compliance, security risks, and open-source guardrails.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "devops_lead",
                "skills": "python_sandbox,shell_execution",
                "x": 450, "y": 1300, "temperature": 0.1
            }
        ]
    },
    "cybersec_redteam": {
        "id": "cybersec_redteam",
        "title": "Cybersecurity & Red Team",
        "description": "An autonomous security auditing team with CISO, Vulnerability Scanner, and Static Code Analyzer.",
        "icon": "ShieldAlert",
        "agents": [
            {
                "id": "ciso_lead",
                "name": "CISO & Security Lead",
                "system_prompt": "You are the Chief Information Security Officer. Coordinate security audits, review vulnerability reports, and ensure compliance with open-source guardrails.",
                "model": "ollama/llama3",
                "agent_type": "sub-orchestrator",
                "parent_id": "jarvis",
                "skills": "shell_execution",
                "x": 200, "y": 1350, "temperature": 0.2
            },
            {
                "id": "vuln_scanner",
                "name": "Vulnerability Scanner",
                "system_prompt": "You run security scanning tools (like pip-audit, npm audit, nmap) to detect CVEs and misconfigurations in local environments.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "ciso_lead",
                "skills": "shell_execution",
                "x": 450, "y": 1300, "temperature": 0.1
            },
            {
                "id": "static_analyzer",
                "name": "Static Code Analyzer",
                "system_prompt": "You run SAST tools (like Bandit, Semgrep) on local repositories to detect hardcoded secrets and dangerous code patterns.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "ciso_lead",
                "skills": "shell_execution",
                "x": 450, "y": 1450, "temperature": 0.1
            }
        ]
    },
    "customer_ops_desk": {
        "id": "customer_ops_desk",
        "title": "Customer Ops & Support Desk",
        "description": "An automated L1/L2 support team for ticket triage, RAG knowledge retrieval, and response drafting.",
        "icon": "Headset",
        "agents": [
            {
                "id": "support_lead",
                "name": "Support Operations Lead",
                "system_prompt": "You coordinate the customer support desk. Route tickets to triagers and ensure drafted responses are accurate before submitting to the ApprovalQueue.",
                "model": "ollama/llama3",
                "agent_type": "sub-orchestrator",
                "parent_id": "jarvis",
                "skills": "obsidian_rag",
                "x": 200, "y": 1650, "temperature": 0.3
            },
            {
                "id": "ticket_triager",
                "name": "Ticket Triager",
                "system_prompt": "You analyze incoming user queries and categorize their severity, urgency, and topic.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "support_lead",
                "skills": "",
                "x": 450, "y": 1600, "temperature": 0.4
            },
            {
                "id": "knowledge_retriever",
                "name": "Knowledge Base Retriever",
                "system_prompt": "You search vector memory and RAG databases for relevant documentation to answer user queries.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "support_lead",
                "skills": "obsidian_rag",
                "x": 450, "y": 1750, "temperature": 0.1
            }
        ]
    }
}




def _all_presets() -> Dict[str, Dict[str, Any]]:
    from backend.plugins import collect
    merged = dict(TEAM_PRESETS)
    for extra in collect("get_team_presets"):
        if isinstance(extra, dict):
            merged.update(extra)
    return merged


def list_presets() -> List[Dict[str, Any]]:
    """Return summary list of available team blueprints."""
    return [
        {
            "id": k,
            "title": v["title"],
            "description": v["description"],
            "agent_count": len(v["agents"]),
        }
        for k, v in _all_presets().items()
    ]


def load_preset(preset_id: str) -> bool:
    """Save all subagents from the chosen preset into the database."""
    preset = _all_presets().get(preset_id)
    if not preset:
        return False
    from backend.database import save_subagent
    for agent in preset["agents"]:
        save_subagent(
            id=agent["id"],
            name=agent["name"],
            system_prompt=agent["system_prompt"],
            model=agent["model"],
            agent_type=agent["agent_type"],
            parent_id=agent["parent_id"],
            skills=agent["skills"],
            x=agent["x"],
            y=agent["y"],
            temperature=agent["temperature"],
        )
    return True
