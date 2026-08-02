import React, { useEffect, useState } from 'react';
import { Kanban, Plus, RefreshCw, Lock, User, Trash2, Zap } from 'lucide-react';
import { styles } from '../styles';

interface Task {
  id: number;
  title: string;
  description: string;
  status: 'BACKLOG' | 'TODO' | 'IN_PROGRESS' | 'IN_REVIEW' | 'DONE' | 'BLOCKED';
  assigned_agent_id: string;
  checkout_lock_until: string;
  checkpoint_data: string;
  created_at: string;
  updated_at: string;
}

const COLUMNS: { id: Task['status']; title: string; color: string }[] = [
  { id: 'BACKLOG',     title: 'Backlog',     color: 'rgba(255,255,255,0.4)' },
  { id: 'TODO',        title: 'To Do',       color: '#3b82f6' },
  { id: 'IN_PROGRESS', title: 'In Progress', color: '#00f0ff' },
  { id: 'IN_REVIEW',   title: 'In Review',   color: '#f59e0b' },
  { id: 'DONE',        title: 'Completed',   color: '#10b981' },
  { id: 'BLOCKED',     title: 'Blocked',     color: '#ef4444' },
];

export function TaskBoardTab() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newStatus, setNewStatus] = useState<Task['status']>('BACKLOG');
  const [newAssignee, setNewAssignee] = useState('');

  const fetchTasks = async () => {
    setLoading(true);
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch('http://localhost:8000/api/tasks', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await res.json();
      setTasks(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch tasks:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch('http://localhost:8000/api/tasks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          title: newTitle,
          description: newDesc,
          status: newStatus,
          assigned_agent_id: newAssignee,
        }),
      });
      if (res.ok) {
        setNewTitle('');
        setNewDesc('');
        setIsCreateOpen(false);
        fetchTasks();
      }
    } catch (err) {
      console.error('Failed to create task:', err);
    }
  };

  const handleUpdateStatus = async (taskId: number, status: Task['status']) => {
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ status }),
      });
      if (res.ok) {
        fetchTasks();
      }
    } catch (err) {
      console.error('Failed to update task status:', err);
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskId}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        fetchTasks();
      }
    } catch (err) {
      console.error('Failed to delete task:', err);
    }
  };

  const handlePulseTask = async (taskId: number) => {
    const token = localStorage.getItem('jarvis_auth_token');
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskId}/pulse`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        fetchTasks();
      }
    } catch (err) {
      console.error('Failed to pulse task:', err);
    }
  };

  return (
    <div style={styles.tabWrapper}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Kanban size={24} style={{ color: 'var(--accent-cyan)' }} />
          <div>
            <h2 className="glow-text-cyan" style={{ fontSize: '1.2rem', margin: 0, fontWeight: 700 }}>
              PAPERCLIP TASK ENGINE & KANBAN
            </h2>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              Atomic task checkout, state checkpoints, and subagent work queues
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={fetchTasks}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
              borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)',
              backgroundColor: 'rgba(255,255,255,0.03)', color: '#fff', fontSize: '0.8rem',
              fontWeight: 600, cursor: 'pointer'
            }}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
              borderRadius: '8px', border: '1px solid rgba(0,240,255,0.4)',
              backgroundColor: 'rgba(0,240,255,0.12)', color: '#00f0ff', fontSize: '0.8rem',
              fontWeight: 600, cursor: 'pointer'
            }}
          >
            <Plus size={14} />
            <span>New Ticket</span>
          </button>
        </div>
      </div>

      {/* Kanban Board Columns */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '12px',
        flex: 1, minHeight: 0, overflowX: 'auto', paddingBottom: '10px'
      }}>
        {COLUMNS.map(col => {
          const columnTasks = tasks.filter(t => t.status === col.id);
          return (
            <div
              key={col.id}
              style={{
                backgroundColor: 'rgba(6, 9, 19, 0.7)',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                borderRadius: '10px', display: 'flex', flexDirection: 'column',
                overflow: 'hidden', minWidth: '220px'
              }}
            >
              {/* Column Header */}
              <div style={{
                padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                backgroundColor: 'rgba(255,255,255,0.02)'
              }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: col.color, letterSpacing: '0.5px' }}>
                  {col.title.toUpperCase()}
                </span>
                <span style={{
                  fontSize: '0.65rem', fontWeight: 700, padding: '2px 7px', borderRadius: '10px',
                  backgroundColor: 'rgba(255,255,255,0.08)', color: 'var(--text-muted)'
                }}>
                  {columnTasks.length}
                </span>
              </div>

              {/* Task Cards */}
              <div style={{ padding: '10px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {columnTasks.map(task => {
                  const isLocked = task.checkout_lock_until && task.checkout_lock_until > new Date().toISOString();
                  return (
                    <div
                      key={task.id}
                      style={{
                        padding: '10px', borderRadius: '8px',
                        border: '1px solid rgba(255,255,255,0.08)',
                        backgroundColor: 'rgba(255,255,255,0.02)',
                        display: 'flex', flexDirection: 'column', gap: '6px',
                        transition: 'all 0.15s'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontWeight: 600 }}>
                          #{task.id}
                        </span>
                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                          {isLocked && (
                            <span title={`Locked until ${task.checkout_lock_until}`}>
                              <Lock size={12} style={{ color: '#f59e0b' }} />
                            </span>
                          )}
                          <button
                            onClick={() => handlePulseTask(task.id)}
                            style={{ background: 'none', border: 'none', color: '#00f0ff', cursor: 'pointer', padding: '2px' }}
                            title="Trigger Pulse Execution"
                          >
                            <Zap size={12} />
                          </button>
                          <button
                            onClick={() => handleDeleteTask(task.id)}
                            style={{ background: 'none', border: 'none', color: 'rgba(239,68,68,0.6)', cursor: 'pointer', padding: '2px' }}
                            title="Delete task"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>

                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff' }}>
                        {task.title}
                      </span>

                      {task.description && (
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                          {task.description}
                        </span>
                      )}

                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '4px' }}>
                        {task.assigned_agent_id ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.65rem', color: 'var(--accent-cyan)' }}>
                            <User size={10} />
                            <span>{task.assigned_agent_id}</span>
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>Unassigned</span>
                        )}

                        <select
                          value={task.status}
                          onChange={e => handleUpdateStatus(task.id, e.target.value as Task['status'])}
                          style={{
                            fontSize: '0.65rem', padding: '2px 4px', borderRadius: '4px',
                            backgroundColor: 'rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.1)',
                            color: '#fff', cursor: 'pointer'
                          }}
                        >
                          {COLUMNS.map(c => (
                            <option key={c.id} value={c.id}>{c.title}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Create Task Modal */}
      {isCreateOpen && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          backgroundColor: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
        }}>
          <form
            onSubmit={handleCreateTask}
            style={{
              width: '100%', maxWidth: '480px', backgroundColor: '#0a0e1a',
              border: '1px solid rgba(0,240,255,0.3)', borderRadius: '12px',
              padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px'
            }}
          >
            <h3 style={{ fontSize: '1rem', color: '#fff', margin: 0, fontWeight: 700 }} className="glow-text-cyan">
              CREATE NEW TASK TICKET
            </h3>

            <input
              type="text"
              placeholder="Task Title *"
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              className="form-input"
              required
            />

            <textarea
              placeholder="Description & Acceptance Criteria..."
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              className="form-input"
              rows={4}
            />

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '4px', display: 'block' }}>Initial Status</label>
                <select
                  value={newStatus}
                  onChange={e => setNewStatus(e.target.value as Task['status'])}
                  className="form-input"
                >
                  {COLUMNS.map(c => (
                    <option key={c.id} value={c.id}>{c.title}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '4px', display: 'block' }}>Assign Agent ID</label>
                <input
                  type="text"
                  placeholder="e.g. quant_analyst"
                  value={newAssignee}
                  onChange={e => setNewAssignee(e.target.value)}
                  className="form-input"
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                style={{
                  padding: '8px 16px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)',
                  backgroundColor: 'transparent', color: 'var(--text-dim)', fontSize: '0.8rem', cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                style={{
                  padding: '8px 16px', borderRadius: '6px', border: '1px solid rgba(0,240,255,0.4)',
                  backgroundColor: 'rgba(0,240,255,0.15)', color: '#00f0ff', fontSize: '0.8rem',
                  fontWeight: 600, cursor: 'pointer'
                }}
              >
                Create Task
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
