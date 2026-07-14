import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  CircleDashed,
  Command,
  FileText,
  Grid2X2,
  List,
  Loader2,
  Maximize2,
  MessageSquare,
  Minus,
  Monitor,
  Pause,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  Users,
  Wifi,
  WifiOff,
  X,
  Zap,
} from 'lucide-react';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AgentEvent, AgentModel } from '../types';

type OfficeView = 'office' | 'command' | 'list';
type StatusKind = 'working' | 'waiting' | 'error' | 'paused' | 'offline';
type ZoneKey = 'work' | 'lounge' | 'meeting' | 'project' | 'idle' | 'error';
type GroupMode = 'project' | 'status';
type SortMode = 'name' | 'status' | 'activity';

interface OfficeTabProps {
  t: (key: string) => string;
  selectChat?: (chatId: string) => void;
  isConnected?: boolean;
  language?: 'en' | 'ru';
}

export interface OfficeAgent extends AgentModel {
  statusKind: StatusKind;
  projectLabel: string;
  projectId: string;
  zone: ZoneKey;
  activityAt: string;
}

interface OfficeProject {
  id: string;
  name: string;
  agents: OfficeAgent[];
  working: number;
  errors: number;
  events: AgentEvent[];
  accent: string;
}

interface OfficeZone {
  id: ZoneKey;
  label: string;
  shortLabel: string;
  agents: OfficeAgent[];
}

const VIEW_STORAGE_KEY = 'hermes_office_view';
const AGENT_STORAGE_KEY = 'hermes_office_agent';
const PROJECT_STORAGE_KEY = 'hermes_office_project';
const POLL_INTERVAL = 4_000;
const STATUS_ORDER: StatusKind[] = ['working', 'waiting', 'error', 'paused', 'offline'];
const PROJECT_COLORS = ['#55e8c1', '#7b9cff', '#b77cff', '#ff72be', '#ffb85c', '#54c8ee'];

const COPY = {
  ru: {
    subtitle: 'Живое состояние агентов в реальном времени', search: 'Поиск агента…', allProjects: 'Все проекты', allStatuses: 'Все статусы',
    total: 'Всего', working: 'Работают', waiting: 'Ожидают', errors: 'Ошибки', paused: 'На паузе', offline: 'Неактивны',
    online: 'Онлайн', reconnecting: 'Переподключение', stale: 'Данные устарели', office: 'Pixel Office', command: 'Command Center', list: 'Список',
    zones: 'Зоны офиса', projects: 'Проекты', fit: 'Вписать в экран', filters: 'Фильтры', noResults: 'По заданным фильтрам ничего не найдено',
    noAgents: 'Офис пока пуст', retrying: 'Не удалось обновить данные. Повторяем попытку в фоне.', chat: 'Открыть чат', details: 'Сведения',
    currentTask: 'Текущая задача', lastActivity: 'Последняя активность', model: 'Модель', eventHistory: 'История событий', noEvents: 'Событий пока нет',
    project: 'Проект', role: 'Роль', progress: 'Прогресс', close: 'Закрыть Inspector', focus: 'Фокус проекта', back: 'Общий вид',
    activeAgents: 'Активных агентов', projectErrors: 'Ошибок', projectEvents: 'Событий', groupBy: 'Группировка', sortBy: 'Сортировка',
    byProject: 'По проекту', byStatus: 'По статусу', byName: 'По имени', byActivity: 'По активности', byState: 'По статусу', open: 'Открыть',
    workZone: 'Рабочая зона', lounge: 'Lounge', meeting: 'Meeting Room', projectRoom: 'Проектная комната', idleZone: 'Idle Zone', support: 'Support / Ошибки',
    unassigned: 'Без проекта', specialist: 'Специалист', noTask: 'Нет активной задачи', refreshed: 'Обновлено', agents: 'агентов', logs: 'Логи',
  },
  en: {
    subtitle: 'Live agent state in real time', search: 'Search agents…', allProjects: 'All projects', allStatuses: 'All statuses',
    total: 'Total', working: 'Working', waiting: 'Waiting', errors: 'Errors', paused: 'Paused', offline: 'Inactive',
    online: 'Online', reconnecting: 'Reconnecting', stale: 'Stale data', office: 'Pixel Office', command: 'Command Center', list: 'List',
    zones: 'Office zones', projects: 'Projects', fit: 'Fit to screen', filters: 'Filters', noResults: 'No agents match the selected filters',
    noAgents: 'The office is empty', retrying: 'Could not refresh data. Retrying in the background.', chat: 'Open chat', details: 'Details',
    currentTask: 'Current task', lastActivity: 'Last activity', model: 'Model', eventHistory: 'Event history', noEvents: 'No events yet',
    project: 'Project', role: 'Role', progress: 'Progress', close: 'Close inspector', focus: 'Project focus', back: 'Overview',
    activeAgents: 'Active agents', projectErrors: 'Errors', projectEvents: 'Events', groupBy: 'Group', sortBy: 'Sort',
    byProject: 'By project', byStatus: 'By status', byName: 'By name', byActivity: 'By activity', byState: 'By status', open: 'Open',
    workZone: 'Work zone', lounge: 'Lounge', meeting: 'Meeting Room', projectRoom: 'Project room', idleZone: 'Idle Zone', support: 'Support / Errors',
    unassigned: 'Unassigned', specialist: 'Specialist', noTask: 'No active task', refreshed: 'Updated', agents: 'agents', logs: 'Logs',
  },
} as const;

