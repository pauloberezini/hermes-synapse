import { useState } from 'react';
import { Clock, Trash2, Info, Edit3, Play, Pause, RotateCcw, X, Check, MessageSquare, Bell, BellOff } from 'lucide-react';
import { styles } from '../styles';
import { formatTimeLeft } from '../utils';
import { AgentSelect } from './AgentSelect';

export interface TimerItem {
  id: string;
  label: string;
  duration?: number;
  time_left: number;
  status: string;
  created_at: string;
  type?: string;
  target_time?: string;
  interval_hours?: number;
  cron_expr?: string;
  fire_count?: number;
  agent_id?: string;
  prompt?: string;
}

interface ScheduleTabProps {
  timers: TimerItem[];
  subagents: { 
    id: string; 
    name: string; 
    agent_type?: string;
  }[];
  handleCancelTimer: (id: string) => void;
  fetchWithAuth?: (url: string, options?: RequestInit) => Promise<Response>;
  onOpenChat?: (sessionId: string) => void;
  onTaskUpdated?: () => void;
  timerSoundEnabled?: boolean;
  setTimerSoundEnabled?: (val: boolean | ((prev: boolean) => boolean)) => void;
}


function formatCreatedDate(dateStr?: string) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const datePart = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const timePart = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return `${datePart}, ${timePart}`;
  } catch {
    return dateStr;
  }
}

