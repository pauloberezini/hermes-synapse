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

  it('refreshes on approval_update websocket message', async () => {
    let messageListener: ((e: MessageEvent) => void) | null = null;
    const fakeWs = {
      addEventListener: vi.fn((event: string, cb: any) => {
        if (event === 'message') messageListener = cb;
      }),
      removeEventListener: vi.fn(),
    } as unknown as WebSocket;

    let countVal = 1;
    globalThis.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ count: countVal }), { status: 200 });
    }) as any;

    render(<ApprovalsBadge onOpen={() => {}} ws={fakeWs} />);
    expect(await screen.findByText('1')).toBeInTheDocument();

    countVal = 4;
    messageListener!({ data: JSON.stringify({ type: 'approval_update', id: 9, status: 'REQUESTED' }) } as MessageEvent);

    expect(await screen.findByText('4')).toBeInTheDocument();
  });

  it('click opens modal', async () => {
    const onOpen = vi.fn();
    render(<ApprovalsBadge onOpen={onOpen} />);
    fireEvent.click(screen.getByRole('button', { name: /approvals/i }));
    expect(onOpen).toHaveBeenCalled();
  });
});
