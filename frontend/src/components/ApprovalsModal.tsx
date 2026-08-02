import { useEffect, useState } from 'react';
import { ShieldAlert, CheckCircle, XCircle, RefreshCw, X } from 'lucide-react';

interface ApprovalRequest {
  id: number;
  agent_id: string;
  action_name: string;
  payload: string;
  description: string;
  status: string;
  created_at: string;
}

interface ApprovalsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onResolved?: () => void;
}

export function ApprovalsModal({ isOpen, onClose, onResolved }: ApprovalsModalProps) {
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState<Record<number, string>>({});

  const fetchRequests = async () => {
    setLoading(true);
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch('http://localhost:8000/api/governance/approvals', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await res.json();
      setRequests(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch approval requests:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchRequests();
    }
  }, [isOpen]);

  const handleResolve = async (id: number, decision: 'APPROVED' | 'REJECTED') => {
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch(`http://localhost:8000/api/governance/approvals/${id}/resolve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          decision,
          resolver_note: note[id] || '',
        }),
      });
      if (res.ok) {
        fetchRequests();
        if (onResolved) onResolved();
      }
    } catch (e) {
      console.error(`Failed to resolve request #${id}:`, e);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      backgroundColor: 'rgba(0, 0, 0, 0.75)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
    }}>
      <div style={{
        width: '100%', maxWidth: '640px', maxHeight: '80vh',
        backgroundColor: '#0a0e1a', border: '1px solid rgba(0, 240, 255, 0.3)',
        borderRadius: '12px', display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 50px rgba(0,0,0,0.8)', overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.08)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          backgroundColor: 'rgba(0,240,255,0.03)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ShieldAlert size={20} style={{ color: '#00f0ff' }} />
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#fff', margin: 0 }}>
                GOVERNANCE APPROVAL QUEUE
              </h3>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                Human-in-the-loop permission requests
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={fetchRequests}
              style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', padding: '4px' }}
              title="Refresh"
            >
              <RefreshCw size={14} className={loading ? 'spin' : ''} />
            </button>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', padding: '4px' }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {requests.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
              No approval requests found in queue.
            </div>
          ) : (
            requests.map(req => {
              const isPending = req.status === 'PENDING';
              return (
                <div
                  key={req.id}
                  style={{
                    padding: '14px', borderRadius: '8px',
                    border: isPending ? '1px solid rgba(0,240,255,0.3)' : '1px solid rgba(255,255,255,0.06)',
                    backgroundColor: isPending ? 'rgba(0,240,255,0.02)' : 'rgba(255,255,255,0.01)',
                    display: 'flex', flexDirection: 'column', gap: '8px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff' }}>
                      #{req.id} · <span style={{ color: 'var(--accent-cyan)' }}>{req.agent_id}</span> → {req.action_name}
                    </span>
                    <span style={{
                      fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px', borderRadius: '12px',
                      backgroundColor: req.status === 'PENDING' ? 'rgba(245,158,11,0.15)' : req.status === 'APPROVED' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                      color: req.status === 'PENDING' ? '#f59e0b' : req.status === 'APPROVED' ? '#10b981' : '#ef4444',
                      border: `1px solid ${req.status === 'PENDING' ? 'rgba(245,158,11,0.3)' : req.status === 'APPROVED' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`
                    }}>
                      {req.status}
                    </span>
                  </div>

                  {req.description && (
                    <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', margin: 0 }}>
                      {req.description}
                    </p>
                  )}

                  <pre style={{
                    fontSize: '0.65rem', backgroundColor: 'rgba(0,0,0,0.4)', padding: '8px',
                    borderRadius: '4px', overflowX: 'auto', color: 'var(--text-dim)', margin: 0
                  }}>
                    {req.payload}
                  </pre>

                  {isPending && (
                    <div style={{ display: 'flex', gap: '8px', marginTop: '6px', alignItems: 'center' }}>
                      <input
                        type="text"
                        placeholder="Optional resolver note..."
                        value={note[req.id] || ''}
                        onChange={e => setNote({ ...note, [req.id]: e.target.value })}
                        style={{
                          flex: 1, padding: '6px 10px', borderRadius: '6px',
                          border: '1px solid rgba(255,255,255,0.1)', backgroundColor: 'rgba(0,0,0,0.3)',
                          color: '#fff', fontSize: '0.75rem'
                        }}
                      />
                      <button
                        onClick={() => handleResolve(req.id, 'APPROVED')}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '4px',
                          padding: '6px 12px', borderRadius: '6px', border: '1px solid rgba(16,185,129,0.4)',
                          backgroundColor: 'rgba(16,185,129,0.15)', color: '#10b981', fontSize: '0.75rem',
                          fontWeight: 600, cursor: 'pointer'
                        }}
                      >
                        <CheckCircle size={14} /> Approve
                      </button>
                      <button
                        onClick={() => handleResolve(req.id, 'REJECTED')}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '4px',
                          padding: '6px 12px', borderRadius: '6px', border: '1px solid rgba(239,68,68,0.4)',
                          backgroundColor: 'rgba(239,68,68,0.15)', color: '#ef4444', fontSize: '0.75rem',
                          fontWeight: 600, cursor: 'pointer'
                        }}
                      >
                        <XCircle size={14} /> Reject
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
