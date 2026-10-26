from backend.evidence import (
    EvidenceContext,
    PlanRef,
    build_bundle,
    bundle_hash,
    cap_bundle,
    redact_bundle,
)


def _ctx():
    c = EvidenceContext(plan=PlanRef(agent="code", instructions="Run ls in /tmp", step_index=0, step_count=2))
    c.add_tool_result("web_search", "result body", capped_at=None)
    return c


def test_bundle_without_context_flags_plan_missing():
    b = build_bundle("chat1", "execute_command", {"cmd": "ls"}, None)
    assert b.plan is None and b.upstream == []
    assert "plan_missing" in b.flags


def test_hash_stable_across_excerpt_recut():
    b1 = build_bundle("c", "execute_command", {"cmd": "ls"}, _ctx())
    b2 = b1.model_copy(deep=True)
    b2.upstream[0].excerpt = "different cut"
    assert bundle_hash(b1) == bundle_hash(b2)


def test_hash_changes_when_upstream_body_changes():
    c1, c2 = _ctx(), _ctx()
    c2.upstream[0].sha256 = "0" * 64
    assert bundle_hash(build_bundle("c", "x", {}, c1)) != bundle_hash(build_bundle("c", "x", {}, c2))


def test_description_is_not_tool_name():
    b = build_bundle("chat1", "execute_command", {"cmd": "ls"}, _ctx())
    assert b.description != "execute_command"
    assert "step 1/2" in b.description and "code" in b.description


def test_pii_redacted_in_inputs_and_upstream():
    c = EvidenceContext()
    c.add_tool_result("read", "mail me at a@b.com key sk-abcdefghijklmnopqrstu")
    tok = "eyJhbGciOiJIUzI1NiJ9.payloadpart.signature"  # ≥20 chars: PIIGuard BEARER_TOKEN
    b = redact_bundle(build_bundle("c", "execute_command", {"cmd": f"curl -H 'Authorization: Bearer {tok}'"}, c))
    dumped = b.model_dump_json()
    assert "a@b.com" not in dumped and "sk-abcdefghijklmnop" not in dumped and tok not in dumped


def test_excerpt_capped_and_flagged():
    c = EvidenceContext()
    c.add_tool_result("read", "x" * 10_000)
    b = cap_bundle(build_bundle("c", "x", {}, c))
    assert len(b.upstream[0].excerpt.encode()) <= 4096
    assert b.upstream[0].truncated and b.upstream[0].reason == "char_cap_4k"


def test_total_cap_drops_oldest_but_keeps_hashes():
    c = EvidenceContext()
    for i in range(40):
        c.add_tool_result(f"t{i}", "y" * 4000)
    b = cap_bundle(build_bundle("c", "x", {}, c))
    assert len(b.model_dump_json().encode()) <= 65536
    assert "upstream_dropped" in b.flags
    assert all(u.sha256 for u in b.upstream)


def test_tool_result_600_cap_flag_propagates():
    c = EvidenceContext()
    c.add_tool_result("t", "z" * 600, capped_at=600)
    assert "tool_result_capped_600" in build_bundle("c", "x", {}, c).flags
