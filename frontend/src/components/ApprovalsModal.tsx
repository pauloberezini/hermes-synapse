import { useEffect, useState, useCallback, useRef } from 'react';
import { ShieldAlert, CheckCircle, XCircle, RefreshCw, X, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';
import type { ApprovalDetail, ApprovalSummary } from '../types';
import { getApproval, listApprovals, resolveApproval } from '../api/governance';

const STATUS_CHIP: Record<string, { backgroundColor: string; color: string; border: string }> = {
  PENDING: {
    backgroundColor: 'rgba(245,158,11,0.15)',
    color: '#f59e0b',
    border: 'rgba(245,158,11,0.3)',
  },
  APPROVED: {
    backgroundColor: 'rgba(16,185,129,0.15)',
    color: '#10b981',
    border: 'rgba(16,185,129,0.3)',
  },
  REJECTED: {
    backgroundColor: 'rgba(239,68,68,0.15)',
    color: '#ef4444',
    border: 'rgba(239,68,68,0.3)',
  },
};

const SLATE_CHIP = {
  backgroundColor: 'rgba(148,163,184,0.15)',
  color: '#94a3b8',
  border: 'rgba(148,163,184,0.3)',
};

function statusChip(status: string) {
  return STATUS_CHIP[status] ?? SLATE_CHIP;
}

export interface ApprovalsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onResolved?: () => void;
}

