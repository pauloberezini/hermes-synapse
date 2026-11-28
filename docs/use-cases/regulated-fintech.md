---
title: Regulated fintech and trading
description: How Hermes Synapse approvals and its decision log map to the Israel Securities Authority draft directive on AI, and what they do not cover.
---

# Regulated fintech and trading

This page is for licensed teams that let AI agents get near client accounts or orders, and that will be asked how a human stayed in control. I wrote it around the Israel Securities Authority (ISA) draft directive on AI. Nothing here is legal advice, and Hermes does not make anyone compliant.

## What the ISA draft proposes

On 4 November 2026 the ISA published a draft directive on technological means and AI for licensed investment advisers, marketers and portfolio managers. Comments close on 6 December 2026. As I read the draft, it proposes four things that matter for agents:

- The licensee sets its own criteria for when a human must review or approve.
- The licensee keeps documentation of the service for seven years, in a form it can retrieve.
- Using a technological tool does not reduce the licensee's liability.
- The ISA asks the public whether AI agents create risks the draft does not address.

All of this is proposed text and can change. The directive covers licensees. A prop shop trading its own capital, or a bank, may fall outside it. Read the source before you rely on my summary.

## Where agents already reach orders

cTrader publishes official MCP servers. An agent in Claude Code or Cursor can use them to place, modify and close orders on a trading account. Hermes does not sit in front of those clients. Approvals cover agents running in Hermes, including their calls to external MCP tools such as cTrader, through Hermes's MCP client. The ISA draft does not mention cTrader. The overlap is that an agent with a live order connection is exactly the case a human-involvement criterion has to describe.

## What Hermes does today

| The draft asks, as proposed | What Hermes does | What it does not do |
|---|---|---|
| Criteria for when a human approves | High-risk tools and MCP tools that are not marked read-only wait for a person. You choose which tools those are. | No policy language. The list lives in code and plugins. |
| Documentation kept and retrievable | Every request, approval, rejection and use is a row in an append-only log. Export gives a zip with the rows, the evidence and a manifest. | Retention periods and backups are yours to run. |
| Who approved what | Each decision stores the approver's subject, roles and login method, and a hash of the exact payload. | The approve endpoint does not check roles. You cannot yet limit approval to a named group. |
| Proof the record was not edited | A SHA-256 chain with database triggers against UPDATE and DELETE, and an offline verifier. | The verifier needs a pinned head hash to catch a full rewrite. The log is not signed. |

## What Hermes does not do

- It does not decide whether an order is suitable for a client. It checks nothing about the content of a call.
- BudgetGuard caps LLM spend. It does not cap order size or market exposure.
- Code Engineer and Data Analyst `execute_code` waits at the same gate as other high-risk tools. Set `CODE_AGENTS_ENABLED=false` to disable the sandbox.
- Approvals cover agents running in Hermes, including their calls to external MCP tools such as cTrader. There is no gateway in front of Claude Code, Cursor or other MCP clients.
- It does not keep the register of technological tools that the draft proposes.

## What a pilot looks like

A design-partner pilot runs for 8 to 10 weeks on a demo account first.

1. Weeks 1 and 2: connect one agent and one tool that can change something, for example a cTrader MCP server on a demo account. Agree which calls wait for a person.
2. Weeks 3 to 6: run real workflows. Tune the list, read the pending queue together, and count how many approvals were useful and how many were noise.
3. Weeks 7 to 10: export the log, verify it offline, and write a short document that maps the log fields to the questions your compliance officer expects. I write it with your compliance lead. I do not offer it as a legal opinion or a certification.

If you run agents in a licensed firm in Israel and want to be one of the first three, [talk to me](https://www.linkedin.com/in/pauloberezini/).

## Sources

- ISA draft directive (Hebrew, 4 November 2026): https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-6283705a39f5d/Draft_tech_AI_publiccomment.pdf
- cTrader AI agent connection: https://help.ctrader.com/ctrader-ai-agent-connect/
- Hermes security model: [Security model](/guide/security)
- Approvals walkthrough: [Approvals](/guide/approvals)
