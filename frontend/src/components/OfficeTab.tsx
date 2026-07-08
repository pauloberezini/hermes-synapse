import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, CircleDashed, Cpu, Loader2, Network, Radio, Zap } from 'lucide-react';
import type { AgentModel } from '../types';
import { styles } from '../styles';

interface OfficeTabProps {
  t: (key: string) => string;
  selectChat?: (chatId: string) => void;
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

function compactName(name: string) {
  return name.length > 17 ? `${name.slice(0, 15)}…` : name;
}

function agentStatus(agent: AgentModel) {
  return agent.is_enabled === false ? 'disabled' : (agent.status || 'idle');
}

function AgentPulseMap({ agents, selectChat }: { agents: AgentModel[]; selectChat?: (chatId: string) => void }) {
  const center = { x: 500, y: 172 };
  const radiusX = 355;
  const radiusY = 112;
  const total = Math.max(agents.length, 1);
  const positions = new Map<string, { x: number; y: number }>();

  agents.forEach((agent, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
    const ringBump = Math.floor(index / 12) * 24;
    positions.set(agent.id, {
      x: center.x + Math.cos(angle) * (radiusX - ringBump),
      y: center.y + Math.sin(angle) * (radiusY - ringBump * 0.35),
    });
  });

  const workingCount = agents.filter(agent => agentStatus(agent) === 'working').length;
  const errorCount = agents.filter(agent => agentStatus(agent) === 'error').length;
  const disabledCount = agents.filter(agent => agentStatus(agent) === 'disabled').length;
  const idleCount = Math.max(0, agents.length - workingCount - errorCount - disabledCount);
  const recentAgents = [...agents]
    .filter(agent => agent.current_task || agent.last_action || (agent.recent_events || []).length > 0)
    .slice(0, 5);

  return (
    <section className="glass-panel office-pulse-frame" style={styles.officePulseFrame}>
      <div style={styles.officePulseHeader}>
        <div>
          <div style={styles.sceneKicker}>AGENT PULSE MAP</div>
          <h3 style={styles.officePulseTitle}>Hermes operational constellation</h3>
        </div>
        <div style={styles.officePulseStats}>
          <span style={{ ...styles.sceneStat, color: 'var(--accent-cyan)' }}>{workingCount} WORKING</span>
          <span style={{ ...styles.sceneStat, color: 'var(--success)' }}>{idleCount} IDLE</span>
          <span style={{ ...styles.sceneStat, color: 'var(--danger)' }}>{errorCount} ERROR</span>
        </div>
      </div>

      <div className="office-pulse-body" style={styles.officePulseBody}>
        <div style={styles.officePulseMap}>
          <svg viewBox="0 0 1000 360" role="img" aria-label="Agent topology visualization" className="agent-pulse-svg">
            <defs>
              <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#f7f4ff" stopOpacity="0.95" />
                <stop offset="42%" stopColor="#9b88ff" stopOpacity="0.7" />
                <stop offset="100%" stopColor="#73d9ff" stopOpacity="0.05" />
              </radialGradient>
              <filter id="softGlow">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <ellipse cx={center.x} cy={center.y} rx="374" ry="126" fill="none" stroke="rgba(155,136,255,0.18)" strokeWidth="2" strokeDasharray="5 12" />
            <ellipse cx={center.x} cy={center.y} rx="248" ry="78" fill="none" stroke="rgba(115,217,255,0.12)" strokeWidth="2" />

            {agents.map((agent) => {
              const pos = positions.get(agent.id) || center;
              const parentPos = agent.parent_id ? positions.get(agent.parent_id) : undefined;
              const from = parentPos || center;
              const color = statusColor(agentStatus(agent));
              return (
                <path
                  key={`link-${agent.id}`}
                  d={`M ${from.x} ${from.y} Q ${(from.x + pos.x) / 2} ${(from.y + pos.y) / 2 - 34} ${pos.x} ${pos.y}`}
                  stroke={color}
                  strokeOpacity="0.28"
                  strokeWidth="2"
                  fill="none"
                />
              );
            })}

            <g filter="url(#softGlow)">
              <circle cx={center.x} cy={center.y} r="48" fill="url(#coreGlow)" opacity="0.95" />
              <circle cx={center.x} cy={center.y} r="72" fill="none" stroke="rgba(155,136,255,0.32)" strokeWidth="2" />
              <circle cx={center.x} cy={center.y} r="92" fill="none" stroke="rgba(115,217,255,0.18)" strokeWidth="1" strokeDasharray="4 10" />
              <text x={center.x} y={center.y - 4} textAnchor="middle" fill="#f7f4ff" fontSize="18" fontWeight="700">HERMES</text>
              <text x={center.x} y={center.y + 18} textAnchor="middle" fill="#73d9ff" fontSize="11" letterSpacing="2">CORE</text>
            </g>

            {agents.map((agent) => {
              const pos = positions.get(agent.id) || center;
              const status = agentStatus(agent);
              const color = statusColor(status);
              const progress = Math.max(0, Math.min(100, agent.progress ?? 0));
              const circumference = 2 * Math.PI * 24;
              return (
                <g
                  key={agent.id}
                  transform={`translate(${pos.x} ${pos.y})`}
                  className="agent-pulse-node"
                  onClick={() => selectChat?.(agent.id)}
                >
                  <circle r="31" fill="rgba(18,19,32,0.92)" stroke="rgba(255,255,255,0.12)" strokeWidth="1" />
                  <circle r="24" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
                  <circle
                    r="24"
                    fill="none"
                    stroke={color}
                    strokeWidth="4"
                    strokeDasharray={`${(progress / 100) * circumference} ${circumference}`}
                    transform="rotate(-90)"
                    opacity="0.95"
                  />
                  <circle r="7" fill={color} filter="url(#softGlow)" />
                  <text y="48" textAnchor="middle" fill="#f7f4ff" fontSize="12" fontWeight="700">{compactName(agent.name || agent.id)}</text>
                  <text y="64" textAnchor="middle" fill={color} fontSize="9" letterSpacing="1.4">{status.toUpperCase()}</text>
                </g>
              );
            })}

            {agents.length === 0 && (
              <text x={center.x} y="318" textAnchor="middle" fill="rgba(247,244,255,0.58)" fontSize="16">
                Waiting for office agents…
              </text>
            )}
          </svg>
        </div>

        <aside className="office-pulse-side" style={styles.officePulseSide}>
          <div style={styles.officePulseSideTitle}>
            <Network size={16} />
            <span>Live routing</span>
          </div>
          <div style={styles.officeSignalList}>
            {(recentAgents.length ? recentAgents : agents.slice(0, 5)).map(agent => (
              <button
                key={agent.id}
                type="button"
                style={styles.officeSignalItem}
                onClick={() => selectChat?.(agent.id)}
              >
                <span style={{ ...styles.sceneLegendDot, background: statusColor(agentStatus(agent)), boxShadow: `0 0 10px ${statusColor(agentStatus(agent))}` }} />
                <span style={styles.officeSignalText}>
                  <strong>{agent.name}</strong>
                  <small>{agent.current_task || agent.last_action || agent.role || agent.id}</small>
                </span>
                <Radio size={14} />
              </button>
            ))}
          </div>
          <div style={styles.officePulseFooter}>
            <Zap size={15} />
            <span>{agents.length} agents connected to the office state stream</span>
          </div>
        </aside>
      </div>
    </section>
  );
}

export function OfficeTab({ t, selectChat }: OfficeTabProps) {
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

      <AgentPulseMap agents={agents} selectChat={selectChat} />

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
