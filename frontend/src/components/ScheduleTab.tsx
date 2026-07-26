import { useState } from 'react';
import { Clock, Trash2, Info, Edit3, Play, Pause, RotateCcw, X, Check } from 'lucide-react';
import { styles } from '../styles';
import { formatTimeLeft } from '../utils';

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
}

export function ScheduleTab({
  timers,
  subagents,
  handleCancelTimer,
  fetchWithAuth,
}: ScheduleTabProps) {
  // Create Form State
  const [taskType, setTaskType] = useState<'one-shot' | 'alarm' | 'recurring'>('one-shot');
  const [taskLabel, setTaskLabel] = useState('');
  const [targetAgent, setTargetAgent] = useState('jarvis');
  const [taskPrompt, setTaskPrompt] = useState('');
  const [taskDuration, setTaskDuration] = useState(60);
  const [taskTimeStr, setTaskTimeStr] = useState('');
  const [taskInterval, setTaskInterval] = useState(1);

  // Info Modal State
  const [infoTimer, setInfoTimer] = useState<TimerItem | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  // Edit Modal State
  const [editTimer, setEditTimer] = useState<TimerItem | null>(null);
  const [editType, setEditType] = useState<'one-shot' | 'alarm' | 'recurring'>('one-shot');
  const [editLabel, setEditLabel] = useState('');
  const [editTargetAgent, setEditTargetAgent] = useState('jarvis');
  const [editPrompt, setEditPrompt] = useState('');
  const [editDuration, setEditDuration] = useState(60);
  const [editTimeStr, setEditTimeStr] = useState('');
  const [editInterval, setEditInterval] = useState(1);
  const [editSaving, setEditSaving] = useState(false);

  const safeSubagents = Array.isArray(subagents) ? subagents : [];
  const safeTimers = Array.isArray(timers) ? timers : [];

  const availableAgents = [
    { id: 'jarvis', name: 'Jarvis (Main Orchestrator)' },
    ...safeSubagents.map(a => ({ id: a.id, name: a.name }))
  ];

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
        if (data.status !== 'paused' && data.status !== 'resumed') {
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
        if (data.status !== 'restarted') {
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
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>SCHEDULES & AUTOMATION</h2>
          <p style={styles.tabSubtitle}>Automate tasks, background processes, and agent actions on a schedule</p>
        </div>
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
                </select>
              </div>

              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TARGET AGENT</label>
                <select 
                  value={targetAgent}
                  onChange={(e) => setTargetAgent(e.target.value)}
                  className="form-input"
                  style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
                >
                  {availableAgents.map(agent => (
                    <option key={agent.id} value={agent.id}>{agent.name}</option>
                  ))}
                </select>
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
                  {taskType === 'one-shot' ? 'DELAY (SECS)' : (taskType === 'alarm' ? 'TIME (HH:MM)' : 'INTERVAL (HRS)')}
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
              style={{ width: '100%', padding: '10px', fontSize: '0.8rem', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
            >
              Schedule Task
            </button>
          </div>
        </div>

        {/* Right Column: List of Tasks */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px', height: 'fit-content' }}>
          <h3 style={{ ...styles.toolsPanelTitle, borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px', marginBottom: '4px' }}>
            <Clock size={18} style={{ color: 'var(--accent-cyan)' }} />
            <span>Active Schedules & Tasks</span>
          </h3>
          
          <div style={styles.timersList}>
            {safeTimers.length === 0 ? (
              <div style={styles.emptyTimersMsg}>
                No active timers or scheduled tasks found, Sir.
              </div>
            ) : (
              safeTimers.map((timer) => (
                <div 
                  key={timer.id} 
                  style={{
                    ...styles.timerCard,
                    borderColor: timer.status === 'paused'
                      ? 'rgba(234, 179, 8, 0.3)'
                      : (timer.status === 'running' 
                          ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.2)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(0, 240, 255, 0.2)')) 
                          : 'rgba(255, 255, 255, 0.05)'),
                    backgroundColor: timer.status === 'paused'
                      ? 'rgba(234, 179, 8, 0.03)'
                      : (timer.status === 'running' 
                          ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.02)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.02)' : 'rgba(0, 240, 255, 0.02)')) 
                          : 'rgba(255, 255, 255, 0.01)'),
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px'
                  }}
                >
                  <div style={styles.timerHeader}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={styles.timerLabel}>{timer.label}</span>
                      
                      {/* Action buttons: Pause/Resume, Restart, Info, Edit, Delete */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '2px', marginLeft: '6px' }}>
                        {/* Pause / Resume Button */}
                        <button 
                          onClick={() => handleTogglePause(timer)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: timer.status === 'paused' ? '#eab308' : 'rgba(59, 130, 246, 0.85)',
                            cursor: 'pointer',
                            padding: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderRadius: '4px',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = timer.status === 'paused' ? '#facc15' : '#60a5fa';
                            e.currentTarget.style.backgroundColor = timer.status === 'paused' ? 'rgba(234, 179, 8, 0.15)' : 'rgba(59, 130, 246, 0.15)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = timer.status === 'paused' ? '#eab308' : 'rgba(59, 130, 246, 0.85)';
                            e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                          title={timer.status === 'paused' ? 'Resume Schedule' : 'Pause Schedule'}
                        >
                          {timer.status === 'paused' ? <Play size={14} /> : <Pause size={14} />}
                        </button>

                        {/* Restart Button */}
                        <button 
                          onClick={() => handleRestart(timer.id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'rgba(16, 185, 129, 0.85)',
                            cursor: 'pointer',
                            padding: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderRadius: '4px',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = '#34d399';
                            e.currentTarget.style.backgroundColor = 'rgba(16, 185, 129, 0.15)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'rgba(16, 185, 129, 0.85)';
                            e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                          title="Restart Schedule (Reset Timer)"
                        >
                          <RotateCcw size={14} />
                        </button>

                        {/* Info Button */}
                        <button 
                          onClick={() => setInfoTimer(timer)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'rgba(0, 240, 255, 0.7)',
                            cursor: 'pointer',
                            padding: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderRadius: '4px',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = 'var(--accent-cyan)';
                            e.currentTarget.style.backgroundColor = 'rgba(0, 240, 255, 0.1)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'rgba(0, 240, 255, 0.7)';
                            e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                          title="View Info & Preview Prompt"
                        >
                          <Info size={14} />
                        </button>

                        {/* Edit Button */}
                        <button 
                          onClick={() => handleOpenEdit(timer)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'rgba(234, 179, 8, 0.7)',
                            cursor: 'pointer',
                            padding: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderRadius: '4px',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = '#eab308';
                            e.currentTarget.style.backgroundColor = 'rgba(234, 179, 8, 0.1)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'rgba(234, 179, 8, 0.7)';
                            e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                          title="Edit Task Configuration"
                        >
                          <Edit3 size={14} />
                        </button>

                        {/* Delete Button */}
                        <button 
                          onClick={() => handleCancelTimer(timer.id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'rgba(239, 68, 68, 0.65)',
                            cursor: 'pointer',
                            padding: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderRadius: '4px',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = '#ef4444';
                            e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'rgba(239, 68, 68, 0.65)';
                            e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                          title={timer.status === 'running' || timer.status === 'paused' ? 'Cancel Task' : 'Dismiss'}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>

                    <span style={{
                      ...styles.timerStatusBadge,
                      color: timer.status === 'paused'
                        ? '#eab308'
                        : (timer.status === 'running' 
                            ? (timer.type === 'alarm' ? '#f97316' : (timer.type === 'recurring' ? '#10b981' : 'var(--accent-cyan)')) 
                            : 'var(--success)'),
                      borderColor: timer.status === 'paused'
                        ? 'rgba(234, 179, 8, 0.3)'
                        : (timer.status === 'running' 
                            ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.3)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(0, 240, 255, 0.3)')) 
                            : 'rgba(16, 185, 129, 0.3)')
                    }}>
                      {timer.status === 'paused'
                        ? 'PAUSED'
                        : (timer.status === 'running' 
                            ? (timer.type === 'alarm' ? 'WAITING' : (timer.type === 'recurring' ? 'RECURRING' : 'COUNTDOWN')) 
                            : 'COMPLETED')}
                    </span>
                  </div>

                  <div style={styles.timerBody}>
                    <div style={styles.countdownBox}>
                      <span style={styles.countdownVal}>
                        {timer.status === 'paused' || timer.status === 'running' ? formatTimeLeft(timer.time_left) : '00:00'}
                      </span>
                      <span style={styles.countdownUnit}>
                        {timer.status === 'paused' ? 'paused' : (timer.type === 'recurring' ? 'until next' : (timer.type === 'alarm' ? 'until ring' : 'remaining'))}
                      </span>
                    </div>
                    <div style={styles.timerMeta}>
                      {timer.type === 'alarm' ? (
                        <div>Triggers at: {timer.target_time}</div>
                      ) : (
                        timer.type === 'recurring' ? (
                          <div>Every {timer.interval_hours} hrs | Fired: {timer.fire_count || 0} times</div>
                        ) : (
                          <div>Duration: {timer.duration} sec</div>
                        )
                      )}
                      <div>Started at: {timer.created_at}</div>
                    </div>
                  </div>

                  {timer.agent_id && (
                    <div style={{ marginTop: '4px', padding: '6px 8px', borderRadius: '4px', backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', fontSize: '0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--accent-cyan)', marginBottom: '2px' }}>
                        <span>🤖 Target Agent: {timer.agent_id}</span>
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={timer.prompt}>
                        "{timer.prompt}"
                      </div>
                    </div>
                  )}
                </div>
              ))
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
              <div>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '2px' }}>TASK NAME / LABEL</label>
                <div style={{ fontSize: '1rem', fontWeight: 600, color: '#fff' }}>{infoTimer.label}</div>
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
                  </select>
                </div>

                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>TARGET AGENT</label>
                  <select 
                    value={editTargetAgent}
                    onChange={(e) => setEditTargetAgent(e.target.value)}
                    className="form-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '0.8rem', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(234, 179, 8, 0.3)', color: '#fff' }}
                  >
                    {availableAgents.map(agent => (
                      <option key={agent.id} value={agent.id}>{agent.name}</option>
                    ))}
                  </select>
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
                    {editType === 'one-shot' ? 'DELAY (SECS)' : (editType === 'alarm' ? 'TIME (HH:MM)' : 'INTERVAL (HRS)')}
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