export function ApprovalsModal({ isOpen, onClose, onResolved }: ApprovalsModalProps) {
  const [activeTab, setActiveTab] = useState<'pending' | 'all'>('pending');
  const [requests, setRequests] = useState<ApprovalSummary[]>([]);
  const [details, setDetails] = useState<Record<number, ApprovalDetail>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listApprovals(activeTab === 'pending');
      const list = Array.isArray(data) ? data : [];
      setRequests(list);
      if (list.length > 0 && focusedId === null) {
        setFocusedId(list[0].id);
      }
    } catch (e) {
      console.error('Failed to fetch approval requests:', e);
    } finally {
      setLoading(false);
    }
  }, [activeTab, focusedId]);

  useEffect(() => {
    if (isOpen) {
      fetchRequests();
      if (dialogRef.current && !dialogRef.current.open) {
        dialogRef.current.showModal?.();
      }
    } else {
      if (dialogRef.current && dialogRef.current.open) {
        dialogRef.current.close?.();
      }
    }
  }, [isOpen, fetchRequests]);

  useEffect(() => {
    if (!isOpen) return;
    const onUpdate = () => {
      void fetchRequests();
    };
    window.addEventListener('approval_update', onUpdate);
    return () => window.removeEventListener('approval_update', onUpdate);
  }, [isOpen, fetchRequests]);

  const toggleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    setFocusedId(id);
    if (!details[id]) {
      try {
        const detail = await getApproval(id);
        setDetails(prev => ({ ...prev, [id]: detail }));
      } catch (err) {
        console.error(`Failed to fetch detail for #${id}`, err);
      }
    }
  };

  const handleResolve = useCallback(async (id: number, decision: 'APPROVED' | 'REJECTED') => {
    try {
      const note = notes[id] || '';
      await resolveApproval(id, decision, note);
      await fetchRequests();
      if (onResolved) onResolved();
    } catch (e) {
      console.error(`Failed to resolve request #${id}:`, e);
    }
  }, [notes, fetchRequests, onResolved]);

  const copyHash = (hash: string) => {
    navigator.clipboard?.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Keyboard navigation: A to approve, R to reject focused pending item, Esc to close
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.key === 'Escape') {
        onClose();
      } else if ((e.key === 'a' || e.key === 'A') && focusedId !== null) {
        const req = requests.find(r => r.id === focusedId);
        if (req && req.status === 'PENDING') {
          e.preventDefault();
          handleResolve(focusedId, 'APPROVED');
        }
      } else if ((e.key === 'r' || e.key === 'R') && focusedId !== null) {
        const req = requests.find(r => r.id === focusedId);
        if (req && req.status === 'PENDING') {
          e.preventDefault();
          handleResolve(focusedId, 'REJECTED');
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, focusedId, requests, onClose, handleResolve]);

  if (!isOpen) return null;

  return (
    <dialog
      ref={dialogRef}
      className="approvals-modal-dialog"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        backgroundColor: 'rgba(5, 8, 18, 0.85)',
        backdropFilter: 'blur(10px)',
        border: 'none',
        padding: 0,
        width: '100vw',
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        className="approvals-modal-container"
        style={{
          width: '94%',
          maxWidth: '1000px',
          maxHeight: '85vh',
          backgroundColor: '#0a0e1a',
          border: '1px solid rgba(0, 240, 255, 0.3)',
          borderRadius: '14px',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 60px rgba(0, 0, 0, 0.9)',
          overflow: 'hidden',
          color: '#e2e8f0',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
      >
        {/* Header with Title and Tabs */}
        <div
          style={{
            padding: '16px 24px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'rgba(0, 240, 255, 0.03)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <ShieldAlert size={22} style={{ color: 'var(--accent-cyan, #00f0ff)' }} />
            <div>
              <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, letterSpacing: '0.5px' }}>
                GOVERNANCE APPROVALS
              </h2>
              <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                Human-in-the-loop audit & evidence verification
              </span>
            </div>
            {/* Filter Tabs: Pending | All */}
            <div style={{ display: 'flex', gap: '6px', marginLeft: '20px', background: 'rgba(255, 255, 255, 0.05)', padding: '3px', borderRadius: '8px' }}>
              <button
                onClick={() => setActiveTab('pending')}
                style={{
                  padding: '4px 12px',
                  borderRadius: '6px',
                  border: 'none',
                  background: activeTab === 'pending' ? 'rgba(0, 240, 255, 0.2)' : 'transparent',
                  color: activeTab === 'pending' ? '#00f0ff' : '#94a3b8',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Pending
              </button>
              <button
                onClick={() => setActiveTab('all')}
                style={{
                  padding: '4px 12px',
                  borderRadius: '6px',
                  border: 'none',
                  background: activeTab === 'all' ? 'rgba(0, 240, 255, 0.2)' : 'transparent',
                  color: activeTab === 'all' ? '#00f0ff' : '#94a3b8',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                All
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={fetchRequests}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px' }}
              title="Refresh"
            >
              <RefreshCw size={16} className={loading ? 'spin' : ''} />
            </button>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px' }}
              title="Close (Esc)"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Content list */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {requests.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '50px 20px', color: '#94a3b8', fontSize: '0.9rem' }}>
              No {activeTab === 'pending' ? 'pending ' : ''}approval requests found.
            </div>
          ) : (
            requests.map((req) => {
              const isPending = req.status === 'PENDING';
              const tone = statusChip(req.status);
              const isExpanded = expandedId === req.id;
              const detail = details[req.id];

              return (
                <div
                  key={req.id}
                  onClick={() => setFocusedId(req.id)}
                  style={{
                    borderRadius: '10px',
                    border: focusedId === req.id ? '1px solid rgba(0, 240, 255, 0.5)' : '1px solid rgba(255, 255, 255, 0.08)',
                    backgroundColor: isPending ? 'rgba(0, 240, 255, 0.02)' : 'rgba(255, 255, 255, 0.01)',
                    overflow: 'hidden',
                    transition: 'all 0.2s ease',
                  }}
                >
                  {/* Summary Bar */}
                  <div
                    style={{
                      padding: '14px 18px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      gap: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpand(req.id);
                        }}
                        aria-label={`Show evidence #${req.id}`}
                        style={{
                          background: 'rgba(255, 255, 255, 0.06)',
                          border: 'none',
                          borderRadius: '6px',
                          color: '#00f0ff',
                          padding: '6px 8px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                        }}
                      >
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        <span>Show evidence #{req.id}</span>
                      </button>

                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#fff' }}>
                            #{req.id} · <span style={{ color: '#00f0ff' }}>{req.agent_name || req.agent_id}</span>
                            {req.agent_name ? (
                              <span style={{ color: '#64748b', fontWeight: 500 }}> {req.agent_id}</span>
                            ) : null}{' '}
                            → {req.action_name}
                          </span>
                          {/* Truncation chips / Flags */}
                          {req.flags?.map((flag) => (
                            <span
                              key={flag}
                              style={{
                                fontSize: '0.65rem',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                background: 'rgba(245, 158, 11, 0.15)',
                                color: '#f59e0b',
                                border: '1px solid rgba(245, 158, 11, 0.3)',
                              }}
                            >
                              {flag === 'tool_result_capped_600' ? 'tool result capped at 600 chars' : flag}
                            </span>
                          ))}
                        </div>
                        <p style={{ margin: '4px 0 0 0', fontSize: '0.78rem', color: '#cbd5e1' }}>
                          {req.description || `${req.agent_id} wants to run ${req.action_name}`}
                        </p>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          padding: '3px 10px',
                          borderRadius: '12px',
                          backgroundColor: tone.backgroundColor,
                          color: tone.color,
                          border: `1px solid ${tone.border}`,
                        }}
                      >
                        {req.status}
                      </span>
                    </div>
                  </div>

                  {/* Expanded Claim / Source Split View */}
                  {isExpanded && (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '16px',
                        padding: '16px 20px',
                        borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                        backgroundColor: 'rgba(0, 0, 0, 0.35)',
                      }}
                    >
                      {/* Left: CLAIM */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#00f0ff', letterSpacing: '0.5px' }}>
                          CLAIM
                        </div>
                        <div style={{ fontSize: '0.78rem', color: '#f8fafc' }}>
                          #{req.id} {req.agent_name || req.agent_id} → {req.action_name}
                        </div>
                        {req.agent_name ? (
                          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>session {req.agent_id}</div>
                        ) : null}
                        <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                          "{req.description}"
                        </div>

                        <div>
                          <span style={{ fontSize: '0.7rem', color: '#64748b' }}>args (pretty JSON):</span>
                          <pre
                            style={{
                              margin: '4px 0 0 0',
                              padding: '8px 10px',
                              borderRadius: '6px',
                              background: 'rgba(0, 0, 0, 0.6)',
                              border: '1px solid rgba(255, 255, 255, 0.06)',
                              fontSize: '0.7rem',
                              maxHeight: '140px',
                              overflowY: 'auto',
                              color: '#cbd5e1',
                            }}
                          >
                            {(() => {
                              try {
                                return JSON.stringify(JSON.parse(req.payload), null, 2);
                              } catch {
                                return req.payload;
                              }
                            })()}
                          </pre>
                        </div>

                        {req.bundle_hash && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.7rem' }}>
                            <span style={{ color: '#64748b' }}>hash:</span>
                            <code style={{ color: '#00f0ff', background: 'rgba(0, 240, 255, 0.08)', padding: '2px 6px', borderRadius: '4px' }}>
                              {req.bundle_hash.slice(0, 10)}...{req.bundle_hash.slice(-8)}
                            </code>
                            <button
                              onClick={() => copyHash(req.bundle_hash!)}
                              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '2px' }}
                              title="Copy full SHA-256 hash"
                            >
                              {copiedHash === req.bundle_hash ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                            </button>
                          </div>
                        )}

                        {isPending && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                            <input
                              type="text"
                              placeholder="resolver note..."
                              value={notes[req.id] || ''}
                              onChange={(e) => setNotes({ ...notes, [req.id]: e.target.value })}
                              style={{
                                padding: '8px 12px',
                                borderRadius: '6px',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                backgroundColor: 'rgba(0, 0, 0, 0.4)',
                                color: '#fff',
                                fontSize: '0.78rem',
                              }}
                            />
                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                onClick={() => handleResolve(req.id, 'APPROVED')}
                                style={{
                                  flex: 1,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '6px',
                                  padding: '7px 12px',
                                  borderRadius: '6px',
                                  border: '1px solid rgba(16, 185, 129, 0.4)',
                                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                  color: '#10b981',
                                  fontSize: '0.78rem',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                <CheckCircle size={15} /> Approve
                              </button>
                              <button
                                onClick={() => handleResolve(req.id, 'REJECTED')}
                                style={{
                                  flex: 1,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '6px',
                                  padding: '7px 12px',
                                  borderRadius: '6px',
                                  border: '1px solid rgba(239, 68, 68, 0.4)',
                                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                                  color: '#ef4444',
                                  fontSize: '0.78rem',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                <XCircle size={15} /> Reject
                              </button>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Right: SOURCE */}
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                          borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
                          paddingLeft: '16px',
                        }}
                      >
                        <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.5px' }}>
                          SOURCE
                        </div>

                        {/* Plan */}
                        <div>
                          <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '4px' }}>
                            {detail?.bundle?.plan ? (
                              <>
                                Plan step {detail.bundle.plan.step_index + 1}/{detail.bundle.plan.step_count} · {detail.bundle.plan.agent}
                              </>
                            ) : (
                              'Plan Context'
                            )}
                          </div>
                          {detail?.bundle?.plan ? (
                            <div
                              style={{
                                padding: '8px 10px',
                                borderRadius: '6px',
                                background: 'rgba(56, 189, 248, 0.08)',
                                border: '1px solid rgba(56, 189, 248, 0.2)',
                                fontSize: '0.75rem',
                                color: '#e0f2fe',
                              }}
                            >
                              {detail.bundle.plan.instructions}
                            </div>
                          ) : (
                            <div style={{ fontSize: '0.75rem', color: '#64748b', fontStyle: 'italic' }}>
                              No planner step attached
                            </div>
                          )}
                          {detail?.bundle?.flags?.includes('direct_route') && (
                            <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '6px' }}>
                              No planner chose this step.
                            </div>
                          )}
                        </div>

                        {/* Upstream Items */}
                        <div>
                          <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '6px' }}>Upstream</div>
                          {!detail?.bundle?.upstream || detail.bundle.upstream.length === 0 ? (
                            <div style={{ fontSize: '0.75rem', color: '#64748b', fontStyle: 'italic' }}>
                              No upstream results
                            </div>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '160px', overflowY: 'auto' }}>
                              {detail.bundle.upstream.map((item, idx) => (
                                <div
                                  key={idx}
                                  style={{
                                    padding: '8px',
                                    borderRadius: '6px',
                                    background: 'rgba(0, 0, 0, 0.5)',
                                    border: '1px solid rgba(255, 255, 255, 0.06)',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '4px',
                                  }}
                                >
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span style={{ fontSize: '0.72rem', fontWeight: 600, color: '#f1f5f9' }}>
                                      {item.name}
                                    </span>
                                    <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                                      {item.truncated && (
                                        <span
                                          style={{
                                            fontSize: '0.62rem',
                                            padding: '1px 5px',
                                            borderRadius: '4px',
                                            background: 'rgba(239, 68, 68, 0.15)',
                                            color: '#f87171',
                                            border: '1px solid rgba(239, 68, 68, 0.3)',
                                          }}
                                        >
                                          {item.reason === 'tool_result_600'
                                            ? 'tool result capped at 600 chars'
                                            : item.reason === 'pdf_page_stop'
                                            ? 'read stopped before the last page'
                                            : 'truncated'}
                                        </span>
                                      )}
                                      <code style={{ fontSize: '0.65rem', color: '#64748b' }}>
                                        sha {item.sha256.slice(0, 6)}...
                                      </code>
                                    </div>
                                  </div>
                                  <div style={{ fontSize: '0.68rem', color: '#94a3b8', whiteSpace: 'pre-wrap', maxHeight: '50px', overflowY: 'auto' }}>
                                    {item.excerpt}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </dialog>
  );
}
