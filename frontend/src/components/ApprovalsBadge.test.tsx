import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApprovalsBadge } from './ApprovalsBadge';

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string) => {
    if (url.endsWith('/approvals/count')) {
      return new Response(JSON.stringify({ count: 3 }), { status: 200 });
    }
    return new Response('{}', { status: 404 });
  }) as any;
});

describe('ApprovalsBadge', () => {
  it('renders count from /count', async () => {
    render(<ApprovalsBadge onOpen={() => {}} />);
    expect(await screen.findByText('3')).toBeInTheDocument();
  });

  it('hides number when zero', async () => {
    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ count: 0 }), { status: 200 });
    }) as any;
    render(<ApprovalsBadge onOpen={() => {}} />);
    await waitFor(() => {
      expect(screen.queryByTestId('approvals-count')).not.toBeInTheDocument();
    });
  });

  it('refetches count on window approval_update without waiting for the poll', async () => {
    let countVal = 1;
    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ count: countVal }), { status: 200 });
    }) as any;

    render(<ApprovalsBadge onOpen={() => {}} />);
    expect(await screen.findByText('1')).toBeInTheDocument();

    countVal = 4;
    window.dispatchEvent(new CustomEvent('approval_update'));

    expect(await screen.findByText('4')).toBeInTheDocument();
  });

  it('keeps the count pill outside the fading label', async () => {
    render(<ApprovalsBadge onOpen={() => {}} />);
    const pill = await screen.findByTestId('approvals-count');
    const label = screen.getByText('Approvals');
    expect(label.className).toContain('sidebar-label');
    expect(pill.closest('.sidebar-label')).toBeNull();
  });

  it('click opens modal', async () => {
    const onOpen = vi.fn();
    render(<ApprovalsBadge onOpen={onOpen} />);
    fireEvent.click(screen.getByRole('button', { name: /approvals/i }));
    expect(onOpen).toHaveBeenCalled();
  });
});
