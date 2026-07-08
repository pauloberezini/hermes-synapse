import { useState } from 'react';
import { Clock, Trash2 } from 'lucide-react';
import { styles } from '../styles';
import { formatTimeLeft } from '../utils';

interface ScheduleTabProps {
  timers: { 
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
  }[];
  subagents: { 
    id: string; 
    name: string; 
    agent_type?: string;
  }[];
  handleCancelTimer: (id: string) => void;
}

export function ScheduleTab({
  timers,
  subagents,
  handleCancelTimer
}: ScheduleTabProps) {
  const [taskType, setTaskType] = useState<'one-shot' | 'alarm' | 'recurring'>('one-shot');
  const [taskLabel, setTaskLabel] = useState('');
  const [targetAgent, setTargetAgent] = useState('jarvis');
  const [taskPrompt, setTaskPrompt] = useState('');
  const [taskDuration, setTaskDuration] = useState(60);
  const [taskTimeStr, setTaskTimeStr] = useState('');
  const [taskInterval, setTaskInterval] = useState(1);

  const availableAgents = [
    { id: 'jarvis', name: 'Jarvis (Main Orchestrator)' },
    ...subagents.map(a => ({ id: a.id, name: a.name }))
  ];

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

    fetch('http://localhost:8000/api/timers', {
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
            {timers.length === 0 ? (
              <div style={styles.emptyTimersMsg}>
                No active timers or scheduled tasks found, Sir.
              </div>
            ) : (
              timers.map((timer) => (
                <div 
                  key={timer.id} 
                  style={{
                    ...styles.timerCard,
                    borderColor: timer.status === 'running' 
                      ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.2)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(0, 240, 255, 0.2)')) 
                      : 'rgba(255, 255, 255, 0.05)',
                    backgroundColor: timer.status === 'running' 
                      ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.02)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.02)' : 'rgba(0, 240, 255, 0.02)')) 
                      : 'rgba(255, 255, 255, 0.01)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px'
                  }}
                >
                  <div style={styles.timerHeader}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <span style={styles.timerLabel}>{timer.label}</span>
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
                          marginLeft: '8px',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = '#ef4444';
                          e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = 'rgba(239, 68, 68, 0.65)';
                          e.currentTarget.style.backgroundColor = 'transparent';
                        }}
                        title={timer.status === 'running' ? 'Cancel' : 'Dismiss'}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <span style={{
                      ...styles.timerStatusBadge,
                      color: timer.status === 'running' 
                          ? (timer.type === 'alarm' ? '#f97316' : (timer.type === 'recurring' ? '#10b981' : 'var(--accent-cyan)')) 
                          : 'var(--success)',
                      borderColor: timer.status === 'running' 
                          ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.3)' : (timer.type === 'recurring' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(0, 240, 255, 0.3)')) 
                          : 'rgba(16, 185, 129, 0.3)'
                    }}>
                      {timer.status === 'running' 
                        ? (timer.type === 'alarm' ? 'WAITING' : (timer.type === 'recurring' ? 'RECURRING' : 'COUNTDOWN')) 
                        : 'COMPLETED'}
                    </span>
                  </div>

                  <div style={styles.timerBody}>
                    <div style={styles.countdownBox}>
                      <span style={styles.countdownVal}>
                        {timer.status === 'running' ? formatTimeLeft(timer.time_left) : '00:00'}
                      </span>
                      <span style={styles.countdownUnit}>
                        {timer.type === 'recurring' ? 'until next' : (timer.type === 'alarm' ? 'until ring' : 'remaining')}
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
    </div>
  );
}