function hashString(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

export function normalizeOfficeStatus(agent: AgentModel): StatusKind {
  if (agent.is_enabled === false) return 'offline';
  const status = (agent.status || 'idle').trim().toLowerCase();
  if (['active', 'working', 'running', 'processing', 'busy'].includes(status)) return 'working';
  if (['waiting', 'queued', 'pending', 'done', 'completed', 'complete', 'success'].includes(status)) return 'waiting';
  if (['error', 'failed', 'failure'].includes(status) || agent.last_error) return 'error';
  if (['paused', 'idle'].includes(status)) return 'paused';
  if (['offline', 'disabled', 'sleeping', 'sleep', 'inactive'].includes(status)) return 'offline';
  return 'paused';
}

export function assignOfficeZone(agent: AgentModel, statusKind = normalizeOfficeStatus(agent)): ZoneKey {
  if (statusKind === 'error') return 'error';
  if (statusKind === 'offline' || statusKind === 'paused') return 'idle';
  if (statusKind === 'waiting') return 'lounge';
  if (agent.parent_id || (agent.agent_type || '').includes('orchestrator')) return 'meeting';
  if (['running', 'processing'].includes((agent.status || '').toLowerCase())) return 'project';
  return 'work';
}

function projectName(agent: AgentModel, unassigned: string) {
  return agent.project_name || agent.project || agent.workspace || agent.project_id || unassigned;
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9а-яё]+/gi, '-').replace(/^-|-$/g, '') || 'unassigned';
}

export function normalizeOfficeAgents(agents: AgentModel[], unassigned = 'Unassigned'): OfficeAgent[] {
  return agents.map(agent => {
    const statusKind = normalizeOfficeStatus(agent);
    const projectLabel = projectName(agent, unassigned);
    return {
      ...agent,
      statusKind,
      projectLabel,
      projectId: agent.project_id || slug(projectLabel),
      zone: assignOfficeZone(agent, statusKind),
      activityAt: agent.updated_at || agent.recent_events?.[0]?.timestamp || agent.created_at || '',
    };
  });
}

function statusLabel(status: StatusKind, copy: typeof COPY.ru | typeof COPY.en) {
  return status === 'working' ? copy.working : status === 'waiting' ? copy.waiting : status === 'error' ? copy.errors : status === 'paused' ? copy.paused : copy.offline;
}

function statusIcon(status: StatusKind, size = 14) {
  if (status === 'working') return <Zap size={size} />;
  if (status === 'waiting') return <CircleDashed size={size} />;
  if (status === 'error') return <AlertTriangle size={size} />;
  if (status === 'paused') return <Pause size={size} />;
  return <WifiOff size={size} />;
}

