"""Redacted, capped snapshot of why an approval was requested.

Pipeline: build → redact → cap → hash. The hash binds what a reviewer can see.
Excluded from the hash: description, excerpt, links, step_context.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.canonical import canonical_json, sha256_hex

_EXCERPT_CAP = 4096
_BUNDLE_CAP = 65536


class UpstreamItem(BaseModel):
    kind: Literal["plan_step", "tool_result", "document"]
    name: str
    excerpt: str
    sha256: str
    truncated: bool = False
    reason: Optional[str] = None


class PlanRef(BaseModel):
    agent: str
    instructions: str
    step_index: int
    step_count: int


class EvidenceBundle(BaseModel):
    schema_ver: Literal[1] = 1
    description: str = ""
    agent_id: str
    action_name: str
    inputs: dict = Field(default_factory=dict)
    step_context: Optional[str] = None
    plan: Optional[PlanRef] = None
    upstream: list[UpstreamItem] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    links: dict = Field(default_factory=dict)


@dataclass
class EvidenceContext:
    plan: Optional[PlanRef] = None
    step_context: Optional[str] = None
    upstream: list[UpstreamItem] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    def add_tool_result(self, name: str, body: str, *, capped_at: int | None = None) -> None:
        text = body if isinstance(body, str) else str(body)
        self.upstream.append(UpstreamItem(
            kind="tool_result",
            name=name,
            excerpt=text,
            sha256=sha256_hex(text),
            truncated=capped_at is not None,
            reason=f"tool_result_{capped_at}" if capped_at else None,
        ))
        if capped_at is not None:
            self.flags.add(f"tool_result_capped_{capped_at}")

    def add_step_result(self, agent: str, body: str, *, truncated: bool) -> None:
        text = body if isinstance(body, str) else str(body)
        self.upstream.append(UpstreamItem(
            kind="plan_step",
            name=agent,
            excerpt=text,
            sha256=sha256_hex(text),
            truncated=truncated,
            reason="step_context_3000" if truncated else None,
        ))
        if truncated:
            self.flags.add("step_output_truncated")


evidence_ctx: ContextVar[Optional[EvidenceContext]] = ContextVar("evidence_ctx", default=None)


def describe(b: EvidenceBundle) -> str:
    text = f"{b.agent_id} wants to run {b.action_name}"
    if b.plan is not None:
        text += f" for step {b.plan.step_index + 1}/{b.plan.step_count} ({b.plan.agent})"
        text += ": " + (b.plan.instructions or "")[:140]
    return text + "."


def build_bundle(agent_id, action_name, payload, ctx: EvidenceContext | None) -> EvidenceBundle:
    flags = set(ctx.flags) if ctx else set()
    plan = ctx.plan if ctx else None
    if plan is None:
        flags.add("plan_missing")
    bundle = EvidenceBundle(
        agent_id=agent_id,
        action_name=action_name,
        inputs=dict(payload or {}),
        step_context=ctx.step_context if ctx else None,
        plan=plan,
        upstream=list(ctx.upstream) if ctx else [],
        flags=sorted(flags),
    )
    bundle.description = describe(bundle)
    return bundle


def _mask_tree(value, mask):
    if isinstance(value, str):
        return mask(value)[0]
    if isinstance(value, list):
        return [_mask_tree(v, mask) for v in value]
    if isinstance(value, dict):
        return {k: _mask_tree(v, mask) for k, v in value.items()}
    return value


def redact_bundle(b: EvidenceBundle) -> EvidenceBundle:
    from backend.governance import MemoryGuard, PIIGuard

    out = EvidenceBundle.model_validate(_mask_tree(b.model_dump(), PIIGuard.mask_pii))
    for item in out.upstream:
        if item.kind == "document":
            item.excerpt = MemoryGuard.audit_text(item.excerpt, source="upload")["clean_text"]
        item.sha256 = sha256_hex(item.excerpt)
    return out


def _truncate_utf8(text: str, max_bytes: int) -> tuple[str, bool]:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False
    raw = raw[:max_bytes]
    while raw:
        try:
            return raw.decode("utf-8"), True
        except UnicodeDecodeError:
            raw = raw[:-1]
    return "", True


def cap_bundle(b: EvidenceBundle, *, per_item: int = _EXCERPT_CAP, total: int = _BUNDLE_CAP) -> EvidenceBundle:
    out = b.model_copy(deep=True)
    reason = "char_cap_4k" if per_item == _EXCERPT_CAP else f"char_cap_{per_item}"
    for item in out.upstream:
        excerpt, cut = _truncate_utf8(item.excerpt or "", per_item)
        if cut:
            item.excerpt = excerpt
            item.truncated = True
            item.reason = reason
    while out.upstream and len(out.model_dump_json().encode()) > total:
        out.upstream.pop(0)  # ponytail: drop oldest; a byte budget beats keeping every excerpt
        out.flags = sorted(set(out.flags) | {"upstream_dropped"})
    return out


def hash_view(b: EvidenceBundle) -> dict:
    plan = None
    if b.plan is not None:
        plan = {
            "agent": b.plan.agent,
            "instructions": b.plan.instructions,
            "step_index": b.plan.step_index,
            "step_count": b.plan.step_count,
        }
    return {
        "schema_ver": b.schema_ver,
        "agent_id": b.agent_id,
        "action_name": b.action_name,
        "inputs": b.inputs,
        "plan": plan,
        "upstream": [
            {
                "kind": u.kind,
                "name": u.name,
                "sha256": u.sha256,
                "truncated": u.truncated,
                "reason": u.reason,
            }
            for u in b.upstream
        ],
        "flags": sorted(set(b.flags)),
    }


def bundle_hash(b: EvidenceBundle) -> str:
    return sha256_hex(canonical_json(hash_view(b)))
