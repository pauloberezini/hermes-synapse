# 🛡️ Paperclip Governance: Budgeting & Approvals

Hermes Synapse integrates **Paperclip-inspired governance controls** to guarantee safe autonomous subagent operations.

---

## 💰 1. Token & Dollar Budget Caps (`FEAT-1`)

The `BudgetGuard` module tracks LLM API spend in real-time and enforces hard dollar limits before invoking model completion endpoints.

### Spend Summary API
```http
GET /api/governance/budget/session_id
```
Returns:
- Session spend vs. daily session budget
- Global spend vs. global daily and monthly caps

```json
{
  "session_spend_usd": 0.125,
  "session_budget_usd": 5.0,
  "global_daily_spend_usd": 1.42,
  "global_daily_budget_usd": 50.0
}
```

---

## 🙋‍♂️ 2. Human Approval Queue (`FEAT-2`)

High-stakes tool executions (file mutations, terminal commands, database deletes) are intercepted by the `ApprovalQueue` until a human operator approves them.

### Approvals Queue Modal UI
Human operators can review pending actions directly in the Web UI:

```tsx
<ApprovalsModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
```

---

## 🏢 3. Team Archetype Presets (`FEAT-3`)

Deploy pre-configured agent teams with 1 click:
- **Hedge Fund**: CEO + Quantitative Researcher + Python Engineer + Risk Analyst
- **Engineering Shop**: Tech Lead + Backend Developer + QA Tester
- **OSINT Bureau**: Intelligence Director + Web Scraper + Fact Checker

---

## 🎥 Video Tutorial

Watch how to configure spend budgets and approve high-stakes subagent requests:

<YouTube id="3GFh-1Gglno" title="Paperclip Governance Tutorial" />
