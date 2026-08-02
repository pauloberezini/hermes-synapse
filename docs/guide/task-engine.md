# 🎯 Task Engine, Kanban & Heartbeat Pulse

Hermes Synapse features an **Atomic Task Engine** and **Resumable Heartbeat Pulse Engine** for coordinating long-running multi-agent pipelines.

---

## 📋 1. Atomic Task Checkout & Locks (`FEAT-5`)

Subagents claim tickets atomically from the `tasks` queue:
```http
POST /api/tasks/{task_id}/checkout
Content-Type: application/json

{
  "agent_id": "code_engineer",
  "lock_duration_seconds": 300
}
```
If another subagent attempts to check out the same task during the lock window, the request receives an `HTTP 409 Conflict` (`status: "locked"`).

---

## ⚡ 2. Heartbeat Pulse & Checkpoints (`FEAT-6`)

Long-running agent orchestrations step through execution windows (pulses):
1. **Load Checkpoint**: Agent loads state from `tasks.checkpoint_data`.
2. **Execute Steps**: Agent executes up to `N` steps.
3. **Save Checkpoint**: Agent serializes updated `AgentState` back to DB and sleeps until next pulse.

### Manual Pulse Trigger API
```http
POST /api/tasks/{task_id}/pulse?max_steps=1
```

---

## 🏢 3. Org Hierarchy Escalation Routing (`FEAT-4`)

If a task fails 3 consecutive times, `AgentMeshRouter` automatically escalates the ticket to its manager node (`reporting_role`: `Director` or `CEO`):

```python
router.escalate_task(task_id=42, failed_agent_id="worker_bot")
```

---

## 🎥 Video Tutorial

See the Kanban Board and Heartbeat Pulse Engine in action:

<YouTube id="3GFh-1Gglno" title="Kanban Board and Resumable Pulse Engine" />
