import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  BrainCircuit,
  Check,
  CircleDot,
  Database,
  FileCheck2,
  ListChecks,
  OctagonX,
  Play,
  RefreshCw,
  ShieldCheck,
  Wrench,
  X,
} from 'lucide-react';
import type { AutonomySummary, ControlPlaneSummary, WorkflowTask } from '../types';

type Props = { language: 'ru' | 'en' };
type Filter = 'all' | 'approval' | 'active' | 'finished';

const COPY = {
  ru: {
    title: 'Процессы и контроль', subtitle: 'Задачи, подтверждения, лимиты и доказательства исполнения',
    running: 'CONTROL PLANE АКТИВЕН', stopped: 'АВАРИЙНАЯ ОСТАНОВКА', stop: 'Остановить всё', resume: 'Возобновить', refresh: 'Обновить',
    approvals: 'Ожидают подтверждения', active: 'В работе', completed: 'Завершено', blocked: 'Остановлено',
    all: 'Все', approval: 'Approval', activeTab: 'Активные', finished: 'Завершённые', queue: 'Очередь задач',
    empty: 'Процессов пока нет. Они появятся при вызове инструментов агентами.', select: 'Выберите задачу для просмотра контракта.',
    approve: 'Подтвердить', reject: 'Отклонить', details: 'Контракт задачи', risk: 'Риск', autonomy: 'Автономность', assignee: 'Исполнитель',
    source: 'Источник', budget: 'Бюджет', commands: 'команд', seconds: 'сек', acceptance: 'Критерии готовности', rollback: 'Откат',
    result: 'Результат', error: 'Ошибка', evidence: 'Evidence Ledger', noEvidence: 'Событий пока нет', confidence: 'Подтверждено',
    confirmation: 'подтверждение', confirmations: 'подтверждения', stoppedReason: 'Причина остановки', failedLoad: 'Не удалось загрузить Control Plane.',
    stopConfirm: 'Немедленно остановить новые действия и активные запуски?', rejectConfirm: 'Отклонить эту задачу?', r4Confirm: 'Это действие класса R4. Подтвердить текущий этап?',
    autonomyTitle: 'Контур автономности', indexed: 'Файлов в памяти', capabilities: 'Инструменты', plans: 'Активные планы',
    proposals: 'На проверке', reindex: 'Обновить память', neverIndexed: 'Индекс ещё не создан', fresh: 'Обновлено',
  },
  en: {
    title: 'Processes & Control', subtitle: 'Tasks, approvals, limits and execution evidence',
    running: 'CONTROL PLANE ACTIVE', stopped: 'EMERGENCY STOP', stop: 'Stop all', resume: 'Resume', refresh: 'Refresh',
    approvals: 'Awaiting approval', active: 'Running', completed: 'Completed', blocked: 'Stopped',
    all: 'All', approval: 'Approval', activeTab: 'Active', finished: 'Finished', queue: 'Task queue',
    empty: 'No processes yet. They appear when agents request tools.', select: 'Select a task to inspect its contract.',
    approve: 'Approve', reject: 'Reject', details: 'Task contract', risk: 'Risk', autonomy: 'Autonomy', assignee: 'Assignee',
    source: 'Origin', budget: 'Budget', commands: 'commands', seconds: 'sec', acceptance: 'Acceptance criteria', rollback: 'Rollback',
    result: 'Result', error: 'Error', evidence: 'Evidence Ledger', noEvidence: 'No events yet', confidence: 'Confirmed',
    confirmation: 'confirmation', confirmations: 'confirmations', stoppedReason: 'Stop reason', failedLoad: 'Could not load Control Plane.',
    stopConfirm: 'Immediately stop new actions and active runs?', rejectConfirm: 'Reject this task?', r4Confirm: 'This is an R4 action. Confirm the current stage?',
    autonomyTitle: 'Autonomy Runtime', indexed: 'Files in memory', capabilities: 'Capabilities', plans: 'Active plans',
    proposals: 'Under review', reindex: 'Refresh memory', neverIndexed: 'Index has not been created', fresh: 'Updated',
  },
} as const;

