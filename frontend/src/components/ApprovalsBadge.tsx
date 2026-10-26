import type { RefObject } from 'react';
import { useEffect, useState, useCallback } from 'react';
import { ShieldAlert } from 'lucide-react';
import { pendingCount } from '../api/governance';

export interface ApprovalsBadgeProps {
  onOpen: () => void;
  ws?: WebSocket | null;
  wsRef?: RefObject<WebSocket | null>;
  getWs?: () => WebSocket | null;
}

export function ApprovalsBadge({ onOpen, ws, wsRef, getWs }: ApprovalsBadgeProps) {
  const [count, setCount] = useState<number>(0);

  const refreshCount = useCallback(async () => {
    try {
      const c = await pendingCount();
      setCount(c);
    } catch {
      // ignore in background
    }
  }, []);

  useEffect(() => {
    refreshCount();
    const timer = setInterval(refreshCount, 10000);
    return () => clearInterval(timer);
  }, [refreshCount]);

  useEffect(() => {
    const activeWs = ws ?? (wsRef ? wsRef.current : (getWs ? getWs() : null));
    if (!activeWs || typeof activeWs.addEventListener !== 'function') return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'approval_update') {
          refreshCount();
        }
      } catch {
        // ignore non-json
      }
    };

    activeWs.addEventListener('message', handleMessage);
    return () => {
      activeWs.removeEventListener('message', handleMessage);
    };
  }, [ws, wsRef, getWs, refreshCount]);

  return (
    <button
      onClick={onOpen}
      className="approvals-badge-btn"
      title={count > 0 ? `${count} pending governance approvals` : 'Governance Approvals'}
      aria-label={count > 0 ? `Approvals (${count})` : 'Approvals'}
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '6px 10px',
        background: count > 0 ? 'rgba(245, 158, 11, 0.15)' : 'rgba(255, 255, 255, 0.05)',
        border: count > 0 ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '8px',
        color: count > 0 ? '#f59e0b' : 'var(--text-dim, #94a3b8)',
        cursor: 'pointer',
        fontSize: '0.8rem',
        fontWeight: 600,
        transition: 'all 0.2s ease',
      }}
    >
      <ShieldAlert size={16} />
      <span>Approvals</span>
      {count > 0 && (
        <span
          data-testid="approvals-count"
          style={{
            backgroundColor: '#f59e0b',
            color: '#000',
            fontSize: '0.7rem',
            fontWeight: 800,
            padding: '1px 6px',
            borderRadius: '10px',
            lineHeight: 1.2,
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}
