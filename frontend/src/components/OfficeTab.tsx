import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, CircleDashed, Cpu, Loader2 } from 'lucide-react';
import type { AgentModel } from '../types';
import { styles } from '../styles';

interface OfficeTabProps {
  t: (key: string) => string;
}

function statusColor(status?: string) {
  if (status === 'working') return 'var(--accent-cyan)';
  if (status === 'error') return 'var(--danger)';
  if (status === 'disabled') return 'var(--text-dim)';
  return 'var(--success)';
}

function statusIcon(status?: string) {
  if (status === 'working') return <Loader2 size={16} className="spin-slow" />;
  if (status === 'error') return <AlertTriangle size={16} />;
  if (status === 'disabled') return <CircleDashed size={16} />;
  return <CheckCircle2 size={16} />;
}

export function OfficeTab({ t }: OfficeTabProps) {
  const [agents, setAgents] = useState<AgentModel[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const token = localStorage.getItem('jarvis_auth_token');
        const response = await fetch('/api/office/state', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (active) {
          setAgents(data.agents || []);
          setError('');
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Failed to load office state');
      }
    };
    load();
    const timer = window.setInterval(load, 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>{t('officeTitle')}</h2>
          <p style={styles.tabSubtitle}>{t('officeSubtitle')}</p>
        </div>
      </div>

      {error && (
        <div className="glass-panel" style={{ padding: 14, color: 'var(--danger)' }}>
          {error}
        </div>
      )}

      <div className="office-grid">
        {agents.map(agent => {
          const status = agent.is_enabled ? (agent.status || 'idle') : 'disabled';
          const progress = Math.max(0, Math.min(100, agent.progress ?? 0));
          return (
            <article key={agent.id} className="glass-panel office-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <h3 style={{ fontSize: '1rem', marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{agent.name}</h3>
                  <p style={{ color: 'var(--text-dim)', fontSize: '0.78rem' }}>{agent.role || 'Specialist'} · {agent.id}</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: statusColor(status), fontWeight: 700, fontSize: '0.78rem' }}>
                  {statusIcon(status)}
                  {status.toUpperCase()}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 14 }}>
                <Cpu size={14} style={{ color: 'var(--accent-cyan)' }} />
                <span>{agent.model_type || 'external'} / {agent.model_provider || 'openrouter'} / {agent.model}</span>
              </div>

              <div style={{ marginTop: 14 }}>
                <div style={styles.metricLabelRow}>
                  <span>{t('activeTask')}</span>
                  <span style={{ color: statusColor(status), fontFamily: 'var(--font-mono)' }}>{progress}%</span>
                </div>
                <div style={styles.progressBarBg}>
                  <div style={{ ...styles.progressBarFill, width: `${progress}%`, backgroundColor: statusColor(status), boxShadow: 'none' }} />
                </div>
                <p style={{ color: agent.current_task ? 'var(--text-primary)' : 'var(--text-dim)', fontSize: '0.84rem', lineHeight: 1.45, marginTop: 8 }}>
                  {agent.current_task || t('noActiveTask')}
                </p>
              </div>

              <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
                <div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', fontWeight: 700 }}>{t('lastAction')}</div>
                  <div style={{ color: 'var(--text-primary)', fontSize: '0.82rem', marginTop: 3 }}>{agent.last_action || '-'}</div>
                </div>
                {agent.last_error && (
                  <div style={{ color: 'var(--danger)', fontSize: '0.8rem' }}>{agent.last_error}</div>
                )}
              </div>

              <div style={{ marginTop: 14, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 12 }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', fontWeight: 700, marginBottom: 8 }}>{t('recentActions')}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {(agent.recent_events || []).length === 0 ? (
                    <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>{t('noEvents')}</span>
                  ) : (
                    (agent.recent_events || []).map(event => (
                      <div key={event.id} style={{ color: 'var(--text-muted)', fontSize: '0.78rem', lineHeight: 1.35 }}>
                        <span style={{ color: statusColor(event.status), fontFamily: 'var(--font-mono)' }}>{event.timestamp}</span> · {event.message}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
