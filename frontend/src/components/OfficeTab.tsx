import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Bed, BriefcaseBusiness, CheckCircle2, CircleDashed, Coffee, Cpu, Loader2, Monitor } from 'lucide-react';
import type { AgentModel } from '../types';
import { styles } from '../styles';

interface OfficeTabProps {
  t: (key: string) => string;
  selectChat?: (chatId: string) => void;
}

interface AgentProjectGroup {
  project: string;
  agents: AgentModel[];
}

type AgentStatusKind = 'work' | 'task' | 'idle' | 'waiting' | 'error' | 'offline' | 'done';
type OfficeZoneKey = 'work' | 'task' | 'idle' | 'waiting' | 'maintenance' | 'sleep';

interface OfficeZone {
  key: OfficeZoneKey;
  label: string;
  icon: string;
  agents: AgentModel[];
}

const ACTIVE_STATUSES = new Set(['active', 'working']);
const TASK_STATUSES = new Set(['running', 'processing']);
const IDLE_STATUSES = new Set(['idle']);
const WAITING_STATUSES = new Set(['waiting', 'queued', 'pending']);
const ERROR_STATUSES = new Set(['error', 'failed', 'failure']);
const OFFLINE_STATUSES = new Set(['offline', 'disabled', 'sleeping', 'sleep', 'inactive']);
const DONE_STATUSES = new Set(['done', 'completed', 'complete', 'success']);

function statusColor(status?: string) {
  const kind = statusKind(status);
  if (kind === 'work') return 'var(--accent-cyan)';
  if (kind === 'task') return 'var(--accent-blue)';
  if (kind === 'waiting') return 'var(--warning)';
  if (kind === 'error') return 'var(--danger)';
  if (kind === 'offline') return 'var(--text-dim)';
  return 'var(--success)';
}

function statusIcon(status?: string) {
  const kind = statusKind(status);
  if (kind === 'work') return <Loader2 size={16} className="spin-slow" />;
  if (kind === 'task') return <Monitor size={16} className="spin-slow" />;
  if (kind === 'waiting') return <CircleDashed size={16} />;
  if (kind === 'error') return <AlertTriangle size={16} />;
  if (kind === 'offline') return <Bed size={16} />;
  if (kind === 'idle') return <Coffee size={16} />;
  return <CheckCircle2 size={16} />;
}

