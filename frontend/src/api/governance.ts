import type { ApprovalDetail, ApprovalSummary } from '../types';

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('jarvis_auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function listApprovals(pendingOnly: boolean = false): Promise<ApprovalSummary[]> {
  const res = await fetch(`/api/governance/approvals${pendingOnly ? '?pending_only=true' : ''}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to list approvals: ${res.status}`);
  return res.json();
}

export async function getApproval(id: number): Promise<ApprovalDetail> {
  const res = await fetch(`/api/governance/approvals/${id}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to get approval #${id}: ${res.status}`);
  return res.json();
}

export async function resolveApproval(
  id: number,
  decision: 'APPROVED' | 'REJECTED',
  note: string = '',
  reason?: string,
): Promise<{ status: string; id: number; decision: string }> {
  const res = await fetch(`/api/governance/approvals/${id}/resolve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({
      decision,
      resolver_note: note || reason || '',
    }),
  });
  if (!res.ok) throw new Error(`Failed to resolve approval #${id}: ${res.status}`);
  return res.json();
}

export async function pendingCount(): Promise<number> {
  const res = await fetch('/api/governance/approvals/count', {
    headers: authHeaders(),
  });
  if (!res.ok) return 0;
  const data = await res.json();
  return typeof data?.count === 'number' ? data.count : 0;
}
