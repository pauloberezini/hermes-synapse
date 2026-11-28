---
title: Hermes Synapse vs Microsoft Agent Governance Toolkit vs LangGraph human-in-the-loop vs a Slack button
description: Where Hermes Synapse fits next to Microsoft Agent Governance Toolkit, LangGraph human-in-the-loop, and a Slack button you wrote.
---

# Hermes Synapse vs Microsoft Agent Governance Toolkit vs LangGraph human-in-the-loop vs a Slack button

These four solve neighbouring problems, and I would not pick Hermes for all of them. This page is my attempt to say where each one fits. Facts about the other tools come from their own docs and source, linked below, as of 28 November 2026. Where I have not checked something, the table says so. Microsoft ships changes to AGT often, so check its repository before you decide.

| | Hermes Synapse | Microsoft Agent Governance Toolkit | LangGraph human-in-the-loop | A Slack button you wrote |
|---|---|---|---|---|
| What it is | A self-hosted app: agent orchestrator, approval screen and decision log | A toolkit of seven packages: policy engine, identity, runtime controls, compliance mapping | Middleware that pauses a LangGraph run until a person responds | A script and a webhook |
| Cost and license | Free, MIT | Free, MIT | Free, open source | Your time |
| Ready-made approval screen | Yes: a pending queue with source view and payload hash | No universal operator UI, per AGT's own architecture notes; you connect an approval service | No: you build the screen and the notifications | Whatever you built |
| Approval tied to the exact call, usable once | Yes. Hash of the redacted payload; consumed once; a replay is a new request | Yes, in its newer approval coordinator (ADR 0030, code in `agentmesh/governance/approval_protocol`): a SHA-256 digest over the exact action, expiry, one-time consumption and staged approvers. The older callback and webhook paths still exist, and the ADR says strong assurance needs durable storage and a verified approver identity | In effect yes: the decision applies to the one paused call, and you can approve, edit or reject it. Replay protection and the record around it are yours to build | Rarely |
| Tamper-evident log | Hash chain with database triggers against UPDATE and DELETE, plus export and an offline verifier | A hash-chained audit logger is documented (TypeScript package), and approval entries are hash-linked. The ADR notes that some audit fields in spec v1.0 are not covered by the entry hash | Not part of it; state lives in your checkpointer | No |
| Rules about who or what needs approval | A fixed list of high-risk tools plus MCP tool annotations. No policy language | YAML, Rego and Cedar policies with named approvers | A per-tool setting in code | In your script |
| Works with agents you already run | Only agents running in Hermes, including their calls to external MCP tools. No gateway in front of Claude Code, Cursor or other MCP clients | Yes: wraps tools from LangChain, CrewAI, OpenAI Agents SDK, AutoGen and others | Only LangGraph | Yes |
| Roles, SSO, multi-tenant | Role checks exist in code but are not wired to routes yet | Identity and trust features in the toolkit (I have not tested them) | Up to you | No |
| Support and track record | One maintainer, 29 GitHub stars on 28 Nov 2026, no public customer references | Microsoft project, 6,619 stars on 28 Nov 2026 (I did not check for a paid support option) | Part of the LangChain project | None |

## When Hermes is the wrong choice

- You already run agents on LangGraph, CrewAI or the OpenAI Agents SDK and cannot move them. Use AGT, or LangGraph interrupts if you are on LangGraph.
- You need one policy language across many frameworks. AGT does that and Hermes does not.
- You need enforced roles, such as a separate approver group, this quarter. Role checks exist in the code and are not wired to routes yet.
- The risky action is code the agent writes. Generated Python runs outside Hermes's gate today.
- You need a signed, non-repudiable log or a vendor with a support contract. Hermes has neither.
- You already run AGT and only need approvals. Its coordinator already covers exact-action approvals that expire. Hermes would add a screen. It would also add one more system to run.
- You need access control by user, shadow-agent discovery or SSO across a whole company. Gateway and identity products such as Runlayer, Mintive and Okta for AI Agents work on that layer. Hermes does not.
- One person approves their own low-risk actions. A Slack button is fine, and cheaper.

## When Hermes is a good fit

- A small team, agents that can change something you would have to explain later (money, production systems, customer data), and a reviewer or auditor who will ask "who approved exactly what".
- You are happy to run the agents in Hermes and want the approval screen, the log and the offline verifier in one Docker Compose file on day one. AGT has deeper policy and wider framework coverage. Hermes has the screen and the verifier already built.
- You want to read what you run: over 20,000 lines of backend Python, MIT licensed.

## Sources

- [AGT repository](https://github.com/microsoft/agent-governance-toolkit)
- [AGT approval workflow tutorial](https://microsoft.github.io/agent-governance-toolkit/tutorials/38-approval-workflows/)
- [AGT action-bound approval ADR 0030](https://microsoft.github.io/agent-governance-toolkit/adr/0030-action-bound-approval-protocol/)
- [AGT approval coordinator source](https://github.com/microsoft/agent-governance-toolkit/blob/main/agent-governance-python/agent-mesh/src/agentmesh/governance/approval_protocol/coordinator.py)
- [AGT OWASP reference architecture, known gap on operator UI](https://microsoft.github.io/agent-governance-toolkit/compliance/owasp-agentic-top10-architecture/)
- [AGT TypeScript AuditLogger](https://microsoft.github.io/agent-governance-toolkit/tutorials/20-typescript-sdk/)
- [AGT launch blog (seven packages, policy languages, frameworks)](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/)
- [LangGraph human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [Hermes Synapse security model](https://pauloberezini.github.io/hermes-synapse/guide/security.html)