const ACTIVE = new Set(['queued', 'running', 'approved']);
const FINISHED = new Set(['done', 'failed', 'killed', 'rejected', 'blocked']);

function shortTime(value: string) {
  if (!value) return '—';
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }).format(timestamp);
}

function statusLabel(task: WorkflowTask, language: 'ru' | 'en') {
  const labels: Record<string, [string, string]> = {
    queued: ['В очереди', 'Queued'], running: ['Выполняется', 'Running'], blocked: ['Заблокировано', 'Blocked'],
    awaiting_approval: ['Ждёт approval', 'Awaiting approval'], approved: ['Подтверждено', 'Approved'], done: ['Готово', 'Done'],
    failed: ['Ошибка', 'Failed'], killed: ['Остановлено', 'Killed'], rejected: ['Отклонено', 'Rejected'],
  };
  return labels[task.status]?.[language === 'ru' ? 0 : 1] || task.status;
}

export function ProcessesTab({ language }: Props) {
  const copy = COPY[language];
  const [summary, setSummary] = useState<ControlPlaneSummary | null>(null);
  const [autonomy, setAutonomy] = useState<AutonomySummary | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [response, autonomyResponse] = await Promise.all([
        fetch('/api/control-plane/summary?limit=120'),
        fetch('/api/autonomy/summary'),
      ]);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json() as ControlPlaneSummary;
      setSummary(data);
      if (autonomyResponse.ok) {
        setAutonomy(await autonomyResponse.json() as AutonomySummary);
      }
      setError('');
      setSelectedId(current => current || data.pending_approvals[0]?.id || data.tasks[0]?.id || '');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : copy.failedLoad);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [copy.failedLoad]);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(true), 3000);
    return () => window.clearInterval(interval);
  }, [load]);

  const tasks = useMemo(() => (summary?.tasks || []).filter(task => {
    if (filter === 'approval') return task.status === 'awaiting_approval';
    if (filter === 'active') return ACTIVE.has(task.status);
    if (filter === 'finished') return FINISHED.has(task.status);
    return true;
  }), [filter, summary]);
  const selected = summary?.tasks.find(task => task.id === selectedId) || null;
  const selectedEvents = summary?.events.filter(event => !selected || event.task_id === selected.id) || [];

  const post = async (path: string, reason = '') => {
    setBusy(path);
    try {
      const response = await fetch(path, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `HTTP ${response.status}`);
      }
      await load(true);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy('');
    }
  };

  const approve = (task: WorkflowTask) => {
    if (task.risk_class === 'R4' && !window.confirm(copy.r4Confirm)) return;
    void post(`/api/control-plane/tasks/${encodeURIComponent(task.id)}/approve`);
  };
  const reject = (task: WorkflowTask) => {
    if (!window.confirm(copy.rejectConfirm)) return;
    void post(`/api/control-plane/tasks/${encodeURIComponent(task.id)}/reject`, 'Rejected by owner');
  };
  const kill = () => {
    if (!window.confirm(copy.stopConfirm)) return;
    void post('/api/control-plane/kill', 'Emergency stop from web console');
  };
  const reindex = async () => {
    setBusy('autonomy-index');
    try {
      const response = await fetch('/api/autonomy/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await load(true);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy('');
    }
  };

  if (loading && !summary) return <div className="control-loading"><RefreshCw className="spin-slow" size={20} />Control Plane</div>;

  const stopped = Boolean(summary?.state.kill_switch);
  return (
    <div className="control-page">
      <header className="control-header">
        <div><span className="control-eyebrow"><ShieldCheck size={14} />CONTROL PLANE</span><h2>{copy.title}</h2><p>{copy.subtitle}</p></div>
        <div className="control-actions">
          <span className={`control-state ${stopped ? 'is-stopped' : 'is-running'}`}><CircleDot size={14} />{stopped ? copy.stopped : copy.running}</span>
          <button type="button" className="icon-btn" onClick={() => void load()} title={copy.refresh} aria-label={copy.refresh}><RefreshCw size={16} /></button>
          {stopped
            ? <button type="button" className="control-command is-resume" disabled={Boolean(busy)} onClick={() => void post('/api/control-plane/resume', 'Resumed from web console')}><Play size={15} />{copy.resume}</button>
            : <button type="button" className="control-command is-stop" disabled={Boolean(busy)} onClick={kill}><OctagonX size={15} />{copy.stop}</button>}
        </div>
      </header>

      {error && <div className="control-alert"><AlertTriangle size={15} />{copy.failedLoad} {error}</div>}
      {stopped && <div className="control-stop-reason"><Ban size={15} /><strong>{copy.stoppedReason}:</strong> {summary?.state.reason || '—'}</div>}

      <section className="control-metrics" aria-label="Control Plane metrics">
        <div><span>{copy.approvals}</span><strong>{summary?.counts.awaiting_approval || 0}</strong></div>
        <div><span>{copy.active}</span><strong>{(summary?.counts.running || 0) + (summary?.counts.queued || 0)}</strong></div>
        <div><span>{copy.completed}</span><strong>{summary?.counts.done || 0}</strong></div>
        <div><span>{copy.blocked}</span><strong>{(summary?.counts.blocked || 0) + (summary?.counts.failed || 0) + (summary?.counts.killed || 0)}</strong></div>
      </section>

      <section className="control-autonomy" aria-labelledby="autonomy-runtime-title">
        <div className="control-autonomy-head">
          <div><BrainCircuit size={18} /><h3 id="autonomy-runtime-title">{copy.autonomyTitle}</h3></div>
          <button type="button" onClick={() => void reindex()} disabled={Boolean(busy)} title={copy.reindex}>
            <RefreshCw size={14} className={busy === 'autonomy-index' ? 'spin-slow' : ''} />{copy.reindex}
          </button>
        </div>
        <div className="control-autonomy-grid">
          <div><Database size={16} /><span>{copy.indexed}</span><strong>{autonomy?.memory.files ?? 0}</strong><small>{autonomy?.memory.fresh_at ? `${copy.fresh}: ${shortTime(autonomy.memory.fresh_at)}` : copy.neverIndexed}</small></div>
          <div><Wrench size={16} /><span>{copy.capabilities}</span><strong>{autonomy ? `${autonomy.capabilities.ready}/${autonomy.capabilities.total}` : '—'}</strong><small>{autonomy?.capabilities.status || '—'}</small></div>
          <div><ListChecks size={16} /><span>{copy.plans}</span><strong>{autonomy?.plans.filter(plan => plan.status === 'running').length ?? 0}</strong><small>{autonomy?.plans[0]?.goal || '—'}</small></div>
          <div><ShieldCheck size={16} /><span>{copy.proposals}</span><strong>{autonomy?.proposals.filter(item => item.status === 'awaiting_approval').length ?? 0}</strong><small>{autonomy?.proposals[0]?.capability_id || '—'}</small></div>
        </div>
      </section>

      <div className="control-workspace">
        <section className="control-queue" aria-labelledby="control-queue-title">
          <div className="control-section-head"><div><ListChecks size={17} /><h3 id="control-queue-title">{copy.queue}</h3></div><span>{tasks.length}</span></div>
          <div className="control-filters" role="tablist">
            {([['all', copy.all], ['approval', copy.approval], ['active', copy.activeTab], ['finished', copy.finished]] as [Filter, string][]).map(([value, label]) => (
              <button key={value} type="button" role="tab" aria-selected={filter === value} onClick={() => setFilter(value)}>{label}</button>
            ))}
          </div>
          <div className="control-task-list">
            {!tasks.length && <p className="control-empty">{copy.empty}</p>}
            {tasks.map(task => (
              <button key={task.id} type="button" className={`control-task-row${selectedId === task.id ? ' is-selected' : ''}`} onClick={() => setSelectedId(task.id)}>
                <span className={`risk-badge is-${task.risk_class.toLowerCase()}`}>{task.risk_class}</span>
                <span className="control-task-main"><strong>{task.tool_name || task.goal}</strong><small>{task.id} · {task.assignee}</small></span>
                <span className={`task-status is-${task.status}`}>{statusLabel(task, language)}</span>
                <time>{shortTime(task.created_at)}</time>
              </button>
            ))}
          </div>
        </section>

        <aside className="control-inspector" aria-label={copy.details}>
          {!selected && <p className="control-empty">{copy.select}</p>}
          {selected && <>
            <div className="control-inspector-head"><div><span>{copy.details}</span><h3>{selected.tool_name || selected.goal}</h3><code>{selected.id}</code></div><span className={`risk-badge is-${selected.risk_class.toLowerCase()}`}>{selected.risk_class}</span></div>
            {selected.status === 'awaiting_approval' && <div className="approval-bar">
              <div><strong>{selected.approval_count}/{selected.approvals_required}</strong><span>{selected.approvals_required === 1 ? copy.confirmation : copy.confirmations}</span></div>
              <button type="button" className="approve-btn" disabled={Boolean(busy)} onClick={() => approve(selected)} title={copy.approve}><Check size={16} />{copy.approve}</button>
              <button type="button" className="reject-btn" disabled={Boolean(busy)} onClick={() => reject(selected)} title={copy.reject}><X size={16} /></button>
            </div>}
            <dl className="control-contract">
              <div><dt>{copy.risk}</dt><dd>{selected.risk_class}</dd></div><div><dt>{copy.autonomy}</dt><dd>{selected.autonomy_level}</dd></div>
              <div><dt>{copy.assignee}</dt><dd>{selected.assignee}</dd></div><div><dt>{copy.source}</dt><dd>{selected.origin}</dd></div>
              <div className="is-wide"><dt>{copy.budget}</dt><dd>{selected.commands_used}/{selected.budget_commands} {copy.commands} · {selected.budget_wallclock_s} {copy.seconds}</dd></div>
            </dl>
            <section className="contract-block"><h4>{copy.acceptance}</h4><ul>{selected.acceptance.map(item => <li key={item}>{item}</li>)}</ul></section>
            <section className="contract-block"><h4>{copy.rollback}</h4><p>{selected.rollback || '—'}</p></section>
            {selected.result && <section className="contract-block is-result"><h4>{copy.result}</h4><pre>{selected.result}</pre></section>}
            {selected.error && <section className="contract-block is-error"><h4>{copy.error}</h4><p>{selected.error}</p></section>}
          </>}
        </aside>
      </div>

      <section className="evidence-ledger" aria-labelledby="evidence-title">
        <div className="control-section-head"><div><FileCheck2 size={17} /><h3 id="evidence-title">{copy.evidence}</h3></div><span>{selectedEvents.length}</span></div>
        {!selectedEvents.length && <p className="control-empty">{copy.noEvidence}</p>}
        <div className="evidence-list">{selectedEvents.slice(0, 12).map(event => <div key={event.id}>
          <code>{event.evidence_id}</code><span className={`risk-badge is-${event.risk_class.toLowerCase()}`}>{event.risk_class}</span>
          <p><strong>{event.event_type}</strong>{event.message}</p><small>{event.actor} · {shortTime(event.created_at)} · {copy.confidence}</small>
          {event.output_hash && <code title={event.output_hash}>{event.output_hash.slice(0, 12)}…</code>}
        </div>)}</div>
      </section>
    </div>
  );
}
