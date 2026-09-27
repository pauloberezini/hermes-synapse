import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import App from './App';

// Mock WebSockets
let lastWs: MockWebSocket | null = null;
class MockWebSocket {
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: any) => void) | null = null;
  send = vi.fn();
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    lastWs = this;
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 10);
  }
}

vi.stubGlobal('WebSocket', MockWebSocket);

function stubAuthenticatedFetch() {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/api/config')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ system_prompt: 'System prompt', model: 'gpt-4' }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve([]),
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function fireWs(payload: Record<string, unknown>) {
  lastWs?.onmessage?.({ data: JSON.stringify(payload) });
}

describe('App Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    lastWs = null;
  });

  it('renders login screen when unauthenticated', async () => {
    render(<App />);
    expect(screen.getByText('SYNAPSE')).toBeInTheDocument();
    expect(screen.getByText(/Secure Access Link/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /request code in telegram/i })).toBeInTheDocument();
  });

  it('requests OTP and shows confirmation message', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success' })
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    
    const requestButton = screen.getByRole('button', { name: /request code in telegram/i });
    fireEvent.click(requestButton);

    expect(screen.getByText(/sending code/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/authorization code sent to your trusted telegram chat/i)).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/auth\/request-code$/), expect.any(Object));
  });

  it('renders main application when authenticated', async () => {
    localStorage.setItem('jarvis_auth_token', 'mock_token');
    
    const fetchMock = vi.fn().mockImplementation((url) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ system_prompt: 'System prompt', model: 'gpt-4' })
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([])
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Communication Link')).toBeInTheDocument();
    });

    const settingsBtn = screen.getByText('Settings');
    fireEvent.click(settingsBtn);

    await waitFor(() => {
      expect(screen.getByText('Core Parameters')).toBeInTheDocument();
    });
  });

  it('persists mic and voice (TTS) toggle states in localStorage', async () => {
    localStorage.setItem('jarvis_auth_token', 'mock_token');
    localStorage.setItem('jarvis_mic_enabled', 'true');
    localStorage.setItem('jarvis_tts_enabled', 'false');

    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([])
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Communication Link')).toBeInTheDocument();
    });

    // Check that pre-set localStorage values were loaded into UI
    expect(screen.getByText(/mic on/i)).toBeInTheDocument();
    expect(screen.getByText(/voice off/i)).toBeInTheDocument();

    // Toggle voice on
    const voiceBtn = screen.getByRole('button', { name: /voice off/i });
    fireEvent.click(voiceBtn);

    expect(localStorage.getItem('jarvis_tts_enabled')).toBe('true');
  });

  it('does not paint orchestrator traces from another session into the open chat', async () => {
    localStorage.setItem('jarvis_auth_token', 'mock_token');
    stubAuthenticatedFetch();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Greetings, Sir/)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(typeof lastWs?.onmessage).toBe('function');
    });

    act(() => {
      fireWs({
        type: 'trace_update',
        session_id: 'task_ops_cron',
        trace: {
          agent: 'Orchestrator',
          action: 'Start',
          message: "Received query for 'ops_orchestrator': 'Execute scheduled task: System Prompt: Nightly Ops Digest'",
          status: 'success',
        },
      });
    });

    expect(
      screen.queryByText(/Execute scheduled task: System Prompt: Nightly Ops Digest/)
    ).not.toBeInTheDocument();

    act(() => {
      fireWs({
        type: 'trace_update',
        session_id: 'dashboard',
        trace: {
          agent: 'Orchestrator',
          action: 'Planning',
          message: 'Plan of 3 steps generated.',
          status: 'success',
        },
      });
    });

    expect(screen.getByText(/Plan of 3 steps generated/)).toBeInTheDocument();
  });
});
