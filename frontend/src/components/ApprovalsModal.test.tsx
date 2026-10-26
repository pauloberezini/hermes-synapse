import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApprovalsModal } from './ApprovalsModal';

const summary = [{
  id: 7,
  agent_id: 'code',
  action_name: 'execute_command',
  description: 'code wants to run execute_command for step 1/2 (code).',
  status: 'PENDING',
  created_at: '2026-10-21T06:00:00Z',
  bundle_hash: 'a'.repeat(64),
  flags: ['tool_result_capped_600'],
  payload: '{"command":"ls"}',
}];

const detail = {
  ...summary[0],
  bundle: {
    plan: { agent: 'code', instructions: 'List files', step_index: 0, step_count: 2 },
    inputs: { command: 'ls' },
    upstream: [
      {
        kind: 'tool_result',
        name: 'web_search',
        excerpt: 'hello',
        sha256: 'b'.repeat(64),
        truncated: true,
        reason: 'tool_result_600',
      },
    ],
    flags: [],
  },
  decisions: [],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.endsWith('/approvals/7/resolve')) {
      return new Response(JSON.stringify({ status: 'success' }), { status: 200 });
    }
    if (url.endsWith('/approvals/7')) {
      return new Response(JSON.stringify(detail), { status: 200 });
    }
    if (url.includes('/approvals')) {
      return new Response(JSON.stringify(summary), { status: 200 });
    }
    return new Response('{}', { status: 404 });
  }) as any;
});

describe('ApprovalsModal', () => {
  it('shows description, not just the tool name', async () => {
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    expect(await screen.findByText(/wants to run execute_command for step 1\/2/)).toBeInTheDocument();
  });

  it('lazy-loads evidence on expand and shows plan + truncation chip', async () => {
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /show evidence #7/i }));
    expect(await screen.findByText('List files')).toBeInTheDocument();
    expect(screen.getAllByText(/tool result capped at 600 chars/i).length).toBeGreaterThanOrEqual(1);
  });

  it('shows explicit empty state when plan is missing', async () => {
    const detailWithoutPlan = {
      ...detail,
      bundle: {
        ...detail.bundle,
        plan: null,
      },
    };
    globalThis.fetch = vi.fn(async (url: string) => {
      if (url.endsWith('/approvals/7')) {
        return new Response(JSON.stringify(detailWithoutPlan), { status: 200 });
      }
      if (url.includes('/approvals')) {
        return new Response(JSON.stringify(summary), { status: 200 });
      }
      return new Response('{}', { status: 404 });
    }) as any;

    render(<ApprovalsModal isOpen onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /show evidence #7/i }));
    expect(await screen.findByText('No planner step attached')).toBeInTheDocument();
  });

  it('approve posts decision + note and calls onResolved', async () => {
    const onResolved = vi.fn();
    render(<ApprovalsModal isOpen onClose={() => {}} onResolved={onResolved} />);
    fireEvent.click(await screen.findByRole('button', { name: /show evidence #7/i }));
    fireEvent.change(await screen.findByPlaceholderText(/resolver note/i), { target: { value: 'ok' } });
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    const call = (fetch as any).mock.calls.find((c: any[]) => c[0].endsWith('/resolve'));
    expect(JSON.parse(call[1].body)).toEqual({ decision: 'APPROVED', resolver_note: 'ok' });
  });

  it('never sends bundle_hash from the client', async () => {
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /show evidence #7/i }));
    fireEvent.click(await screen.findByRole('button', { name: /reject/i }));
    const call = (fetch as any).mock.calls.find((c: any[]) => c[0].endsWith('/resolve'));
    expect(JSON.parse(call[1].body)).not.toHaveProperty('bundle_hash');
  });
});
