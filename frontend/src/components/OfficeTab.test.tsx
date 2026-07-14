import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentModel } from '../types';
import { assignOfficeZone, normalizeOfficeAgents, normalizeOfficeStatus, OfficeTab } from './OfficeTab';

const agents: AgentModel[] = [
  {
    id: 'analyst',
    name: 'Data Analyst',
    role: 'Analytics specialist',
    system_prompt: '',
    model: 'openai/gpt-4.1',
    status: 'working',
    project_id: 'analytics',
    project_name: 'Analytics Platform',
    current_task: 'Analyse product metrics',
    progress: 65,
    updated_at: '2026-07-13 10:42:00',
    recent_events: [{ id: 1, agent_id: 'analyst', timestamp: '2026-07-13 10:42:00', event_type: 'task_started', message: 'Started analytics task', status: 'success' }],
  },
  {
    id: 'reviewer',
    name: 'QA Engineer With An Intentionally Long Display Name',
    role: 'QA',
    system_prompt: '',
    model: 'google/gemini-2.5-flash',
    status: 'waiting',
    project_id: 'analytics',
    project_name: 'Analytics Platform',
    current_task: 'Waiting for build',
  },
];

function mockOfficeResponse(nextAgents: AgentModel[] = agents) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ agents: nextAgents }) }));
}

describe('OfficeTab data adapters', () => {
  it('normalizes unknown and disabled statuses without inventing backend fields', () => {
    const unknown = { id: 'a', name: 'Agent', system_prompt: '', model: 'm', status: 'unexpected' };
    expect(normalizeOfficeStatus(unknown)).toBe('paused');
    expect(normalizeOfficeStatus({ ...unknown, is_enabled: false })).toBe('offline');
    expect(assignOfficeZone({ ...unknown, status: 'error' })).toBe('error');
    expect(normalizeOfficeAgents([unknown], 'Unassigned')[0]).toMatchObject({ projectLabel: 'Unassigned', statusKind: 'paused', zone: 'idle' });
  });
});

describe('OfficeTab interactions', () => {
  beforeEach(() => {
    localStorage.clear();
    mockOfficeResponse();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('filters agents, opens the inspector, and restores it with keyboard controls', async () => {
    render(<OfficeTab t={key => key === 'officeTitle' ? 'ИИ-офис' : key} language="ru" isConnected />);
    const analyst = await screen.findByRole('button', { name: /Data Analyst, Работают/i });
    fireEvent.change(screen.getByLabelText('Поиск агента…'), { target: { value: 'Data Analyst' } });
    expect(screen.queryByText('QA Engineer With An Intentionally Long Display Name')).not.toBeInTheDocument();
    fireEvent.click(analyst);
    expect(screen.getByRole('dialog', { name: 'Data Analyst' })).toBeInTheDocument();
    expect(localStorage.getItem('hermes_office_agent')).toBe('analyst');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('switches modes without refetching and persists the selected view', async () => {
    const { unmount } = render(<OfficeTab t={() => 'ИИ-офис'} language="en" isConnected />);
    await screen.findByText('Data Analyst');
    fireEvent.click(screen.getByRole('tab', { name: 'Command Center' }));
    expect(screen.getByRole('tab', { name: 'Command Center' })).toHaveAttribute('aria-selected', 'true');
    expect(localStorage.getItem('hermes_office_view')).toBe('command');
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: /Project focus: Analytics Platform/i }));
    expect(screen.getByText('Project focus')).toBeInTheDocument();
    unmount();
    render(<OfficeTab t={() => 'ИИ-офис'} language="en" isConnected />);
    expect(screen.getByRole('tab', { name: 'Command Center' })).toHaveAttribute('aria-selected', 'true');
  });

  it('renders a dedicated empty state', async () => {
    mockOfficeResponse([]);
    render(<OfficeTab t={() => 'ИИ-офис'} language="en" />);
    expect(await screen.findByText('The office is empty')).toBeInTheDocument();
  });

  it('keeps the page usable when the initial refresh fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    render(<OfficeTab t={() => 'ИИ-офис'} language="en" />);
    expect(await screen.findByText('Could not refresh data. Retrying in the background.')).toBeInTheDocument();
  });

  it('renders more than fifty agents through the compact accessible view', async () => {
    const manyAgents = Array.from({ length: 55 }, (_, index): AgentModel => ({
      id: `agent-${index}`,
      name: `Scale Agent ${index}`,
      system_prompt: '',
      model: 'test/model',
      status: index % 7 === 0 ? 'error' : 'working',
      project_id: `project-${index % 5}`,
      project_name: `Project ${index % 5}`,
    }));
    localStorage.setItem('hermes_office_view', 'list');
    mockOfficeResponse(manyAgents);
    render(<OfficeTab t={() => 'ИИ-офис'} language="en" isConnected />);
    expect(await screen.findByText('Scale Agent 54')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(55);
  });
});
