import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProcessesTab } from './ProcessesTab';

const pendingTask = {
  id: 'T-test123', origin: 'agent', requester: 'dashboard', goal: 'Execute add_calendar_event',
  tool_name: 'add_calendar_event', tool_arguments: { title: 'Review' }, assignee: 'jarvis',
  risk_class: 'R3' as const, autonomy_level: 'L3' as const, data_class: 'Internal',
  status: 'awaiting_approval' as const, approvals_required: 1, approval_count: 0, approval_required: true,
  budget_commands: 1, budget_tokens: 0, budget_wallclock_s: 60, commands_used: 0, tokens_used: 0,
  acceptance: ['Tool returns a valid result'], rollback: 'Delete the calendar event.', result: '', error: '',
  created_at: '2026-07-16T10:00:00Z', updated_at: '2026-07-16T10:00:00Z', completed_at: null,
};

const summary = {
  state: { kill_switch: false, reason: '', updated_by: 'system', updated_at: '2026-07-16T10:00:00Z' },
  counts: { awaiting_approval: 1 }, pending_approvals: [pendingTask], tasks: [pendingTask],
  events: [{ id: 1, evidence_id: 'EV-000001', task_id: pendingTask.id, event_type: 'task_created', actor: 'control-plane', message: 'Tool request classified as R3', risk_class: 'R3', confidence: 'CONFIRMED', output_hash: '', created_at: '2026-07-16T10:00:00Z' }],
  policy: { risk_levels: ['R0', 'R1', 'R2', 'R3', 'R4'], unknown_tools: 'R4', r4_double_confirmation: true },
};

describe('ProcessesTab', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows pending task contract and sends explicit approval', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => summary })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'done' }) })
      .mockResolvedValue({ ok: true, json: async () => ({ ...summary, pending_approvals: [], counts: { done: 1 } }) });
    vi.stubGlobal('fetch', fetchMock);

    render(<ProcessesTab language="en" />);
    expect((await screen.findAllByText('add_calendar_event')).length).toBeGreaterThan(0);
    expect(screen.getByText('EV-000001')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/control-plane/tasks/T-test123/approve',
      expect.objectContaining({ method: 'POST' }),
    ));
  });

  it('requires confirmation before activating the kill switch', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => summary })
      .mockResolvedValue({ ok: true, json: async () => summary });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<ProcessesTab language="en" />);
    fireEvent.click(await screen.findByRole('button', { name: /stop all/i }));
    expect(window.confirm).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
