"""
backend/presets.py — Team Archetype Presets (Paperclip-inspired Blueprints)

Provides 1-click multi-agent team setups for Hermes Synapse:
  1. Financial Trading & Hedge Fund
  2. Full-Stack Software Engineering Shop
  3. OSINT & Intelligence Bureau
"""

from typing import List, Dict, Any

TEAM_PRESETS: Dict[str, Dict[str, Any]] = {
    "hedge_fund": {
        "id": "hedge_fund",
        "title": "Financial Hedge Fund & Trading Desk",
        "description": "A quantitative trading team with Market Analyst, Risk Compliance Officer, and Automated Execution Trader.",
        "icon": "TrendingUp",
        "agents": [
            {
                "id": "fund_lead",
                "name": "Portfolio Manager",
                "system_prompt": "You are the Chief Investment Officer. Synthesize market data, evaluate risk scores, and authorize asset allocations. Delegate research to analysts.",
                "model": "ollama/llama3",
                "agent_type": "sub-orchestrator",
                "parent_id": "jarvis",
                "skills": "market_monitor,bcm",
                "x": 200, "y": 150, "temperature": 0.3
            },
            {
                "id": "quant_analyst",
                "name": "Quant Market Analyst",
                "system_prompt": "You are a Quantitative Market Analyst. Track live crypto/equity metrics, technical indicators (RSI, ATR, Keltner), and report market anomalies.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "fund_lead",
                "skills": "market_monitor,web_search",
                "x": 450, "y": 100, "temperature": 0.2
            },
            {
                "id": "risk_compliance",
                "name": "Risk & Compliance Officer",
                "system_prompt": "You are the Risk Officer. Verify drawdowns, validate stop-loss/take-profit parameters, and enforce strict hard trading limits.",
                "model": "ollama/llama3",
                "agent_type": "agent",
                "parent_id": "fund_lead",
                "skills": "bcm",
                "x": 450, "y": 250, "temperature": 0.1
            }
        ]
    },
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
    }
}


def list_presets() -> List[Dict[str, Any]]:
    """Return summary list of available team blueprints."""
    return [
        {
            "id": k,
            "title": v["title"],
            "description": v["description"],
            "agent_count": len(v["agents"]),
        }
        for k, v in TEAM_PRESETS.items()
    ]


def load_preset(preset_id: str) -> bool:
    """Save all subagents from the chosen preset into the database."""
    preset = TEAM_PRESETS.get(preset_id)
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