function formatRelative(value: string, language: 'en' | 'ru') {
  if (!value) return '—';
  const timestamp = Date.parse(value.includes('T') ? value : value.replace(' ', 'T'));
  if (Number.isNaN(timestamp)) return value;
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return language === 'ru' ? 'только что' : 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return language === 'ru' ? `${minutes} мин назад` : `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return language === 'ru' ? `${hours} ч назад` : `${hours}h ago`;
  return new Intl.DateTimeFormat(language === 'ru' ? 'ru-RU' : 'en-US', { day: '2-digit', month: 'short' }).format(timestamp);
}

function eventTime(value: string) {
  if (!value) return '—';
  const match = value.match(/(\d{1,2}:\d{2})/);
  return match?.[1] || value.slice(0, 5);
}

function officeSignature(agents: AgentModel[]) {
  return agents.map(agent => `${agent.id}:${agent.status}:${agent.updated_at}:${agent.progress}:${agent.recent_events?.[0]?.id || ''}`).join('|');
}

const PixelAvatar = memo(function PixelAvatar({ agent, size = 'md' }: { agent: OfficeAgent; size?: 'sm' | 'md' | 'lg' }) {
  const variant = hashString(agent.id || agent.name) % 8;
  return (
    <span className={`office-avatar office-avatar-${size} office-avatar-${variant} is-${agent.statusKind}`} aria-hidden="true">
      <i className="office-avatar-shadow" /><i className="office-avatar-hair" /><i className="office-avatar-head" /><i className="office-avatar-face" />
      <i className="office-avatar-body" /><i className="office-avatar-arm left" /><i className="office-avatar-arm right" /><i className="office-avatar-leg left" /><i className="office-avatar-leg right" />
      {agent.statusKind === 'error' && <b>!</b>}{agent.statusKind === 'offline' && <b>z</b>}
    </span>
  );
});

const AgentSprite = memo(function AgentSprite({ agent, selected, onSelect, copy }: { agent: OfficeAgent; selected: boolean; onSelect: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en }) {
  return (
    <button
      type="button"
      className={`office-agent-sprite is-${agent.statusKind}${selected ? ' is-selected' : ''}`}
      onClick={event => onSelect(agent, event.currentTarget)}
      aria-label={`${agent.name}, ${statusLabel(agent.statusKind, copy)}`}
      aria-pressed={selected}
      title={`${agent.name}: ${agent.current_task || agent.last_action || copy.noTask}`}
    >
      <span className="office-pixel-desk"><i /><b /><em /></span>
      <PixelAvatar agent={agent} />
      <span className="office-sprite-label"><strong>{agent.name || agent.id}</strong><small>{statusLabel(agent.statusKind, copy)}</small></span>
    </button>
  );
});

function ZoneDecor({ zone }: { zone: ZoneKey }) {
  return (
    <div className={`office-zone-decor decor-${zone}`} aria-hidden="true">
      {zone === 'lounge' && <><i className="decor-sofa" /><i className="decor-table" /><i className="decor-plant" /></>}
      {zone === 'meeting' && <><i className="decor-board" /><i className="decor-meeting-table" /></>}
      {zone === 'project' && <><i className="decor-terminal one" /><i className="decor-terminal two" /></>}
      {zone === 'idle' && <><i className="decor-beanbag one" /><i className="decor-beanbag two" /></>}
      {zone === 'error' && <><i className="decor-error-monitor one" /><i className="decor-error-monitor two" /></>}
      {zone === 'work' && <><i className="decor-window" /><i className="decor-plant" /></>}
    </div>
  );
}

const OfficeRoom = memo(function OfficeRoom({ zone, selectedAgentId, onSelect, copy, mobileActive }: { zone: OfficeZone; selectedAgentId: string; onSelect: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en; mobileActive: boolean }) {
  return (
    <section className={`office-room room-${zone.id}${mobileActive ? ' is-mobile-active' : ''}`} aria-labelledby={`zone-${zone.id}`}>
      <header><span className="office-zone-symbol">{zone.id === 'error' ? '!' : zone.id === 'lounge' ? '☕' : zone.id === 'meeting' ? '◆' : '▣'}</span><h3 id={`zone-${zone.id}`}>{zone.label}</h3><strong>{zone.agents.length}</strong></header>
      <ZoneDecor zone={zone.id} />
      <div className="office-room-agents">
        {zone.agents.map(agent => <AgentSprite key={agent.id} agent={agent} selected={selectedAgentId === agent.id} onSelect={onSelect} copy={copy} />)}
      </div>
    </section>
  );
});

function PixelOfficeView({ zones, selectedAgentId, onSelect, copy, zoom, mobileZone }: { zones: OfficeZone[]; selectedAgentId: string; onSelect: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en; zoom: number; mobileZone: ZoneKey }) {
  return (
    <div className="office-map-viewport" tabIndex={0} aria-label={copy.office}>
      <div className="office-pixel-map" style={{ '--office-zoom': zoom } as React.CSSProperties}>
        <div className="office-map-grid" aria-hidden="true" />
        {zones.map(zone => <OfficeRoom key={zone.id} zone={zone} selectedAgentId={selectedAgentId} onSelect={onSelect} copy={copy} mobileActive={mobileZone === zone.id} />)}
      </div>
    </div>
  );
}

function ActivityOverlay({ projects }: { projects: OfficeProject[] }) {
  const projectIndex = new Map(projects.map((project, index) => [project.id, index]));
  const agentProject = new Map(projects.flatMap(project => project.agents.map(agent => [agent.id, project.id] as const)));
  const links = projects.flatMap((project, sourceIndex) => project.events.flatMap(event => {
    const metadata = event.metadata || {};
    const targetProject = String(metadata.target_project_id || agentProject.get(String(metadata.target_agent_id || '')) || metadata.project_id || '');
    const targetIndex = projectIndex.get(targetProject);
    if (targetIndex === undefined || targetIndex === sourceIndex) return [];
    return [{ id: `${project.id}-${event.id}`, sourceIndex, targetIndex, error: event.status === 'error' }];
  })).slice(0, 6);
  if (!links.length) return null;
  return (
    <svg className="command-activity-overlay" viewBox="0 0 1000 620" preserveAspectRatio="none" aria-label="Live project activity">
      {links.map(link => {
        const x1 = 170 + (link.sourceIndex % 3) * 330;
        const y1 = 150 + Math.floor(link.sourceIndex / 3) * 300;
        const x2 = 170 + (link.targetIndex % 3) * 330;
        const y2 = 150 + Math.floor(link.targetIndex / 3) * 300;
        return <path key={link.id} d={`M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1 - 80}, ${(x1 + x2) / 2} ${y2 + 80}, ${x2} ${y2}`} className={link.error ? 'is-error' : ''} />;
      })}
    </svg>
  );
}

const ProjectPlatform = memo(function ProjectPlatform({ project, focused, dimmed, onFocus, onSelectAgent, copy }: { project: OfficeProject; focused: boolean; dimmed: boolean; onFocus: (id: string) => void; onSelectAgent: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en }) {
  return (
    <article className={`command-platform${focused ? ' is-focused' : ''}${dimmed ? ' is-dimmed' : ''}`} style={{ '--project-accent': project.accent } as React.CSSProperties}>
      <div className="command-platform-surface">
        <span className="platform-grid" aria-hidden="true" />
        <button type="button" className="platform-focus-button" onClick={() => onFocus(project.id)} aria-label={`${copy.focus}: ${project.name}`}>
          <Maximize2 size={15} />
        </button>
        <div className="platform-agents" role="list" aria-label={project.name}>
          {project.agents.slice(0, 10).map(agent => (
            <button key={agent.id} type="button" role="listitem" className="platform-agent" onClick={event => onSelectAgent(agent, event.currentTarget)} aria-label={agent.name} title={agent.name}>
              <PixelAvatar agent={agent} size="sm" />
            </button>
          ))}
          {project.agents.length > 10 && <span className="platform-overflow">+{project.agents.length - 10}</span>}
        </div>
        <div className="platform-terminal" aria-hidden="true"><i /><i /></div>
      </div>
      <footer><strong title={project.name}>{project.name}</strong><span>{project.agents.length} {copy.agents}</span></footer>
    </article>
  );
});

function CommandCenterView({ projects, focusedProject, onFocus, onSelectAgent, copy }: { projects: OfficeProject[]; focusedProject: string; onFocus: (id: string) => void; onSelectAgent: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en }) {
  const visibleProjects = focusedProject ? projects.filter(project => project.id === focusedProject) : projects;
  const focus = projects.find(project => project.id === focusedProject);
  return (
    <div className={`command-center-map${focusedProject ? ' is-focus-mode' : ''}`}>
      <div className="command-grid-floor" aria-hidden="true" />
      {!focusedProject && <ActivityOverlay projects={projects} />}
      {focusedProject && focus && (
        <div className="command-focus-header">
          <button type="button" onClick={() => onFocus('')}><ArrowLeft size={16} />{copy.back}</button>
          <div><span>{copy.focus}</span><h3>{focus.name}</h3></div>
          <dl><div><dt>{copy.activeAgents}</dt><dd>{focus.working}</dd></div><div><dt>{copy.projectErrors}</dt><dd>{focus.errors}</dd></div><div><dt>{copy.projectEvents}</dt><dd>{focus.events.length}</dd></div></dl>
        </div>
      )}
      <div className="command-platforms">
        {visibleProjects.map(project => <ProjectPlatform key={project.id} project={project} focused={project.id === focusedProject} dimmed={Boolean(focusedProject && project.id !== focusedProject)} onFocus={onFocus} onSelectAgent={onSelectAgent} copy={copy} />)}
      </div>
      {focusedProject && focus && (
        <div className="command-focus-timeline">
          <h4>{copy.eventHistory}</h4>
          {focus.events.length ? focus.events.slice(0, 8).map(event => <div key={`${event.agent_id}-${event.id}`}><time>{eventTime(event.timestamp)}</time><span>{event.message}</span></div>) : <p>{copy.noEvents}</p>}
        </div>
      )}
    </div>
  );
}

const CompactAgentRow = memo(function CompactAgentRow({ agent, onSelect, copy, language }: { agent: OfficeAgent; onSelect: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en; language: 'en' | 'ru' }) {
  return (
    <article className="compact-agent-row" role="listitem">
      <PixelAvatar agent={agent} size="sm" />
      <div className="compact-agent-identity"><strong title={agent.name}>{agent.name}</strong><span>{agent.role || copy.specialist}</span></div>
      <span className="compact-agent-project" title={agent.projectLabel}>{agent.projectLabel}</span>
      <span className={`office-status-pill is-${agent.statusKind}`}>{statusIcon(agent.statusKind)}{statusLabel(agent.statusKind, copy)}</span>
      <span className="compact-agent-task" title={agent.current_task || agent.last_action || copy.noTask}>{agent.current_task || agent.last_action || copy.noTask}</span>
      <time>{formatRelative(agent.activityAt, language)}</time>
      <button type="button" onClick={event => onSelect(agent, event.currentTarget)} aria-label={`${copy.open}: ${agent.name}`}>{copy.open}</button>
    </article>
  );
});

function CompactListView({ agents, onSelect, copy, language, groupMode, setGroupMode, sortMode, setSortMode }: { agents: OfficeAgent[]; onSelect: (agent: OfficeAgent, trigger: HTMLButtonElement) => void; copy: typeof COPY.ru | typeof COPY.en; language: 'en' | 'ru'; groupMode: GroupMode; setGroupMode: (value: GroupMode) => void; sortMode: SortMode; setSortMode: (value: SortMode) => void }) {
  const groups = useMemo(() => {
    const sorted = [...agents].sort((a, b) => sortMode === 'name' ? a.name.localeCompare(b.name) : sortMode === 'status' ? STATUS_ORDER.indexOf(a.statusKind) - STATUS_ORDER.indexOf(b.statusKind) : (b.activityAt || '').localeCompare(a.activityAt || ''));
    const map = new Map<string, OfficeAgent[]>();
    sorted.forEach(agent => {
      const key = groupMode === 'project' ? agent.projectLabel : statusLabel(agent.statusKind, copy);
      map.set(key, [...(map.get(key) || []), agent]);
    });
    return [...map.entries()];
  }, [agents, copy, groupMode, sortMode]);
  return (
    <div className="compact-list-view">
      <div className="compact-list-tools">
        <label>{copy.groupBy}<select value={groupMode} onChange={event => setGroupMode(event.target.value as GroupMode)}><option value="project">{copy.byProject}</option><option value="status">{copy.byStatus}</option></select><ChevronDown size={14} /></label>
        <label>{copy.sortBy}<select value={sortMode} onChange={event => setSortMode(event.target.value as SortMode)}><option value="name">{copy.byName}</option><option value="status">{copy.byState}</option><option value="activity">{copy.byActivity}</option></select><ChevronDown size={14} /></label>
      </div>
      <div className="compact-list-header" aria-hidden="true"><span /><span>{copy.project}</span><span>{copy.byState}</span><span>{copy.currentTask}</span><span>{copy.lastActivity}</span><span /></div>
      {groups.map(([group, groupAgents]) => <section key={group} className="compact-agent-group"><h3>{group}<span>{groupAgents.length}</span></h3><div role="list">{groupAgents.map(agent => <CompactAgentRow key={agent.id} agent={agent} onSelect={onSelect} copy={copy} language={language} />)}</div></section>)}
    </div>
  );
}

function AgentInspector({ agent, copy, language, onClose, onChat, panelRef }: { agent: OfficeAgent; copy: typeof COPY.ru | typeof COPY.en; language: 'en' | 'ru'; onClose: () => void; onChat?: (id: string) => void; panelRef: React.RefObject<HTMLElement | null> }) {
  const progress = Math.max(0, Math.min(100, agent.progress || 0));
  return (
    <aside className="agent-inspector" ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="inspector-agent-name">
      <button type="button" className="inspector-close" onClick={onClose} aria-label={copy.close}><X size={18} /></button>
      <header><PixelAvatar agent={agent} size="lg" /><div><h2 id="inspector-agent-name" title={agent.name}>{agent.name}</h2><p>{agent.role || copy.specialist}</p><span className={`office-status-pill is-${agent.statusKind}`}>{statusIcon(agent.statusKind)}{statusLabel(agent.statusKind, copy)}</span></div></header>
      <div className="inspector-actions">
        {onChat && <button type="button" className="inspector-chat" onClick={() => onChat(agent.id)}><MessageSquare size={16} />{copy.chat}</button>}
        <button type="button" className="inspector-logs" onClick={() => panelRef.current?.querySelector('.inspector-events')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}><FileText size={15} />{copy.logs}</button>
      </div>
      <dl className="inspector-details">
        <div><dt>{copy.project}</dt><dd>{agent.projectLabel}</dd></div><div><dt>{copy.model}</dt><dd title={agent.model}>{agent.model || '—'}</dd></div>
        <div><dt>{copy.currentTask}</dt><dd>{agent.current_task || copy.noTask}</dd></div><div><dt>{copy.lastActivity}</dt><dd>{formatRelative(agent.activityAt, language)}</dd></div>
      </dl>
      {(agent.progress !== undefined || agent.statusKind === 'working') && <div className="inspector-progress"><span>{copy.progress}<strong>{progress}%</strong></span><i><b style={{ width: `${progress}%` }} /></i></div>}
      {agent.last_error && <div className="inspector-error"><AlertTriangle size={16} /><span>{agent.last_error}</span></div>}
      <section className="inspector-events"><h3>{copy.eventHistory}</h3>{agent.recent_events?.length ? <ol>{agent.recent_events.map(event => <li key={event.id}><time>{eventTime(event.timestamp)}</time><i className={`is-${event.status}`} /><div><strong>{event.event_type.replace(/_/g, ' ')}</strong><span>{event.message}</span>{event.task && <small>{event.task}</small>}</div></li>)}</ol> : <div className="inspector-empty"><Sparkles size={18} />{copy.noEvents}</div>}</section>
    </aside>
  );
}

function ViewSwitcher({ view, setView, copy }: { view: OfficeView; setView: (view: OfficeView) => void; copy: typeof COPY.ru | typeof COPY.en }) {
  const views: { id: OfficeView; label: string; icon: React.ReactNode }[] = [{ id: 'office', label: copy.office, icon: <Grid2X2 size={15} /> }, { id: 'command', label: copy.command, icon: <Command size={15} /> }, { id: 'list', label: copy.list, icon: <List size={15} /> }];
  return <div className="office-view-switcher" role="tablist" aria-label="Office view">{views.map(item => <button key={item.id} type="button" role="tab" aria-selected={view === item.id} className={view === item.id ? 'is-active' : ''} onClick={() => setView(item.id)}>{item.icon}<span>{item.label}</span></button>)}</div>;
}

export function OfficeTab({ t, selectChat, isConnected = false, language = 'ru' }: OfficeTabProps) {
  const copy = COPY[language];
  const [rawAgents, setRawAgents] = useState<AgentModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [view, setViewState] = useState<OfficeView>(() => {
    const saved = localStorage.getItem(VIEW_STORAGE_KEY);
    return saved === 'command' || saved === 'list' ? saved : 'office';
  });
  const [search, setSearch] = useState('');
  const [projectFilter, setProjectFilter] = useState(() => localStorage.getItem(PROJECT_STORAGE_KEY) || '');
  const [statusFilter, setStatusFilter] = useState<StatusKind | ''>('');
  const [selectedAgentId, setSelectedAgentId] = useState(() => localStorage.getItem(AGENT_STORAGE_KEY) || '');
  const [focusedProject, setFocusedProject] = useState('');
  const [zoom, setZoom] = useState(1);
  const [mobileZone, setMobileZone] = useState<ZoneKey>('work');
  const [groupMode, setGroupMode] = useState<GroupMode>('project');
  const [sortMode, setSortMode] = useState<SortMode>('name');
  const inspectorRef = useRef<HTMLElement | null>(null);
  const lastTriggerRef = useRef<HTMLElement | null>(null);
  const didAutoSelectRef = useRef(Boolean(localStorage.getItem(AGENT_STORAGE_KEY)));

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    let failures = 0;
    let hasLoaded = false;
    let controller: AbortController | null = null;
    const load = async () => {
      if (cancelled) return;
      if (document.visibilityState === 'hidden' && hasLoaded) {
        timer = window.setTimeout(load, POLL_INTERVAL);
        return;
      }
      controller = new AbortController();
      setRefreshing(hasLoaded);
      try {
        const token = localStorage.getItem('jarvis_auth_token');
        const response = await fetch('/api/office/state', { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json() as { agents?: AgentModel[] };
        if (cancelled) return;
        const next = Array.isArray(data.agents) ? data.agents : [];
        setRawAgents(previous => officeSignature(previous) === officeSignature(next) ? previous : next);
        setError('');
        setLastUpdated(new Date());
        failures = 0;
      } catch (loadError) {
        if (cancelled || (loadError instanceof DOMException && loadError.name === 'AbortError')) return;
        failures += 1;
        setError(loadError instanceof Error ? loadError.message : 'Office state unavailable');
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
          hasLoaded = true;
          timer = window.setTimeout(load, Math.min(30_000, POLL_INTERVAL * Math.max(1, 2 ** (failures - 1))));
        }
      }
    };
    void load();
    return () => { cancelled = true; window.clearTimeout(timer); controller?.abort(); };
  }, []);

  const agents = useMemo(() => normalizeOfficeAgents(rawAgents, copy.unassigned), [copy.unassigned, rawAgents]);
  const projects = useMemo<OfficeProject[]>(() => {
    const map = new Map<string, OfficeAgent[]>();
    agents.forEach(agent => map.set(agent.projectId, [...(map.get(agent.projectId) || []), agent]));
    return [...map.entries()].map(([id, projectAgents]) => ({ id, name: projectAgents[0].projectLabel, agents: projectAgents, working: projectAgents.filter(agent => agent.statusKind === 'working').length, errors: projectAgents.filter(agent => agent.statusKind === 'error').length, events: projectAgents.flatMap(agent => agent.recent_events || []).sort((a, b) => b.timestamp.localeCompare(a.timestamp)), accent: PROJECT_COLORS[hashString(id) % PROJECT_COLORS.length] })).sort((a, b) => a.name.localeCompare(b.name));
  }, [agents]);
  const filteredAgents = useMemo(() => {
    const query = search.trim().toLowerCase();
    return agents.filter(agent => (!query || `${agent.name} ${agent.role || ''} ${agent.current_task || ''} ${agent.projectLabel}`.toLowerCase().includes(query)) && (!projectFilter || agent.projectId === projectFilter) && (!statusFilter || agent.statusKind === statusFilter));
  }, [agents, projectFilter, search, statusFilter]);
  const zones = useMemo<OfficeZone[]>(() => {
    const definitions: [ZoneKey, string, string][] = [['work', copy.workZone, copy.workZone], ['lounge', copy.lounge, copy.lounge], ['meeting', copy.meeting, copy.meeting], ['project', copy.projectRoom, copy.projectRoom], ['idle', copy.idleZone, copy.idleZone], ['error', copy.support, copy.support]];
    return definitions.map(([id, label, shortLabel]) => ({ id, label, shortLabel, agents: filteredAgents.filter(agent => agent.zone === id) }));
  }, [copy, filteredAgents]);
  const visibleProjects = useMemo(() => projects.map(project => ({ ...project, agents: project.agents.filter(agent => filteredAgents.some(item => item.id === agent.id)) })).filter(project => project.agents.length), [filteredAgents, projects]);
  const selectedAgent = agents.find(agent => agent.id === selectedAgentId) || null;
  const counts = useMemo(() => ({ total: agents.length, working: agents.filter(agent => agent.statusKind === 'working').length, waiting: agents.filter(agent => agent.statusKind === 'waiting').length, error: agents.filter(agent => agent.statusKind === 'error').length, paused: agents.filter(agent => agent.statusKind === 'paused').length, offline: agents.filter(agent => agent.statusKind === 'offline').length }), [agents]);

  useEffect(() => {
    if (selectedAgentId && !selectedAgent) {
      setSelectedAgentId('');
      localStorage.removeItem(AGENT_STORAGE_KEY);
    }
  }, [selectedAgent, selectedAgentId]);

  useEffect(() => {
    const isDesktop = typeof window.matchMedia !== 'function' || window.matchMedia('(min-width: 769px)').matches;
    if (!isDesktop || loading || selectedAgentId || didAutoSelectRef.current || !agents.length || view !== 'office') return;
    const preferred = agents.find(agent => agent.statusKind === 'working') || agents[0];
    didAutoSelectRef.current = true;
    setSelectedAgentId(preferred.id);
    localStorage.setItem(AGENT_STORAGE_KEY, preferred.id);
  }, [agents, loading, selectedAgentId, view]);

  const setView = useCallback((next: OfficeView) => { setViewState(next); localStorage.setItem(VIEW_STORAGE_KEY, next); }, []);
  const selectAgent = useCallback((agent: OfficeAgent, trigger: HTMLButtonElement) => {
    lastTriggerRef.current = trigger;
    setSelectedAgentId(agent.id);
    localStorage.setItem(AGENT_STORAGE_KEY, agent.id);
    window.setTimeout(() => inspectorRef.current?.querySelector<HTMLElement>('button')?.focus(), 0);
  }, []);
  const closeInspector = useCallback(() => {
    setSelectedAgentId('');
    localStorage.removeItem(AGENT_STORAGE_KEY);
    window.setTimeout(() => lastTriggerRef.current?.focus(), 0);
  }, []);

  useEffect(() => {
    if (!selectedAgent) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); closeInspector(); return; }
      if (event.key !== 'Tab' || !inspectorRef.current) return;
      const focusable = [...inspectorRef.current.querySelectorAll<HTMLElement>('button, [href], select, input, [tabindex]:not([tabindex="-1"])')].filter(element => !element.hasAttribute('disabled'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [closeInspector, selectedAgent]);

  const chooseProject = (id: string) => { setProjectFilter(id); localStorage.setItem(PROJECT_STORAGE_KEY, id); setFocusedProject(''); };
  const connectionKind = error && rawAgents.length ? 'stale' : isConnected ? 'online' : 'reconnecting';
  const connectionLabel = connectionKind === 'stale' ? copy.stale : connectionKind === 'online' ? copy.online : copy.reconnecting;
  const statusCounters: { key: StatusKind | ''; label: string; value: number }[] = [{ key: '', label: copy.total, value: counts.total }, { key: 'working', label: copy.working, value: counts.working }, { key: 'waiting', label: copy.waiting, value: counts.waiting }, { key: 'error', label: copy.errors, value: counts.error }, { key: 'offline', label: copy.offline, value: counts.offline }];

  return (
    <div className={`ai-office-page view-${view}${selectedAgent ? ' has-inspector' : ''}`}>
      <header className="office-command-bar">
        <div className="office-brand"><span><Bot size={23} /></span><div><h1>{t('officeTitle')}</h1><p>{copy.subtitle}</p></div></div>
        <div className="office-filters">
          <label className="office-search"><Search size={16} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder={copy.search} aria-label={copy.search} />{search && <button type="button" onClick={() => setSearch('')} aria-label="Clear search"><X size={14} /></button>}</label>
          <label className="office-select"><BriefcaseBusiness size={15} /><select value={projectFilter} onChange={event => chooseProject(event.target.value)} aria-label={copy.allProjects}><option value="">{copy.allProjects}</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select><ChevronDown size={14} /></label>
          <label className="office-select"><SlidersHorizontal size={15} /><select value={statusFilter} onChange={event => setStatusFilter(event.target.value as StatusKind | '')} aria-label={copy.allStatuses}><option value="">{copy.allStatuses}</option>{STATUS_ORDER.map(status => <option key={status} value={status}>{statusLabel(status, copy)}</option>)}</select><ChevronDown size={14} /></label>
        </div>
        <div className="office-command-actions"><ViewSwitcher view={view} setView={setView} copy={copy} /><div className={`office-connection is-${connectionKind}`} role="status">{connectionKind === 'online' ? <Wifi size={15} /> : connectionKind === 'stale' ? <AlertTriangle size={15} /> : <Loader2 size={15} />}<span>{connectionLabel}</span></div></div>
        <div className="office-counters" role="group" aria-label="Agent status filters">{statusCounters.map(counter => <button type="button" key={counter.key || 'total'} className={`is-${counter.key || 'total'}${statusFilter === counter.key ? ' is-active' : ''}`} onClick={() => setStatusFilter(current => current === counter.key ? '' : counter.key)} aria-pressed={statusFilter === counter.key} title={`${counter.label}: ${counter.value}`}><span>{counter.label}</span><strong>{counter.value}</strong><i />{statusFilter === counter.key && <Check size={12} />}</button>)}</div>
      </header>

      {error && <div className="office-refresh-warning" role="status"><AlertTriangle size={16} /><span>{copy.retrying}</span>{lastUpdated && <small>{copy.refreshed}: {lastUpdated.toLocaleTimeString(language === 'ru' ? 'ru-RU' : 'en-US', { hour: '2-digit', minute: '2-digit' })}</small>}</div>}
      {loading ? <div className="office-loading" aria-label="Loading"><span /><span /><span /></div> : rawAgents.length === 0 ? <div className="office-empty"><Bot size={32} /><h2>{copy.noAgents}</h2></div> : (
        <div className="office-workspace">
          <aside className="office-context-sidebar">
            <div className="context-sidebar-title"><span>{view === 'command' ? copy.projects : copy.zones}</span>{refreshing && <Loader2 size={14} />}</div>
            {view === 'command' ? <nav>{projects.map(project => <button key={project.id} type="button" className={focusedProject === project.id ? 'is-active' : ''} onClick={() => setFocusedProject(focusedProject === project.id ? '' : project.id)}><i style={{ background: project.accent }}><BriefcaseBusiness size={13} /></i><span><strong title={project.name}>{project.name}</strong><small>{project.agents.length} {copy.agents}</small></span><em>{project.errors || ''}</em></button>)}</nav> : <nav>{zones.map(zone => <button key={zone.id} type="button" className={statusFilter && zone.agents.length ? 'has-filter' : ''} onClick={() => setStatusFilter(zone.id === 'error' ? 'error' : zone.id === 'idle' ? 'paused' : zone.id === 'lounge' ? 'waiting' : zone.id === 'work' ? 'working' : '')}><i><Monitor size={13} /></i><span><strong title={zone.label}>{zone.shortLabel}</strong><small>{zone.agents.length} {copy.agents}</small></span></button>)}</nav>}
            {view === 'office' && <div className="office-zoom-controls"><span>{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoom(value => Math.max(.75, value - .1))} aria-label="Zoom out"><Minus size={15} /></button><button type="button" onClick={() => setZoom(1)} aria-label={copy.fit}><Maximize2 size={14} /></button><button type="button" onClick={() => setZoom(value => Math.min(1.25, value + .1))} aria-label="Zoom in"><Plus size={15} /></button></div>}
          </aside>
          <main className="office-stage">
            {view === 'office' && <nav className="office-mobile-zone-picker" aria-label={copy.zones}>{zones.map(zone => <button type="button" key={zone.id} className={mobileZone === zone.id ? 'is-active' : ''} onClick={() => setMobileZone(zone.id)}><span>{zone.id === 'error' ? '!' : zone.id === 'lounge' ? '☕' : zone.id === 'meeting' ? '◆' : '▣'}</span><strong>{zone.shortLabel}</strong><em>{zone.agents.length}</em></button>)}</nav>}
            {filteredAgents.length === 0 ? <div className="office-no-results"><Search size={24} /><span>{copy.noResults}</span></div> : view === 'office' ? <PixelOfficeView zones={zones} selectedAgentId={selectedAgentId} onSelect={selectAgent} copy={copy} zoom={zoom} mobileZone={mobileZone} /> : view === 'command' ? <CommandCenterView projects={visibleProjects} focusedProject={focusedProject} onFocus={setFocusedProject} onSelectAgent={selectAgent} copy={copy} /> : <CompactListView agents={filteredAgents} onSelect={selectAgent} copy={copy} language={language} groupMode={groupMode} setGroupMode={setGroupMode} sortMode={sortMode} setSortMode={setSortMode} />}
          </main>
          {selectedAgent && <AgentInspector agent={selectedAgent} copy={copy} language={language} onClose={closeInspector} onChat={selectChat} panelRef={inspectorRef} />}
        </div>
      )}
      <nav className="office-mobile-nav" aria-label="Office views"><button type="button" className={view === 'office' ? 'is-active' : ''} onClick={() => setView('office')}><Grid2X2 size={18} /><span>{copy.office}</span></button><button type="button" className={view === 'list' ? 'is-active' : ''} onClick={() => setView('list')}><Users size={18} /><span>{copy.list}</span></button><button type="button" className={view === 'command' ? 'is-active' : ''} onClick={() => setView('command')}><Command size={18} /><span>{copy.projects}</span></button></nav>
    </div>
  );
}
