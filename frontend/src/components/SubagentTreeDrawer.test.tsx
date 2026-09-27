import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SubagentTreeDrawer, SkillPill } from './SubagentTreeDrawer';
import type { AgentThread } from '../types';

describe('SubagentTreeDrawer Component (DeepSeek Harness style)', () => {
  const mockThreads: AgentThread[] = [
    {
      id: 101,
      agent_id: 'research',
      agent_name: 'Search Agent',
      model: 'deepseek-v4-flash',
      role_description: 'You are a research agent searching the internet.',
      user_message: 'Search for recent Bitcoin and Ethereum price updates',
      assistant_response: 'BTC is at $95,000, ETH is at $3,400.',
      reasoning_content: 'Let me search duckduckgo first. Querying BTC/ETH live prices.',
      skills_used: ['web_search'],
      tool_calls_log: [
        {
          name: 'web_search',
          args: { query: 'BTC ETH price 2026' },
          result: 'BTC $95,000 | ETH $3,400',
          skill: 'web_search',
        },
      ],
      prompt_tokens_estimate: 150,
      completion_tokens_estimate: 200,
      total_tokens: 350,
      latency_ms: 1250,
      cost_usd: 0.000045,
      timestamp: '10:00:00',
      success: true,
      error: null,
    },
    {
      id: 102,
      agent_id: 'code',
      agent_name: 'Code Engineer',
      model: 'deepseek-v4-flash',
      role_description: 'You are a Python code engineer.',
      user_message: 'Calculate percentage spread between BTC and ETH',
      assistant_response: 'The ratio is 27.94.',
      reasoning_content: 'Running python script: print(95000 / 3400)',
      skills_used: ['python_sandbox'],
      tool_calls_log: [
        {
          name: 'python_sandbox',
          args: { code: 'print(95000 / 3400)' },
          result: '27.941176470588236',
          skill: 'python_sandbox',
        },
      ],
      prompt_tokens_estimate: 80,
      completion_tokens_estimate: 120,
      total_tokens: 200,
      latency_ms: 850,
      cost_usd: 0.000025,
      timestamp: '10:00:02',
      success: true,
      error: null,
    },
  ];

  it('renders Communication Link button and expands on click', async () => {
    const fetchWithAuth = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ threads: mockThreads, message_id: 1 }),
    });

    render(<SubagentTreeDrawer messageId={1} fetchWithAuth={fetchWithAuth} />);

    const button = screen.getByRole('button', { name: /Communication Link/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith('/api/messages/1/agent_threads');
    });

    // Check header and agents rendered
    await waitFor(() => {
      expect(screen.getByText(/SUBAGENTS COMMUNICATION & REASONING TREE/i)).toBeInTheDocument();
      expect(screen.getByText('Search Agent')).toBeInTheDocument();
      expect(screen.getByText('Code Engineer')).toBeInTheDocument();
    });

    // Check skill pills rendered
    expect(screen.getAllByText('web_search').length).toBeGreaterThan(0);
    expect(screen.getAllByText('python_sandbox').length).toBeGreaterThan(0);

    // Click Expand All to open reasoning accordions
    const expandAllBtn = screen.getByRole('button', { name: /Expand All/i });
    fireEvent.click(expandAllBtn);

    // Check thought process reasoning is rendered
    expect(screen.getAllByText(/Agent Thought Process & Reasoning/i).length).toBe(2);
    expect(screen.getByText(/Querying BTC\/ETH live prices/i)).toBeInTheDocument();

    // Check raw output is rendered
    expect(screen.getByText(/BTC is at \$95,000, ETH is at \$3,400\./i)).toBeInTheDocument();
  });

  it('renders individual SkillPill with icon and styling', () => {
    render(<SkillPill skill="web_search" />);
    expect(screen.getByText('web_search')).toBeInTheDocument();
    expect(screen.getByText('🌐')).toBeInTheDocument();
  });
});
