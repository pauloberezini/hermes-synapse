import { useState } from 'react';
import type { AgentThread, ToolCallLog } from '../types';

export interface SubagentTreeDrawerProps {
  messageId?: number;
  fetchWithAuth: (url: string, options?: RequestInit) => Promise<Response>;
}

// ─── Skill Colors & Icons Mapping ──────────────────────────────────────────
export const SKILL_METADATA: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  web_search:         { bg: 'rgba(0,240,255,0.08)',   border: 'rgba(0,240,255,0.3)',  text: '#00f0ff', icon: '🌐' },
  python_sandbox:     { bg: 'rgba(56,189,248,0.08)',  border: 'rgba(56,189,248,0.3)', text: '#38bdf8', icon: '🐍' },
  charts:             { bg: 'rgba(236,72,153,0.08)',  border: 'rgba(236,72,153,0.3)', text: '#ec4899', icon: '📊' },
  market_monitor:     { bg: 'rgba(255,159,0,0.08)',   border: 'rgba(255,159,0,0.3)',  text: '#ff9f00', icon: '📈' },
  obsidian_rag:       { bg: 'rgba(167,139,250,0.1)',  border: 'rgba(167,139,250,0.3)',text: '#a78bfa', icon: '📓' },
  todoist_sync:       { bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.3)', text: '#10b981', icon: '✅' },
  google_calendar:    { bg: 'rgba(52,211,153,0.08)',  border: 'rgba(52,211,153,0.3)', text: '#34d399', icon: '📅' },
  timers_alarms:      { bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.3)', text: '#f59e0b', icon: '⏱' },
  shell_execution:    { bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.3)',  text: '#ef4444', icon: '💻' },
  read_rss_node_feed: { bg: 'rgba(251,146,60,0.08)',  border: 'rgba(251,146,60,0.3)', text: '#fb923c', icon: '📰' },
  agent_management:   { bg: 'rgba(129,140,248,0.08)', border: 'rgba(129,140,248,0.3)',text: '#818cf8', icon: '🤖' },
  agent_delegation:   { bg: 'rgba(129,140,248,0.08)', border: 'rgba(129,140,248,0.3)',text: '#818cf8', icon: '🔀' },
};

export function SkillPill({ skill }: { skill: string }) {
  const meta = SKILL_METADATA[skill] || {
    bg: 'rgba(148,163,184,0.08)',
    border: 'rgba(148,163,184,0.25)',
    text: '#94a3b8',
    icon: '⚡'
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '0.66rem',
        fontWeight: 600,
        fontFamily: 'var(--font-mono, monospace)',
        padding: '2px 7px',
        borderRadius: '4px',
        backgroundColor: meta.bg,
        border: `1px solid ${meta.border}`,
        color: meta.text,
        letterSpacing: '0.2px',
      }}
      title={`Skill: ${skill}`}
    >
      <span style={{ fontSize: '0.7rem' }}>{meta.icon}</span>
      <span>{skill}</span>
    </span>
  );
}

function formatTokens(tokens?: number): string {
  if (!tokens || tokens <= 0) return '0 tok';
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M tok`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}K tok`;
  return `${tokens} tok`;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const remainingSec = Math.round(seconds % 60);
  return `${mins}m ${remainingSec}s`;
}

interface SubagentNodeProps {
  thread: AgentThread;
  index?: number;
  isNested?: boolean;
  expandedTools: Set<string>;
  toggleTool: (key: string) => void;
  expandedReasoning: Set<number>;
  toggleReasoning: (id: number) => void;
  expandedNode: boolean;
  toggleNode: (id: number) => void;
}