export function ScheduleTab({
  timers,
  subagents,
  handleCancelTimer,
  fetchWithAuth,
  onOpenChat,
  onTaskUpdated,
  timerSoundEnabled = false,
  setTimerSoundEnabled,
}: ScheduleTabProps) {

  // Create Form State
  const [taskType, setTaskType] = useState<'one-shot' | 'alarm' | 'recurring' | 'cron'>('one-shot');
  const [taskLabel, setTaskLabel] = useState('');
  const [targetAgent, setTargetAgent] = useState('jarvis');
  const [taskPrompt, setTaskPrompt] = useState('');
  const [taskDuration, setTaskDuration] = useState(60);
  const [taskTimeStr, setTaskTimeStr] = useState('');
  const [taskInterval, setTaskInterval] = useState(1);
  const [taskCronExpr, setTaskCronExpr] = useState('*/15 * * * *');

  // Info Modal State
  const [infoTimer, setInfoTimer] = useState<TimerItem | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  // Edit Modal State
  const [editTimer, setEditTimer] = useState<TimerItem | null>(null);
  const [editType, setEditType] = useState<'one-shot' | 'alarm' | 'recurring' | 'cron'>('one-shot');
  const [editLabel, setEditLabel] = useState('');
  const [editTargetAgent, setEditTargetAgent] = useState('jarvis');
  const [editPrompt, setEditPrompt] = useState('');
  const [editDuration, setEditDuration] = useState(60);
  const [editTimeStr, setEditTimeStr] = useState('');
  const [editInterval, setEditInterval] = useState(1);
  const [editCronExpr, setEditCronExpr] = useState('*/15 * * * *');
  const [editSaving, setEditSaving] = useState(false);

  const safeSubagents = Array.isArray(subagents) ? subagents : [];
  const safeTimers = Array.isArray(timers) ? timers : [];

  const doFetch = fetchWithAuth || ((url: string, opts?: RequestInit) => fetch(url, opts));

  const handleScheduleTask = () => {
    if (!taskLabel || !taskPrompt) {
      alert("Label and Prompt are required!");
      return;
    }
    const payload: any = {
      type: taskType,
      label: taskLabel,
      agent_id: targetAgent,
      prompt: taskPrompt,
    };
    if (taskType === 'one-shot') {
      payload.duration_seconds = taskDuration;
    } else if (taskType === 'alarm') {
      payload.time_str = taskTimeStr;
    } else if (taskType === 'recurring') {
      payload.interval_hours = taskInterval;
    } else if (taskType === 'cron') {
      if (!taskCronExpr.trim()) {
        alert("Cron expression is required!");
        return;
      }
      payload.cron_expr = taskCronExpr.trim();
    }

    doFetch('http://localhost:8000/api/timers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setTaskLabel('');
          setTaskPrompt('');
          onTaskUpdated?.();
          if (onOpenChat && data.id) {
            onOpenChat(`task_${data.id}`);
          }
        } else {
          alert("Error: " + (data.error || "Failed to schedule task"));
        }
      })
      .catch(err => console.error('Error scheduling task:', err));
  };

  const handleOpenEdit = (timer: TimerItem) => {
    setEditTimer(timer);
    setEditType((timer.type as any) || 'one-shot');
    setEditLabel(timer.label || '');
    setEditTargetAgent(timer.agent_id || 'jarvis');
    setEditPrompt(timer.prompt || '');
    setEditDuration(timer.duration || 60);
    setEditTimeStr(timer.target_time || '');
    setEditInterval(timer.interval_hours || 1);
    setEditCronExpr(timer.cron_expr || '*/15 * * * *');
  };

  const handleSaveEdit = () => {
    if (!editTimer) return;
    if (!editLabel || !editPrompt) {
      alert("Label and Prompt are required!");
      return;
    }

    setEditSaving(true);
    const payload: any = {
      type: editType,
      label: editLabel,
      agent_id: editTargetAgent,
      prompt: editPrompt,
    };
    if (editType === 'one-shot') {
      payload.duration_seconds = editDuration;
    } else if (editType === 'alarm') {
      payload.time_str = editTimeStr;
    } else if (editType === 'recurring') {
      payload.interval_hours = editInterval;
    } else if (editType === 'cron') {
      if (!editCronExpr.trim()) {
        alert("Cron expression is required!");
        setEditSaving(false);
        return;
      }
      payload.cron_expr = editCronExpr.trim();
    }

    doFetch(`http://localhost:8000/api/timers/${editTimer.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(data => {
        setEditSaving(false);
        if (data.status === 'success') {
          setEditTimer(null);
          onTaskUpdated?.();
        } else {
          alert("Error updating task: " + (data.error || "Failed to save changes"));
        }
      })
      .catch(err => {
        setEditSaving(false);
        console.error('Error saving task edit:', err);
        alert("Error saving task edit");
      });
  };

  const handleRunNow = (timerId: string) => {
    setRunMessage(null);
    doFetch(`http://localhost:8000/api/timers/${timerId}/run`, {
      method: 'POST'
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'triggered') {
          setRunMessage("⚡ Task triggered successfully! Agent is executing instructions...");
          setTimeout(() => setRunMessage(null), 4000);
          onTaskUpdated?.();
          if (onOpenChat) {
            onOpenChat(`task_${timerId}`);
          }
        } else {
          alert("Error running task: " + (data.error || "Failed to trigger task"));
        }
      })
      .catch(err => {
        console.error("Error triggering task:", err);
        alert("Failed to trigger task execution");
      });
  };

  const handleTogglePause = (timer: TimerItem) => {
    const isPaused = timer.status === 'paused';
    const endpoint = isPaused ? 'resume' : 'pause';
    doFetch(`http://localhost:8000/api/timers/${timer.id}/${endpoint}`, {
      method: 'POST'
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'paused' || data.status === 'resumed') {
          onTaskUpdated?.();
        } else {
          alert("Error: " + (data.error || "Failed to toggle pause/resume"));
        }
      })
      .catch(err => {
        console.error("Error toggling pause/resume:", err);
        alert("Failed to update timer pause state");
      });
  };

  const handleRestart = (timerId: string) => {
    doFetch(`http://localhost:8000/api/timers/${timerId}/restart`, {
      method: 'POST'
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'restarted') {
          onTaskUpdated?.();
        } else {
          alert("Error: " + (data.error || "Failed to restart task"));
        }
      })
      .catch(err => {
        console.error("Error restarting task:", err);
        alert("Failed to restart task");
      });
  };

  return (
    <div style={styles.tabWrapper}>
      <div style={{ ...styles.tabHeader, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>SCHEDULES & AUTOMATION</h2>
          <p style={styles.tabSubtitle}>Automate tasks, background processes, and agent actions on a schedule</p>
        </div>
        <button
          onClick={() => setTimerSoundEnabled && setTimerSoundEnabled(v => !v)}
          className="btn-primary"
          title={timerSoundEnabled ? 'Turn off timer alarm sound' : 'Turn on timer alarm sound (off by default)'}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            fontSize: '0.8rem',
            border: timerSoundEnabled
              ? '1px solid rgba(0, 240, 255, 0.4)'
              : '1px solid rgba(255,255,255,0.15)',
            color: timerSoundEnabled ? 'var(--accent-cyan)' : 'var(--text-dim)',
            boxShadow: timerSoundEnabled ? '0 0 8px rgba(0,240,255,0.2)' : 'none',
            transition: 'all 0.2s',
          }}
        >
          {timerSoundEnabled ? <Bell size={16} /> : <BellOff size={16} />}
          <span>{timerSoundEnabled ? 'Alarm Sound: ON' : 'Alarm Sound: OFF'}</span>
        </button>
      </div>


      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '24px', flex: 1, minHeight: 0 }}>
        {/* Left Column: Create Form */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px', height: 'fit-content' }}>
          <h3 style={{ ...styles.toolsPanelTitle, borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px', marginBottom: '4px' }}>
            <Clock size={18} style={{ color: 'var(--accent-cyan)' }} />
            <span>Create Scheduled Task</span>
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TASK TYPE</label>
                <select 
                  value={taskType}
                  onChange={(e) => setTaskType(e.target.value as any)}
                  className="form-input"
                  style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
                >
                  <option value="one-shot">One-Shot (Timer)</option>
                  <option value="alarm">Alarm (Specific Time)</option>
                  <option value="recurring">Recurring (Interval)</option>
                  <option value="cron">Cron (n8n Expression)</option>
                </select>
              </div>

              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TARGET AGENT</label>
                <AgentSelect
                  value={targetAgent}
                  onChange={(agentId) => setTargetAgent(agentId)}
                  agents={[
                    { id: 'jarvis', name: 'Jarvis (Main)', agent_type: 'orchestrator' },
                    ...safeSubagents
                  ]}
                  variant="full"
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <div style={{ flex: 2 }}>
                <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TASK LABEL</label>
                <input 
                  type="text" 
                  placeholder="e.g. Check crypto, Morning report" 
                  value={taskLabel}
                  onChange={(e) => setTaskLabel(e.target.value)}
                  className="form-input"
                  style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
                />
              </div>

              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>
                  {taskType === 'one-shot' ? 'DELAY (SECS)' : (taskType === 'alarm' ? 'TIME (HH:MM)' : (taskType === 'recurring' ? 'INTERVAL (HRS)' : 'CRON (* * * * *)'))}
                </label>
                {taskType === 'one-shot' && (
                  <input 
                    type="number" 
                    value={taskDuration}
                    onChange={(e) => setTaskDuration(parseInt(e.target.value) || 0)}
                    className="form-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
                  />
                )}
                {taskType === 'alarm' && (
                  <input 
                    type="text" 
                    placeholder="e.g. 15:30 or 2026-07-08 18:00" 
                    value={taskTimeStr}
                    onChange={(e) => setTaskTimeStr(e.target.value)}
                    className="form-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
                  />
                )}
                {taskType === 'recurring' && (
                  <input 
                    type="number" 
                    step="0.1"
                    value={taskInterval}
                    onChange={(e) => setTaskInterval(parseFloat(e.target.value) || 0)}
                    className="form-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
                  />
                )}
                {taskType === 'cron' && (
                  <div>
                    <input 
                      type="text" 
                      placeholder="e.g. */15 * * * * or 0 9 * * 1-5" 
                      value={taskCronExpr}
                      onChange={(e) => setTaskCronExpr(e.target.value)}
                      className="form-input"
                      style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(168, 85, 247, 0.3)', color: '#fff', fontFamily: 'var(--font-mono)' }}
                    />
                    <div style={{ display: 'flex', gap: '4px', marginTop: '6px', flexWrap: 'wrap' }}>
                      {[
                        { label: '1m', expr: '* * * * *' },
                        { label: '15m', expr: '*/15 * * * *' },
                        { label: '1h', expr: '0 * * * *' },
                        { label: 'Daily 9:00', expr: '0 9 * * *' },
                        { label: 'Mon-Fri 9:00', expr: '0 9 * * 1-5' }
                      ].map((preset) => (
                        <button
                          key={preset.expr}
                          type="button"
                          onClick={() => setTaskCronExpr(preset.expr)}
                          style={{
                            fontSize: '0.65rem',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: taskCronExpr === preset.expr ? 'rgba(168, 85, 247, 0.25)' : 'rgba(255, 255, 255, 0.06)',
                            border: `1px solid ${taskCronExpr === preset.expr ? 'rgba(168, 85, 247, 0.5)' : 'rgba(255, 255, 255, 0.1)'}`,
                            color: taskCronExpr === preset.expr ? '#e9d5ff' : 'var(--text-muted)',
                            cursor: 'pointer',
                            fontFamily: 'var(--font-mono)'
                          }}
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>PREPROMPT / INSTRUCTIONS</label>
              <textarea 
                placeholder="Tell the agent what to do when this task runs..." 
                value={taskPrompt}
                onChange={(e) => setTaskPrompt(e.target.value)}
                className="form-input"
                style={{ width: '100%', padding: '8px 10px', fontSize: '0.8rem', height: '80px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff', resize: 'vertical' }}
              />
            </div>

            <button 
              onClick={handleScheduleTask}
              className="btn-primary"
              style={{
                width: '100%',
                padding: '10px',
                fontSize: '0.85rem',
                fontWeight: 600,
                height: '42px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.25) 0%, rgba(0, 240, 255, 0.08) 100%)',
                border: '1px solid rgba(0, 240, 255, 0.5)',
                boxShadow: '0 0 12px rgba(0, 240, 255, 0.2)',
                color: '#fff',
                cursor: 'pointer',
                borderRadius: '8px',
                transition: 'all 0.2s'
              }}
            >
              <Clock size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span>SCHEDULE TASK</span>
            </button>
          </div>
        </div>

        {/* Right Column: List of Tasks */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px', flex: 1, minHeight: 0, maxHeight: 'calc(100vh - 180px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px' }}>
            <h3 style={{ ...styles.toolsPanelTitle, margin: 0 }}>
              <Clock size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Active Schedules & Tasks ({safeTimers.length})</span>
            </h3>
          </div>
          
          <div style={styles.timersList}>
            {safeTimers.length === 0 ? (
              <div style={styles.emptyTimersMsg}>
                No active timers or scheduled tasks found, Sir.
              </div>
            ) : (
              safeTimers.map((timer) => {
                const isPaused = timer.status === 'paused';
                const isRunning = timer.status === 'running';

                let statusText = 'COMPLETED';
                let statusClass = 'completed';
                let badgeColor = 'var(--success)';
                let badgeBorder = 'rgba(16, 185, 129, 0.35)';
                let badgeBg = 'rgba(16, 185, 129, 0.1)';

                if (isPaused) {
                  statusText = 'PAUSED';
                  statusClass = 'paused';
                  badgeColor = '#eab308';
                  badgeBorder = 'rgba(234, 179, 8, 0.35)';
                  badgeBg = 'rgba(234, 179, 8, 0.1)';
                } else if (isRunning) {
                  if (timer.type === 'alarm') {
                    statusText = 'WAITING';
                    statusClass = 'waiting';
                    badgeColor = '#f97316';
                    badgeBorder = 'rgba(249, 115, 22, 0.35)';
                    badgeBg = 'rgba(249, 115, 22, 0.1)';
                  } else if (timer.type === 'recurring') {
                    statusText = 'RUNNING';
                    statusClass = 'running';
                    badgeColor = '#10b981';
                    badgeBorder = 'rgba(16, 185, 129, 0.35)';
                    badgeBg = 'rgba(16, 185, 129, 0.1)';
                  } else {
                    statusText = 'COUNTDOWN';
                    statusClass = 'countdown';
                    badgeColor = 'var(--accent-cyan)';
                    badgeBorder = 'rgba(0, 240, 255, 0.35)';
                    badgeBg = 'rgba(0, 240, 255, 0.1)';
                  }
                }

                const cardBorderColor = isPaused
                  ? 'rgba(234, 179, 8, 0.3)'
                  : (isRunning 
                      ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.25)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(0, 240, 255, 0.25)')) 
                      : 'rgba(255, 255, 255, 0.08)');

                const cardBgColor = isPaused
                  ? 'rgba(234, 179, 8, 0.03)'
                  : (isRunning 
                      ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.02)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.02)' : 'rgba(0, 240, 255, 0.02)')) 
                      : 'rgba(255, 255, 255, 0.01)');

                return (
                  <div 
                    key={timer.id} 
                    className="schedule-card"
                    style={{
                      ...styles.timerCard,
                      borderColor: cardBorderColor,
                      backgroundColor: cardBgColor,
                    }}
                  >
                    {/* Compact Row 1: Title & Type (Left), Countdown & Status & Actions (Right) */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                      {/* Left: Title & Type Pill */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1, overflow: 'hidden' }}>
                        <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={timer.label}>
                          {timer.label}
                        </span>

                        <span style={{ 
                          fontSize: '0.58rem', 
                          fontFamily: 'var(--font-mono)', 
                          fontWeight: 700, 
                          padding: '2px 5px', 
                          borderRadius: '4px', 
                          backgroundColor: timer.type === 'cron' ? 'rgba(168, 85, 247, 0.15)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.12)' : (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.12)' : 'rgba(0, 240, 255, 0.12)')),
                          color: timer.type === 'cron' ? '#c084fc' : (timer.type === 'recurring' ? '#10b981' : (timer.type === 'alarm' ? '#f97316' : 'var(--accent-cyan)')),
                          border: `1px solid ${timer.type === 'cron' ? 'rgba(168, 85, 247, 0.35)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.25)' : (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.25)' : 'rgba(0, 240, 255, 0.25)'))}`,
                          textTransform: 'uppercase',
                          flexShrink: 0
                        }}>
                          {timer.type === 'cron' ? 'CRON' : (timer.type === 'recurring' ? 'RECURRING' : (timer.type === 'alarm' ? 'ALARM' : 'ONE-SHOT'))}
                        </span>
                      </div>

                      {/* Right: Countdown, Status Badge, Toolbar */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                          <span style={{ fontSize: '1.1rem', fontWeight: 700, color: isPaused ? '#eab308' : 'var(--accent-cyan)', fontFamily: 'var(--font-mono)', textShadow: '0 0 8px rgba(0, 240, 255, 0.3)' }}>
                            {timer.status === 'paused' || timer.status === 'running' ? formatTimeLeft(timer.time_left) : '00:00'}
                          </span>
                          <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>
                            {timer.status === 'paused' ? 'paused' : (timer.type === 'recurring' ? 'next' : 'left')}
                          </span>
                        </div>

                        <span style={{
                          ...styles.timerStatusBadge,
                          color: badgeColor,
                          borderColor: badgeBorder,
                          backgroundColor: badgeBg,
                        }}>
                          <span className={`status-dot-pulse ${statusClass}`} />
                          {statusText}
                        </span>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '2px', background: 'rgba(0, 0, 0, 0.3)', padding: '2px 4px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                          {onOpenChat && (
                            <button onClick={() => onOpenChat(`task_${timer.id}`)} className="icon-btn-action" title="Open Chat Session" style={{ padding: '2px 4px', cursor: 'pointer' }}>
                              <MessageSquare size={13} color="var(--accent-cyan)" />
                            </button>
                          )}
                          <button onClick={() => handleTogglePause(timer)} className="icon-btn-action" title={timer.status === 'paused' ? 'Resume Task' : 'Pause Task'} style={{ padding: '2px 4px', cursor: 'pointer' }}>
                            {timer.status === 'paused' ? <Play size={13} color="#eab308" /> : <Pause size={13} color="#60a5fa" />}
                          </button>
                          <button onClick={() => handleRestart(timer.id)} className="icon-btn-action" title="Restart Task" style={{ padding: '2px 4px', cursor: 'pointer' }}>
                            <RotateCcw size={13} color="#34d399" />
                          </button>
                          <button onClick={() => setInfoTimer(timer)} className="icon-btn-action" title="View Info & Prompt" style={{ padding: '2px 4px', cursor: 'pointer' }}>
                            <Info size={13} color="var(--accent-cyan)" />
                          </button>
                          <button onClick={() => handleOpenEdit(timer)} className="icon-btn-action" title="Edit Task" style={{ padding: '2px 4px', cursor: 'pointer' }}>
                            <Edit3 size={13} color="#eab308" />
                          </button>
                          <button onClick={() => handleCancelTimer(timer.id)} className="icon-btn-action danger" title="Delete Task" style={{ padding: '2px 4px', cursor: 'pointer' }}>
                            <Trash2 size={13} color="#ef4444" />
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Compact Row 2: ID, Agent, Prompt, Stats */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', fontSize: '0.7rem', color: 'var(--text-dim)', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 }}>
                        <span style={{ fontSize: '0.62rem', fontFamily: 'var(--font-mono)', color: 'rgba(255,255,255,0.4)', background: 'rgba(255,255,255,0.04)', padding: '1px 4px', borderRadius: '3px', flexShrink: 0 }}>
                          ID: {timer.id.slice(0, 8)}
                        </span>
                        <span style={{ color: 'var(--accent-cyan)', fontWeight: 500, flexShrink: 0 }}>🤖 {timer.agent_id || 'jarvis'}</span>
                        {timer.prompt && (
                          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={timer.prompt}>
                            "{timer.prompt}"
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0, fontFamily: 'var(--font-mono)', fontSize: '0.66rem' }}>
                        {timer.created_at && (
                          <span style={{ color: 'rgba(255,255,255,0.4)' }}>
                            {formatCreatedDate(timer.created_at)}
                          </span>
                        )}
                        {timer.type === 'cron' ? (
                          <span>Cron: <code style={{ color: '#c084fc' }}>{timer.cron_expr}</code> | Fired: {timer.fire_count || 0}</span>
                        ) : timer.type === 'recurring' ? (
                          <span>Every {timer.interval_hours}h | Fired: {timer.fire_count || 0}</span>
                        ) : timer.type === 'alarm' ? (
                          <span>Target: {timer.target_time}</span>
                        ) : (
                          <span>Duration: {timer.duration}s</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* INFO / PREVIEW MODAL */}
      {infoTimer && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div className="glass-panel" style={{
            width: '100%',
            maxWidth: '560px',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            border: '1px solid rgba(0, 240, 255, 0.3)',
            boxShadow: '0 0 30px rgba(0, 240, 255, 0.15)',
            maxHeight: '90vh',
            overflowY: 'auto'
          }}>
            {/* Modal Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Info size={20} style={{ color: 'var(--accent-cyan)' }} />
                <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#fff', fontWeight: 700 }}>
                  Task Details & Preview
                </h3>
              </div>
              <button 
                onClick={() => { setInfoTimer(null); setRunMessage(null); }}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Notification message */}
            {runMessage && (
              <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.4)', color: '#10b981', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Check size={16} />
                <span>{runMessage}</span>
              </div>
            )}

            {/* Task Info Body */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '2px' }}>TASK NAME / LABEL</label>
                  <div style={{ fontSize: '1rem', fontWeight: 600, color: '#fff' }}>{infoTimer.label}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '2px' }}>TASK ID (DB)</label>
                  <code style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', background: 'rgba(0,240,255,0.06)', padding: '3px 8px', borderRadius: '4px', border: '1px solid rgba(0,240,255,0.15)', userSelect: 'all' }}>
                    {infoTimer.id}
                  </code>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <div style={{ flex: 1, padding: '8px 12px', borderRadius: '6px', backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block' }}>TARGET AGENT</span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>🤖 {infoTimer.agent_id || 'jarvis'}</span>
                </div>
                <div style={{ flex: 1, padding: '8px 12px', borderRadius: '6px', backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block' }}>TYPE</span>
                  <span style={{ fontSize: '0.85rem', color: '#fff', fontWeight: 600, textTransform: 'capitalize' }}>{infoTimer.type || 'one-shot'}</span>
                </div>
                <div style={{ flex: 1, padding: '8px 12px', borderRadius: '6px', backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block' }}>SCHEDULE PARAMETER</span>
                  <span style={{ fontSize: '0.85rem', color: '#fff', fontWeight: 600 }}>
                    {infoTimer.type === 'recurring' ? `Every ${infoTimer.interval_hours} hrs` : (infoTimer.type === 'alarm' ? infoTimer.target_time : `${infoTimer.duration || 0}s`)}
                  </span>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>FULL PREPROMPT / INSTRUCTIONS RUN BY AGENT</label>
                <div style={{
                  padding: '12px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(6, 9, 19, 0.9)',
                  border: '1px solid rgba(0, 240, 255, 0.2)',
                  color: '#e2e8f0',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  lineHeight: '1.4',
                  whiteSpace: 'pre-wrap',
                  maxHeight: '180px',
                  overflowY: 'auto'
                }}>
                  {infoTimer.prompt || '(No prompt defined)'}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '16px', fontSize: '0.75rem', color: 'var(--text-muted)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '10px' }}>
                <div>Created: <span style={{ color: '#fff' }}>{infoTimer.created_at || 'N/A'}</span></div>
                {infoTimer.type === 'recurring' && (
                  <div>Total Fired: <span style={{ color: 'var(--accent-cyan)' }}>{infoTimer.fire_count || 0} times</span></div>
                )}
              </div>
            </div>

            {/* Modal Actions */}
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginTop: '8px' }}>
              <button
                onClick={() => handleRunNow(infoTimer.id)}
                className="btn-primary"
                style={{ padding: '8px 16px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: 'rgba(16, 185, 129, 0.2)', borderColor: '#10b981', color: '#10b981' }}
              >
                <Play size={14} />
                <span>Run Now</span>
              </button>

              <button
                onClick={() => { setInfoTimer(null); setRunMessage(null); }}
                style={{ padding: '8px 16px', fontSize: '0.8rem', backgroundColor: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', borderRadius: '6px', cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EDIT TASK MODAL */}
      {editTimer && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div className="glass-panel" style={{
            width: '100%',
            maxWidth: '540px',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            border: '1px solid rgba(234, 179, 8, 0.3)',
            boxShadow: '0 0 30px rgba(234, 179, 8, 0.15)',
            maxHeight: '90vh',
            overflowY: 'auto'
          }}>
            {/* Edit Modal Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Edit3 size={20} style={{ color: '#eab308' }} />
                <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#fff', fontWeight: 700 }}>
                  Edit Scheduled Task
                </h3>
              </div>
              <button 
                onClick={() => setEditTimer(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Edit Form */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', gap: '8px' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TASK TYPE</label>
                  <select 
                    value={editType}
                    onChange={(e) => setEditType(e.target.value as any)}
                    className="form-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff' }}
                  >
                    <option value="one-shot">One-Shot (Timer)</option>
                    <option value="alarm">Alarm (Specific Time)</option>
                    <option value="recurring">Recurring (Interval)</option>
                    <option value="cron">Cron (n8n Expression)</option>
                  </select>
                </div>

                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TARGET AGENT</label>
                  <AgentSelect
                    value={editTargetAgent}
                    onChange={(agentId) => setEditTargetAgent(agentId)}
                    agents={[
                      { id: 'jarvis', name: 'Jarvis (Main)', agent_type: 'orchestrator' },
                      ...safeSubagents
                    ]}
                    variant="full"
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <div style={{ flex: 2 }}>
                  <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TASK LABEL</label>
                  <input 
                    type="text" 
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    className="form-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff' }}
                  />
                </div>

                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>
                    {editType === 'one-shot' ? 'DELAY (SECS)' : (editType === 'alarm' ? 'TIME (HH:MM)' : (editType === 'recurring' ? 'INTERVAL (HRS)' : 'CRON (* * * * *)'))}
                  </label>
                  {editType === 'one-shot' && (
                    <input 
                      type="number" 
                      value={editDuration}
                      onChange={(e) => setEditDuration(parseInt(e.target.value) || 0)}
                      className="form-input"
                      style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff' }}
                    />
                  )}
                  {editType === 'alarm' && (
                    <input 
                      type="text" 
                      value={editTimeStr}
                      onChange={(e) => setEditTimeStr(e.target.value)}
                      className="form-input"
                      style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff' }}
                    />
                  )}
                  {editType === 'recurring' && (
                    <input 
                      type="number" 
                      step="0.1"
                      value={editInterval}
                      onChange={(e) => setEditInterval(parseFloat(e.target.value) || 0)}
                      className="form-input"
                      style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff' }}
                    />
                  )}
                  {editType === 'cron' && (
                    <input 
                      type="text" 
                      placeholder="e.g. */15 * * * *" 
                      value={editCronExpr}
                      onChange={(e) => setEditCronExpr(e.target.value)}
                      className="form-input"
                      style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff', fontFamily: 'var(--font-mono)' }}
                    />
                  )}
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>PREPROMPT / INSTRUCTIONS</label>
                <textarea 
                  value={editPrompt}
                  onChange={(e) => setEditPrompt(e.target.value)}
                  className="form-input"
                  style={{ width: '100%', padding: '8px 10px', fontSize: '0.8rem', height: '100px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff', resize: 'vertical' }}
                />
              </div>
            </div>

            {/* Modal Actions */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
              <button
                onClick={() => setEditTimer(null)}
                style={{ padding: '8px 16px', fontSize: '0.8rem', backgroundColor: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', borderRadius: '6px', cursor: 'pointer' }}
              >
                Cancel
              </button>

              <button
                onClick={handleSaveEdit}
                disabled={editSaving}
                className="btn-primary"
                style={{ padding: '8px 18px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: '#eab308', borderColor: '#eab308', color: '#000', fontWeight: 600 }}
              >
                <Check size={14} />
                <span>{editSaving ? 'Saving...' : 'Save Changes'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
