1. RBAC is not wired. The approve endpoint does not check roles. Any logged-in session can approve. Each decision records the approver's subject and login method, with the roles.
2. The log is tamper-evident when you pin its head hash. This sample pack does not include signed checkpoints; the zip log carries no signatures.
3. No SOC 2 or other certification. One maintainer. No named customers.
4. Approvals cover agents running in Hermes, including their calls to external MCP tools. There is no gateway in front of Claude Code or Cursor, or in front of other MCP clients.
5. Code agents are off by default. When switched on, each `execute_code` call waits for an approval tied to the exact source.
6. Raw tool arguments remain in `approval_requests.payload` for matching. Evidence and HTTP responses are masked (R2-4).
7. `bundle_hash` does not cover the description, the links or the excerpts.
8. A rejected call stays rejected for that session with no cooldown (R2-2).
9. Secret redaction matches known formats and nothing else. There is no policy language and no built-in criteria such as order size.
10. The log covers gated actions and approval events, not every conversation turn. Seven-year retention and backups are the buyer's job.
11. The sample is built from a scripted agent with a mocked shell and sandbox.