function SubagentNode({
  thread,
  isNested = false,
  expandedTools,
  toggleTool,
  expandedReasoning,
  toggleReasoning,
  expandedNode,
  toggleNode,
}: SubagentNodeProps) {
  const isReasoningOpen = expandedReasoning.has(thread.id);
  const totalTokens = thread.total_tokens || (thread.prompt_tokens_estimate || 0) + (thread.completion_tokens_estimate || 0);

  return (
    <div
      style={{
        marginLeft: isNested ? '18px' : '0px',
        borderLeft: isNested ? '2px solid rgba(0,240,255,0.25)' : 'none',
        paddingLeft: isNested ? '12px' : '0px',
        marginTop: '6px',
        marginBottom: '6px',
      }}
    >
      {/* Node Container */}
      <div
        style={{
          background: 'rgba(15, 23, 42, 0.75)',
          border: '1px solid rgba(0, 240, 255, 0.18)',
          borderRadius: '8px',
          overflow: 'hidden',
          transition: 'border-color 0.2s, background 0.2s',
          boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
        }}
      >
        {/* Node Header */}
        <div
          onClick={() => toggleNode(thread.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 12px',
            cursor: 'pointer',
            background: expandedNode ? 'rgba(0, 240, 255, 0.06)' : 'rgba(0,0,0,0.2)',
            borderBottom: expandedNode ? '1px solid rgba(0, 240, 255, 0.12)' : 'none',
            userSelect: 'none',
          }}
        >
          {/* Tree connector glyph */}
          <span style={{ color: 'var(--accent-cyan, #00f0ff)', fontFamily: 'monospace', fontSize: '0.8rem', opacity: 0.7 }}>
            {isNested ? '└──' : '├──'}
          </span>

          {/* Status Dot */}
          <span
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: thread.error ? '#ef4444' : thread.success ? '#10b981' : '#38bdf8',
              boxShadow: thread.error
                ? '0 0 6px rgba(239,68,68,0.8)'
                : thread.success
                ? '0 0 6px rgba(16,185,129,0.8)'
                : '0 0 6px rgba(56,189,248,0.8)',
            }}
            title={thread.error ? `Error: ${thread.error}` : 'Completed successfully'}
          />

          {/* Agent Title & ID */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--accent-cyan, #00f0ff)',
                fontFamily: 'var(--font-mono, monospace)',
              }}
            >
              {thread.agent_name || thread.agent_id}
            </span>

            {/* Role Snippet */}
            {thread.role_description && (
              <span
                style={{
                  fontSize: '0.67rem',
                  color: 'rgba(203, 213, 225, 0.7)',
                  fontStyle: 'italic',
                  maxWidth: '220px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={thread.role_description}
              >
                — {thread.role_description}
              </span>
            )}
          </div>

          {/* Skills Badges */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap', marginLeft: '4px' }}>
            {(thread.skills_used || []).map((sk) => (
              <SkillPill key={sk} skill={sk} />
            ))}
          </div>

          {/* Right Metrics: Tokens, Duration, Cost */}
          <div
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '0.67rem',
              fontFamily: 'var(--font-mono, monospace)',
              color: 'var(--text-dim, #94a3b8)',
            }}
          >
            {totalTokens > 0 && (
              <span style={{ color: '#cbd5e1', fontWeight: 600 }}>
                {formatTokens(totalTokens)}
              </span>
            )}

            {thread.latency_ms > 0 && (
              <span>⏱ {formatDuration(thread.latency_ms)}</span>
            )}

            {thread.cost_usd > 0 && (
              <span style={{ color: '#10b981' }}>
                ${thread.cost_usd.toFixed(5)}
              </span>
            )}

            <span style={{ fontSize: '0.65rem', opacity: 0.7 }}>
              {expandedNode ? '▲' : '▼'}
            </span>
          </div>
        </div>

        {/* Node Body Details */}
        {expandedNode && (
          <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* 1. Sub-task Prompt */}
            {thread.user_message && (
              <div
                style={{
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '6px',
                  padding: '7px 10px',
                }}
              >
                <div
                  style={{
                    fontSize: '0.66rem',
                    fontWeight: 700,
                    color: 'rgba(255, 159, 0, 0.9)',
                    textTransform: 'uppercase',
                    marginBottom: '3px',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  📥 Sub-task Prompt / Directive
                </div>
                <div
                  style={{
                    fontSize: '0.74rem',
                    color: '#e2e8f0',
                    fontFamily: 'var(--font-mono, monospace)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {thread.user_message}
                </div>
              </div>
            )}

            {/* 2. Thoughts & Reasoning (<think> / Chain of Thought) */}
            {thread.reasoning_content && (
              <div
                style={{
                  background: 'rgba(167, 139, 250, 0.05)',
                  border: '1px solid rgba(167, 139, 250, 0.25)',
                  borderRadius: '6px',
                  overflow: 'hidden',
                }}
              >
                <button
                  onClick={() => toggleReasoning(thread.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    width: '100%',
                    padding: '6px 10px',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: '#c084fc',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  <span>🧠</span>
                  <span>Agent Thought Process & Reasoning (<code style={{ fontSize: '0.68rem', color: '#e9d5ff' }}>&lt;think&gt;</code>)</span>
                  <span style={{ marginLeft: 'auto', fontSize: '0.62rem', opacity: 0.8 }}>
                    {isReasoningOpen ? '▲ Hide Thoughts' : '▼ Expand Thoughts'}
                  </span>
                </button>

                {isReasoningOpen && (
                  <div
                    style={{
                      padding: '8px 10px 10px 10px',
                      borderTop: '1px solid rgba(167, 139, 250, 0.15)',
                      fontSize: '0.73rem',
                      lineHeight: '1.45',
                      color: '#ddd6fe',
                      fontFamily: 'var(--font-mono, monospace)',
                      whiteSpace: 'pre-wrap',
                      maxHeight: '220px',
                      overflowY: 'auto',
                      background: 'rgba(0,0,0,0.25)',
                    }}
                  >
                    {thread.reasoning_content}
                  </div>
                )}
              </div>
            )}

            {/* 3. Tool Calls & Skills Invocations */}
            {thread.tool_calls_log && thread.tool_calls_log.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <div
                  style={{
                    fontSize: '0.66rem',
                    fontWeight: 700,
                    color: 'rgba(56, 189, 248, 0.9)',
                    textTransform: 'uppercase',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  🛠 Executed Skills & Tool Calls ({thread.tool_calls_log.length})
                </div>

                {thread.tool_calls_log.map((tc: ToolCallLog, tci: number) => {
                  const toolKey = `${thread.id}-${tci}`;
                  const isExpanded = expandedTools.has(toolKey);
                  return (
                    <div
                      key={tci}
                      style={{
                        background: 'rgba(0,0,0,0.35)',
                        border: '1px solid rgba(255,255,255,0.07)',
                        borderRadius: '5px',
                        overflow: 'hidden',
                      }}
                    >
                      <button
                        onClick={() => toggleTool(toolKey)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          width: '100%',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '5px 8px',
                          textAlign: 'left',
                        }}
                      >
                        <span style={{ fontSize: '0.7rem' }}>⚙️</span>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            color: 'var(--accent-cyan, #00f0ff)',
                            fontFamily: 'var(--font-mono, monospace)',
                          }}
                        >
                          {tc.name}
                        </span>
                        {tc.skill && <SkillPill skill={tc.skill} />}
                        <span style={{ fontSize: '0.6rem', color: 'var(--text-dim, #94a3b8)', marginLeft: 'auto' }}>
                          {isExpanded ? '▲' : '▼'}
                        </span>
                      </button>

                      {isExpanded && (
                        <div
                          style={{
                            padding: '6px 8px 8px 8px',
                            borderTop: '1px solid rgba(255,255,255,0.05)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px',
                            fontSize: '0.68rem',
                            fontFamily: 'var(--font-mono, monospace)',
                          }}
                        >
                          {tc.args && Object.keys(tc.args).length > 0 && (
                            <div>
                              <span style={{ color: 'rgba(255,159,0,0.85)', fontWeight: 600 }}>Arguments: </span>
                              <pre
                                style={{
                                  margin: '2px 0',
                                  padding: '4px 6px',
                                  background: 'rgba(0,0,0,0.4)',
                                  borderRadius: '4px',
                                  color: '#cbd5e1',
                                  overflowX: 'auto',
                                  fontSize: '0.66rem',
                                }}
                              >
                                {JSON.stringify(tc.args, null, 2)}
                              </pre>
                            </div>
                          )}
                          {tc.result && (
                            <div>
                              <span style={{ color: 'rgba(16,185,129,0.85)', fontWeight: 600 }}>Execution Result: </span>
                              <pre
                                style={{
                                  margin: '2px 0',
                                  padding: '4px 6px',
                                  background: 'rgba(0,0,0,0.4)',
                                  borderRadius: '4px',
                                  color: '#cbd5e1',
                                  overflowX: 'auto',
                                  whiteSpace: 'pre-wrap',
                                  maxHeight: '160px',
                                  fontSize: '0.66rem',
                                }}
                              >
                                {tc.result}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* 4. Raw Subagent Output (Before Synthesis) */}
            <div
              style={{
                background: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '6px',
                padding: '7px 10px',
              }}
            >
              <div
                style={{
                  fontSize: '0.66rem',
                  fontWeight: 700,
                  color: 'rgba(16, 185, 129, 0.9)',
                  textTransform: 'uppercase',
                  marginBottom: '3px',
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              >
                📤 Subagent Raw Output (Passed to Synthesizer)
              </div>
              <div
                style={{
                  fontSize: '0.73rem',
                  color: 'var(--text-primary, #f1f5f9)',
                  fontFamily: 'var(--font-mono, monospace)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: '180px',
                  overflowY: 'auto',
                  lineHeight: '1.4',
                }}
              >
                {thread.assistant_response || <span style={{ color: 'var(--text-dim, #64748b)', fontStyle: 'italic' }}>empty response</span>}
              </div>
            </div>

            {/* 5. Recursive Children Subagents (if any) */}
            {thread.children && thread.children.length > 0 && (
              <div style={{ marginTop: '6px' }}>
                <div
                  style={{
                    fontSize: '0.66rem',
                    fontWeight: 700,
                    color: 'var(--accent-cyan, #00f0ff)',
                    marginBottom: '4px',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  ↳ Child Subagents ({thread.children.length})
                </div>
                {thread.children.map((child, ci) => (
                  <SubagentNode
                    key={child.id || ci}
                    thread={child}
                    index={ci}
                    isNested={true}
                    expandedTools={expandedTools}
                    toggleTool={toggleTool}
                    expandedReasoning={expandedReasoning}
                    toggleReasoning={toggleReasoning}
                    expandedNode={expandedNode}
                    toggleNode={toggleNode}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function SubagentTreeDrawer({ messageId, fetchWithAuth }: SubagentTreeDrawerProps) {
  const [open, setOpen] = useState(false);
  const [threads, setThreads] = useState<AgentThread[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState<Set<number>>(new Set());
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [expandedReasoning, setExpandedReasoning] = useState<Set<number>>(new Set());

  const handleToggle = async () => {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen && threads === null && !loading && messageId) {
      setLoading(true);
      try {
        const res = await fetchWithAuth(`/api/messages/${messageId}/agent_threads`);
        if (res.ok) {
          const data = await res.json();
          const loadedThreads: AgentThread[] = data.threads || [];
          setThreads(loadedThreads);
          // Default: expand all nodes
          setExpandedNodes(new Set(loadedThreads.map(t => t.id)));
        } else {
          setThreads([]);
        }
      } catch {
        setThreads([]);
      } finally {
        setLoading(false);
      }
    }
  };

  const toggleNode = (id: number) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleTool = (key: string) => {
    setExpandedTools(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const toggleReasoning = (id: number) => {
    setExpandedReasoning(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const expandAll = () => {
    if (!threads) return;
    setExpandedNodes(new Set(threads.map(t => t.id)));
    setExpandedReasoning(new Set(threads.map(t => t.id)));
  };

  const collapseAll = () => {
    setExpandedNodes(new Set());
    setExpandedReasoning(new Set());
    setExpandedTools(new Set());
  };

  const hasThreads = threads !== null && threads.length > 0;
  const countLabel = threads !== null ? ` (${threads.length} subagent${threads.length > 1 ? 's' : ''})` : '';

  // Aggregate stats
  const totalTokens = (threads || []).reduce(
    (acc, t) => acc + (t.total_tokens || (t.prompt_tokens_estimate || 0) + (t.completion_tokens_estimate || 0)),
    0
  );

  return (
    <div style={{ marginTop: '10px' }}>
      {/* Toggle Button */}
      <button
        onClick={handleToggle}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '0.74rem',
          fontWeight: 600,
          fontFamily: 'var(--font-mono, monospace)',
          padding: '5px 12px',
          borderRadius: '6px',
          cursor: 'pointer',
          backgroundColor: open ? 'rgba(0,240,255,0.15)' : 'rgba(0,240,255,0.06)',
          border: '1px solid rgba(0,240,255,0.3)',
          color: 'var(--accent-cyan, #00f0ff)',
          transition: 'all 0.2s ease',
          boxShadow: open ? '0 0 10px rgba(0,240,255,0.2)' : 'none',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(0,240,255,0.2)')}
        onMouseLeave={(e) =>
          (e.currentTarget.style.backgroundColor = open ? 'rgba(0,240,255,0.15)' : 'rgba(0,240,255,0.06)')
        }
      >
        <span style={{ fontSize: '0.85rem' }}>🧵</span>
        <span>{loading ? 'Loading agents telemetry...' : `Communication Link${countLabel}`}</span>
        {totalTokens > 0 && !loading && (
          <span style={{ opacity: 0.8, color: '#cbd5e1', fontSize: '0.68rem' }}>
            · {formatTokens(totalTokens)}
          </span>
        )}
        <span style={{ opacity: 0.8, fontSize: '0.65rem' }}>{open ? '▲' : '▼'}</span>
      </button>

      {/* Expanded Subagents Tree Drawer */}
      {open && (
        <div
          style={{
            marginTop: '10px',
            background: 'rgba(10, 15, 30, 0.92)',
            border: '1px solid rgba(0, 240, 255, 0.25)',
            borderRadius: '10px',
            padding: '12px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.4), inset 0 0 15px rgba(0,240,255,0.03)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          {/* Top Bar Header with Summary and Actions */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingBottom: '8px',
              borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
              flexWrap: 'wrap',
              gap: '6px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  color: 'var(--accent-cyan, #00f0ff)',
                  fontFamily: 'var(--font-mono, monospace)',
                  letterSpacing: '0.5px',
                }}
              >
                🗂️ SUBAGENTS COMMUNICATION & REASONING TREE
              </span>
              {hasThreads && (
                <span
                  style={{
                    fontSize: '0.67rem',
                    color: 'var(--text-dim, #94a3b8)',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  ({threads!.length} agent{threads!.length > 1 ? 's' : ''} dispatched)
                </span>
              )}
            </div>

            {hasThreads && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button
                  onClick={expandAll}
                  style={{
                    fontSize: '0.65rem',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: '#e2e8f0',
                    cursor: 'pointer',
                  }}
                >
                  Expand All
                </button>
                <button
                  onClick={collapseAll}
                  style={{
                    fontSize: '0.65rem',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: '#e2e8f0',
                    cursor: 'pointer',
                  }}
                >
                  Collapse All
                </button>
              </div>
            )}
          </div>

          {loading && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim, #94a3b8)', padding: '12px 6px' }}>
              ⏳ Loading subagents communication traces and reasoning...
            </div>
          )}

          {/* Subagent Tree Nodes */}
          {!loading && hasThreads && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {threads!.map((thread, ti) => (
                <SubagentNode
                  key={thread.id || ti}
                  thread={thread}
                  index={ti}
                  expandedTools={expandedTools}
                  toggleTool={toggleTool}
                  expandedReasoning={expandedReasoning}
                  toggleReasoning={toggleReasoning}
                  expandedNode={expandedNodes.has(thread.id)}
                  toggleNode={toggleNode}
                />
              ))}
            </div>
          )}

          {!loading && threads !== null && threads.length === 0 && (
            <div
              style={{
                fontSize: '0.72rem',
                color: 'var(--text-dim, #94a3b8)',
                padding: '8px 10px',
                background: 'rgba(0,0,0,0.25)',
                borderRadius: '6px',
              }}
            >
              ℹ️ No external subagents or tools were dispatched for this direct response.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SubagentTreeDrawer;
