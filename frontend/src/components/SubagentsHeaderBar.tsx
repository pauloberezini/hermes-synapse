import { useState, useEffect } from 'react';
import type { AgentThread } from '../types';
import { SkillPill } from './SubagentTreeDrawer';

export interface SubagentsHeaderBarProps {
  currentChatId?: string;
  latestAssistantMessageId?: number;
  fetchWithAuth: (url: string, options?: RequestInit) => Promise<Response>;
}

export function SubagentsHeaderBar({
  latestAssistantMessageId,
  fetchWithAuth,
}: SubagentsHeaderBarProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!latestAssistantMessageId) {
      setThreads([]);
      return;
    }

    let isMounted = true;
    setLoading(true);

    fetchWithAuth(`/api/messages/${latestAssistantMessageId}/agent_threads`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((data) => {
        if (isMounted) {
          setThreads(data.threads || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setThreads([]);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [latestAssistantMessageId, fetchWithAuth]);

  if (!threads || threads.length === 0) {
    return null;
  }

  const totalTokens = threads.reduce(
    (acc, t) => acc + (t.total_tokens || (t.prompt_tokens_estimate || 0) + (t.completion_tokens_estimate || 0)),
    0
  );

  const formatTokens = (tokens: number): string => {
    if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M tok`;
    if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(0)}K tok`;
    return `${tokens} tok`;
  };

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`;
    const sec = ms / 1000;
    if (sec < 60) return `${sec.toFixed(0)}s`;
    const mins = Math.floor(sec / 60);
    const rem = Math.round(sec % 60);
    return `${mins}m ${rem}s`;
  };

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      {/* Top Header Trigger Button */}
      <button
        onClick={() => setDropdownOpen((prev) => !prev)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 10px',
          background: dropdownOpen ? 'rgba(0, 240, 255, 0.18)' : 'rgba(0, 240, 255, 0.08)',
          border: '1px solid rgba(0, 240, 255, 0.35)',
          borderRadius: '6px',
          color: 'var(--accent-cyan, #00f0ff)',
          fontSize: '0.73rem',
          fontWeight: 700,
          fontFamily: 'var(--font-mono, monospace)',
          cursor: 'pointer',
          transition: 'all 0.2s',
          boxShadow: dropdownOpen ? '0 0 10px rgba(0,240,255,0.25)' : 'none',
        }}
        title={loading ? 'Loading active & completed subagents...' : 'View active & completed subagents in this interaction'}
      >
        <span style={{ fontSize: '0.8rem' }}>🗂️</span>
        <span>{threads.length} subagents</span>
        {totalTokens > 0 && (
          <span style={{ color: '#cbd5e1', fontSize: '0.67rem', fontWeight: 500 }}>
            · {formatTokens(totalTokens)}
          </span>
        )}
        <span style={{ fontSize: '0.62rem', opacity: 0.8 }}>{dropdownOpen ? '▲' : '▼'}</span>
      </button>

      {/* Dropdown Menu (DeepSeek Harness style) */}
      {dropdownOpen && (
        <>
          {/* Backdrop overlay for closing */}
          <div
            onClick={() => setDropdownOpen(false)}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 998,
            }}
          />

          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              marginTop: '6px',
              width: '380px',
              maxWidth: '90vw',
              background: 'rgba(15, 23, 42, 0.96)',
              backdropFilter: 'blur(12px)',
              border: '1px solid rgba(0, 240, 255, 0.3)',
              borderRadius: '8px',
              boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5), 0 0 15px rgba(0, 240, 255, 0.1)',
              zIndex: 999,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Header */}
            <div
              style={{
                padding: '8px 12px',
                background: 'rgba(0, 240, 255, 0.08)',
                borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: 'var(--accent-cyan, #00f0ff)',
                  fontFamily: 'var(--font-mono, monospace)',
                  letterSpacing: '0.4px',
                }}
              >
                SUBAGENTS TELEMETRY
              </span>
              <span
                style={{
                  fontSize: '0.67rem',
                  color: '#cbd5e1',
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              >
                {threads.length} active/completed
              </span>
            </div>

            {/* List of subagents */}
            <div
              style={{
                maxHeight: '340px',
                overflowY: 'auto',
                padding: '6px 0',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {threads.map((thread, idx) => {
                const nodeTokens =
                  thread.total_tokens ||
                  (thread.prompt_tokens_estimate || 0) + (thread.completion_tokens_estimate || 0);

                return (
                  <div
                    key={thread.id || idx}
                    style={{
                      padding: '8px 12px',
                      borderBottom:
                        idx < threads.length - 1 ? '1px solid rgba(255, 255, 255, 0.05)' : 'none',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '8px',
                      transition: 'background 0.15s',
                      cursor: 'default',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(0, 240, 255, 0.04)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    {/* Status Dot */}
                    <span
                      style={{
                        marginTop: '3px',
                        display: 'inline-block',
                        width: '7px',
                        height: '7px',
                        borderRadius: '50%',
                        backgroundColor: thread.error ? '#ef4444' : thread.success ? '#10b981' : '#38bdf8',
                        boxShadow: thread.error
                          ? '0 0 5px rgba(239,68,68,0.8)'
                          : thread.success
                          ? '0 0 5px rgba(16,185,129,0.8)'
                          : '0 0 5px rgba(56,189,248,0.8)',
                      }}
                    />

                    {/* Agent details */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
                        <span
                          style={{
                            fontSize: '0.74rem',
                            fontWeight: 700,
                            color: '#f8fafc',
                            fontFamily: 'var(--font-mono, monospace)',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {thread.agent_name || thread.agent_id}
                        </span>

                        {/* Tokens & Latency */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            fontSize: '0.65rem',
                            fontFamily: 'var(--font-mono, monospace)',
                            color: 'var(--text-dim, #94a3b8)',
                          }}
                        >
                          {nodeTokens > 0 && (
                            <span style={{ color: '#cbd5e1', fontWeight: 600 }}>
                              {formatTokens(nodeTokens)}
                            </span>
                          )}
                          {thread.latency_ms > 0 && (
                            <span>{formatDuration(thread.latency_ms)}</span>
                          )}
                        </div>
                      </div>

                      {/* Subagent Prompt / Role preview */}
                      <div
                        style={{
                          fontSize: '0.67rem',
                          color: '#94a3b8',
                          marginTop: '2px',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {thread.role_description || thread.user_message || 'Executing instructions'}
                      </div>

                      {/* Skills badges */}
                      {thread.skills_used && thread.skills_used.length > 0 && (
                        <div style={{ display: 'flex', gap: '3px', marginTop: '4px', flexWrap: 'wrap' }}>
                          {thread.skills_used.map((s) => (
                            <SkillPill key={s} skill={s} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default SubagentsHeaderBar;