function statusLabel(status?: string, t?: (key: string) => string) {
  const normalized = normalizeStatus(status);
  const key = `status${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
  const translated = t?.(key);
  if (translated && translated !== key) return translated;
  if (normalized === 'working') return 'Running task';
  return normalized.replace(/_/g, ' ');
}

function agentStatus(agent: AgentModel) {
  return agent.is_enabled === false ? 'disabled' : normalizeStatus(agent.status);
}

function normalizeStatus(status?: string) {
  return (status || 'idle').trim().toLowerCase();
}

function statusKind(status?: string): AgentStatusKind {
  const normalized = normalizeStatus(status);
  if (ACTIVE_STATUSES.has(normalized)) return 'work';
  if (TASK_STATUSES.has(normalized)) return 'task';
  if (WAITING_STATUSES.has(normalized)) return 'waiting';
  if (ERROR_STATUSES.has(normalized)) return 'error';
  if (OFFLINE_STATUSES.has(normalized)) return 'offline';
  if (DONE_STATUSES.has(normalized)) return 'done';
  if (IDLE_STATUSES.has(normalized)) return 'idle';
  return 'idle';
}

function agentZone(agent: AgentModel): OfficeZoneKey {
  const kind = statusKind(agentStatus(agent));
  if (kind === 'work') return 'work';
  if (kind === 'task') return 'task';
  if (kind === 'waiting') return 'waiting';
  if (kind === 'error') return 'maintenance';
  if (kind === 'offline') return 'sleep';
  return 'idle';
}

function agentProject(agent: AgentModel, t: (key: string) => string) {
  const source = agent as AgentModel & {
    project?: string;
    project_id?: string;
    project_name?: string;
    workspace?: string;
  };
  return source.project_name || source.project || source.project_id || source.workspace || t('unassignedProject');
}

function compactName(name: string) {
  return name.length > 18 ? `${name.slice(0, 16)}...` : name;
}

function groupAgentsByProject(agents: AgentModel[], t: (key: string) => string): AgentProjectGroup[] {
  const groups = new Map<string, AgentModel[]>();
  agents.forEach(agent => {
    const project = agentProject(agent, t);
    groups.set(project, [...(groups.get(project) || []), agent]);
  });

  return [...groups.entries()]
    .map(([project, projectAgents]) => ({ project, agents: projectAgents }))
    .sort((a, b) => {
      if (a.project === t('unassignedProject')) return 1;
      if (b.project === t('unassignedProject')) return -1;
      return a.project.localeCompare(b.project);
    });
}

function getProjectZones(agents: AgentModel[], t: (key: string) => string): OfficeZone[] {
  const zones: OfficeZone[] = [
    { key: 'work', label: t('workRoom'), icon: '▣', agents: [] },
    { key: 'task', label: t('taskRoom'), icon: '◆', agents: [] },
    { key: 'idle', label: t('idleLounge'), icon: '☕', agents: [] },
    { key: 'waiting', label: t('waitingArea'), icon: '⌛', agents: [] },
    { key: 'maintenance', label: t('maintenanceRoom'), icon: '!', agents: [] },
    { key: 'sleep', label: t('sleepZone'), icon: 'Z', agents: [] },
  ];
  const zoneByKey = new Map(zones.map(zone => [zone.key, zone]));

  agents.forEach(agent => {
    zoneByKey.get(agentZone(agent))?.agents.push(agent);
  });

  return zones.filter(zone => zone.agents.length > 0 || zone.key === 'work' || zone.key === 'idle');
}

function PixelPerson({ agent, index, pose = 'work' }: { agent: AgentModel; index: number; pose?: AgentStatusKind }) {
  const status = agentStatus(agent);
  const color = statusColor(status);
  const variant = index % 4;

  return (
    <div className={`pixel-person pixel-person-${variant} pixel-person-${pose}`} title={`${agent.name} - ${statusLabel(status)}`}>
      <span className="pixel-status" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
      <span className="pixel-head" />
      <span className="pixel-hair" />
      <span className="pixel-body" />
      <span className="pixel-arm pixel-arm-left" />
      <span className="pixel-arm pixel-arm-right" />
      {pose === 'idle' && <span className="pixel-coffee-cup" />}
      {pose === 'waiting' && <span className="pixel-wait-bubble">?</span>}
      {pose === 'error' && <span className="pixel-warning-bubble">!</span>}
      {pose === 'offline' && <span className="pixel-sleep-bubble">zzz</span>}
      {pose === 'done' && <span className="pixel-done-badge">✓</span>}
    </div>
  );
}

function PixelDesk({ agent, index, selectChat, zone, t }: { agent: AgentModel; index: number; selectChat?: (chatId: string) => void; zone: 'work' | 'task'; t: (key: string) => string }) {
  const status = agentStatus(agent);
  const progress = Math.max(0, Math.min(100, agent.progress ?? 0));
  const color = statusColor(status);
  const kind = statusKind(status);

  return (
    <button
      type="button"
      className={`pixel-workstation pixel-workstation-${zone}`}
      onClick={() => selectChat?.(agent.id)}
      title={`${agent.name}: ${agent.current_task || agent.last_action || statusLabel(status, t)}`}
    >
      <div className="pixel-desk">
        <div className="pixel-monitor">
          <i />
          <span style={{ width: `${Math.max(progress, 14)}%`, background: color }} />
        </div>
        <div className="pixel-keyboard" />
        <div className="pixel-mug" />
      </div>
      <PixelPerson agent={agent} index={index} pose={kind} />
      <div className="pixel-agent-label">
        <strong>{compactName(agent.name || agent.id)}</strong>
        <span style={{ color }}>{statusLabel(status, t)}</span>
      </div>
    </button>
  );
}

function PixelAgentSpot({ agent, index, selectChat, t }: { agent: AgentModel; index: number; selectChat?: (chatId: string) => void; t: (key: string) => string }) {
  const status = agentStatus(agent);
  const kind = statusKind(status);
  const color = statusColor(status);

  return (
    <button
      type="button"
      className={`pixel-agent-spot pixel-agent-spot-${kind}`}
      onClick={() => selectChat?.(agent.id)}
      title={`${agent.name}: ${agent.current_task || agent.last_action || statusLabel(status, t)}`}
    >
      <PixelPerson agent={agent} index={index} pose={kind} />
      <div className="pixel-agent-label">
        <strong>{compactName(agent.name || agent.id)}</strong>
        <span style={{ color }}>{statusLabel(status, t)}</span>
      </div>
    </button>
  );
}

function PixelZoneFurniture({ zone }: { zone: OfficeZoneKey }) {
  if (zone === 'idle') {
    return (
      <>
        <div className="pixel-sofa" />
        <div className="pixel-coffee-table" />
        <div className="pixel-bookshelf pixel-bookshelf-zone" />
      </>
    );
  }
  if (zone === 'waiting') {
    return <div className="pixel-task-board"><span /><span /><span /></div>;
  }
  if (zone === 'maintenance') {
    return (
      <>
        <div className="pixel-warning-sign">!</div>
        <div className="pixel-broken-monitor" />
      </>
    );
  }
  if (zone === 'sleep') {
    return <div className="pixel-sleep-pod"><span>zzz</span></div>;
  }
  if (zone === 'task') {
    return (
      <>
        <div className="pixel-task-board pixel-task-board-live"><span /><span /><span /></div>
        <div className="pixel-terminal-stack" />
      </>
    );
  }
  return <div className="pixel-wall-screen"><span /><span /></div>;
}

function PixelZone({ zone, selectChat, projectIndex, t }: { zone: OfficeZone; selectChat?: (chatId: string) => void; projectIndex: number; t: (key: string) => string }) {
  const isDeskZone = zone.key === 'work' || zone.key === 'task';

  return (
    <section className={`pixel-zone pixel-zone-${zone.key}`}>
      <div className="pixel-zone-label">
        <span>{zone.icon}</span>
        <strong>{zone.label}</strong>
        <em>{zone.agents.length}</em>
      </div>
      <PixelZoneFurniture zone={zone.key} />
      {zone.agents.length === 0 ? (
        <div className="pixel-zone-empty">{zone.key === 'work' ? 'Standby' : 'Clear'}</div>
      ) : (
        <div className={isDeskZone ? 'pixel-workstations' : 'pixel-zone-agents'}>
          {zone.agents.map((agent, index) => (
            isDeskZone ? (
              <PixelDesk key={agent.id} agent={agent} index={index + projectIndex} selectChat={selectChat} zone={zone.key === 'task' ? 'task' : 'work'} t={t} />
            ) : (
              <PixelAgentSpot key={agent.id} agent={agent} index={index + projectIndex} selectChat={selectChat} t={t} />
            )
          ))}
        </div>
      )}
    </section>
  );
}

function PixelOffice({ groups, selectChat, t }: { groups: AgentProjectGroup[]; selectChat?: (chatId: string) => void; t: (key: string) => string }) {
  const allAgents = groups.flatMap(group => group.agents);
  const workingCount = allAgents.filter(agent => ['work', 'task'].includes(statusKind(agentStatus(agent)))).length;
  const idleCount = allAgents.filter(agent => ['idle', 'done', 'waiting'].includes(statusKind(agentStatus(agent)))).length;
  const errorCount = allAgents.filter(agent => statusKind(agentStatus(agent)) === 'error').length;
  const offlineCount = allAgents.filter(agent => statusKind(agentStatus(agent)) === 'offline').length;
  const totalCount = groups.reduce((sum, group) => sum + group.agents.length, 0);

  return (
    <section className="pixel-office-shell">
      <div className="pixel-office-header">
        <div>
          <div style={styles.sceneKicker}>PIXEL AI OFFICE</div>
          <h3 className="pixel-office-title">{t('officeFloorTitle')}</h3>
        </div>
        <div className="pixel-office-stats">
          <span>{totalCount} {t('agentsLabel')}</span>
          <span>{workingCount} {t('workingLabel')}</span>
          <span>{idleCount} {t('idleLabel')}</span>
          <span>{errorCount} {t('errorLabel')}</span>
          <span>{offlineCount} {t('offlineLabel')}</span>
        </div>
      </div>

      <div className="pixel-office-map">
        {groups.length === 0 ? (
          <div className="pixel-empty-room">
            <BriefcaseBusiness size={28} />
            <span>{t('officeWaiting')}</span>
          </div>
        ) : (
          groups.map((group, groupIndex) => (
            <section key={group.project} className={`pixel-room pixel-room-${groupIndex % 4}`}>
              <div className="pixel-room-label">
                <BriefcaseBusiness size={14} />
                <span>{group.project}</span>
              </div>
              <div className="pixel-room-floor">
                <div className="pixel-plant pixel-plant-left" />
                <div className="pixel-plant pixel-plant-right" />
                <div className="pixel-project-zones">
                  {getProjectZones(group.agents, t).map(zone => (
                    <PixelZone key={zone.key} zone={zone} selectChat={selectChat} projectIndex={groupIndex} t={t} />
                  ))}
                </div>
              </div>
            </section>
          ))
        )}
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

  const groups = useMemo(() => groupAgentsByProject(agents, t), [agents, t]);

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

      <PixelOffice groups={groups} selectChat={selectChat} t={t} />

      {agents.length === 0 && !error && (
        <div className="glass-panel" style={{ padding: 18, color: 'var(--text-muted)', textAlign: 'center' }}>
          {t('officeWaiting')}
        </div>
      )}

      <div className="office-grid">
        {groups.map(group => (
          <section key={group.project} className="office-project-section">
            <h3 className="office-project-title">{group.project}</h3>
            <div className="office-project-cards">
              {group.agents.map(agent => {
                const status = agentStatus(agent);
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
                        {statusLabel(status, t).toUpperCase()}
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
          </section>
        ))}
      </div>
    </div>
  );
}
