import React, { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, Terminal, CheckCircle2, XCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { styles } from '../styles';

interface MCPServer {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  connected: boolean;
  tools_count: number;
}

const AUTH = (): Record<string, string> => {
  const token = localStorage.getItem('jarvis_auth_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
};

const API = 'http://localhost:8000/api/mcp/servers';

function EnvEditor({ value, onChange }: {
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}) {
  const entries = Object.entries(value);
  const set = (idx: number, k: string, v: string) => {
    const next = [...entries];
    next[idx] = [k, v];
    onChange(Object.fromEntries(next.filter(([key]) => key)));
  };
  const remove = (idx: number) => {
    const next = entries.filter((_, i) => i !== idx);
    onChange(Object.fromEntries(next));
  };
  const add = () => onChange({ ...value, '': '' });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {entries.map(([k, v], i) => (
        <div key={i} style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <input
            className="form-input" placeholder="KEY" value={k}
            onChange={e => set(i, e.target.value, v)}
            style={{ flex: '0 0 140px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
          />
          <span style={{ color: 'var(--text-dim)' }}>=</span>
          <input
            className="form-input" placeholder="value" value={v}
            onChange={e => set(i, k, e.target.value)}
            style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
          />
          <button type="button" onClick={() => remove(i)}
            style={{ background: 'none', border: 'none', color: 'rgba(239,68,68,0.6)', cursor: 'pointer', padding: '4px' }}>
            <XCircle size={14} />
          </button>
        </div>
      ))}
      <button type="button" onClick={add}
        style={{ alignSelf: 'flex-start', background: 'none', border: '1px dashed rgba(255,255,255,0.15)', borderRadius: '6px', color: 'var(--text-dim)', padding: '4px 10px', fontSize: '0.75rem', cursor: 'pointer' }}>
        + Add env var
      </button>
    </div>
  );
}

export function MCPTab() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [command, setCommand] = useState('npx');
  const [argsStr, setArgsStr] = useState('');
  const [env, setEnv] = useState<Record<string, string>>({});

  const load = () => {
    setLoading(true);
    fetch(API, { headers: AUTH() })
      .then(r => r.json())
      .then(data => setServers(Array.isArray(data) ? data : []))
      .catch(() => setServers([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !command.trim()) return;
    setSaving(true);
    try {
      const args = argsStr.split(/\s+/).filter(Boolean);
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH() },
        body: JSON.stringify({ name: name.trim(), command, args, env }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        setName(''); setCommand('npx'); setArgsStr(''); setEnv({});
        setShowForm(false);
        load();
      } else {
        alert(data.warning || 'Config saved but server failed to connect — check logs.');
        load();
      }
    } catch (e) {
      alert('Failed to save MCP server config.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (serverName: string) => {
    if (!confirm(`Remove MCP server "${serverName}"? It will be disconnected.`)) return;
    await fetch(`${API}/${encodeURIComponent(serverName)}`, { method: 'DELETE', headers: AUTH() });
    load();
  };

  const statusColor = (connected: boolean) => connected ? '#10b981' : '#ef4444';
  const statusLabel = (connected: boolean) => connected ? 'CONNECTED' : 'DISCONNECTED';

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>MCP SERVERS</h2>
          <p style={styles.tabSubtitle}>Model Context Protocol — connect external tools to your agents</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button onClick={load} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-dim)', cursor: 'pointer', padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
            <RefreshCw size={14} />
            Refresh
          </button>
          <button onClick={() => setShowForm(v => !v)} className="btn-primary">
            <Plus size={14} />
            Add Server
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '800px', flex: 1, overflowY: 'auto' }}>

        {/* Add Server Form */}
        {showForm && (
          <form onSubmit={handleSave} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }} className="glass-panel">
            <h3 style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, margin: 0 }} className="glow-text-cyan">NEW MCP SERVER</h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Server name (unique key)</label>
                <input className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. filesystem" required />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Command</label>
                <input className="form-input" value={command} onChange={e => setCommand(e.target.value)} placeholder="e.g. npx" required />
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Args (space-separated)</label>
              <input className="form-input" value={argsStr} onChange={e => setArgsStr(e.target.value)} placeholder="e.g. -y @modelcontextprotocol/server-filesystem /data" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Environment variables</label>
              <EnvEditor value={env} onChange={setEnv} />
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
              <button type="submit" className="btn-primary" disabled={saving}>
                <CheckCircle2 size={14} />
                {saving ? 'Connecting…' : 'Save & Connect'}
              </button>
              <button type="button" onClick={() => setShowForm(false)}
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-dim)', cursor: 'pointer', padding: '0 16px', height: '42px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}>
                Cancel
              </button>
            </div>

            {/* Quick templates */}
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '12px' }}>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>QUICK TEMPLATES</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {[
                  { name: 'filesystem', command: 'npx', args: '-y @modelcontextprotocol/server-filesystem /data' },
                  { name: 'brave-search', command: 'npx', args: '-y @modelcontextprotocol/server-brave-search' },
                  { name: 'github', command: 'npx', args: '-y @modelcontextprotocol/server-github' },
                  { name: 'puppeteer', command: 'npx', args: '-y @modelcontextprotocol/server-puppeteer' },
                ].map(t => (
                  <button key={t.name} type="button"
                    onClick={() => { setName(t.name); setCommand(t.command); setArgsStr(t.args); }}
                    style={{ padding: '4px 12px', borderRadius: '16px', border: '1px solid rgba(0,240,255,0.2)', background: 'transparent', color: 'rgba(0,240,255,0.7)', fontSize: '0.72rem', cursor: 'pointer' }}>
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
          </form>
        )}

        {/* Server Cards */}
        {loading ? (
          <p style={{ color: 'var(--text-dim)', fontSize: '0.9rem', padding: '20px 0' }}>Loading servers…</p>
        ) : servers.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' }} className="glass-panel">
            <Terminal size={32} style={{ color: 'var(--text-dim)', marginBottom: '12px' }} />
            <p style={{ color: 'var(--text-dim)', fontSize: '0.9rem', marginBottom: '6px' }}>No MCP servers configured</p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Click "Add Server" to connect a Model Context Protocol server and give your agents more tools.</p>
          </div>
        ) : (
          servers.map(server => (
            <div key={server.name} className="glass-panel" style={{ padding: '16px 20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
                onClick={() => setExpandedCard(expandedCard === server.name ? null : server.name)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {expandedCard === server.name ? <ChevronDown size={16} style={{ color: 'var(--text-dim)' }} /> : <ChevronRight size={16} style={{ color: 'var(--text-dim)' }} />}
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>{server.name}</span>
                    <span style={{ marginLeft: '10px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                      {server.command} {server.args.join(' ')}
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {server.tools_count > 0 && (
                    <span style={{ fontSize: '0.72rem', color: '#00f0ff', background: 'rgba(0,240,255,0.1)', border: '1px solid rgba(0,240,255,0.2)', borderRadius: '12px', padding: '2px 8px' }}>
                      {server.tools_count} tools
                    </span>
                  )}
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.75rem', color: statusColor(server.connected), fontWeight: 600 }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor(server.connected), display: 'inline-block', boxShadow: `0 0 6px ${statusColor(server.connected)}` }} />
                    {statusLabel(server.connected)}
                  </span>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(server.name); }}
                    style={{ background: 'none', border: 'none', color: 'rgba(239,68,68,0.6)', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', borderRadius: '4px' }}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {expandedCard === server.name && (
                <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '4px 12px', fontSize: '0.8rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Command:</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: '#00f0ff' }}>{server.command}</span>
                    <span style={{ color: 'var(--text-muted)' }}>Args:</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: '#fff', wordBreak: 'break-all' }}>{server.args.join(' ') || '—'}</span>
                    {Object.keys(server.env).length > 0 && (
                      <>
                        <span style={{ color: 'var(--text-muted)' }}>Env:</span>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', fontSize: '0.75rem' }}>
                          {Object.keys(server.env).join(', ')}
                        </span>
                      </>
                    )}
                  </div>
                  {!server.connected && (
                    <p style={{ fontSize: '0.75rem', color: '#f59e0b', margin: 0 }}>
                      ⚠ Server is not connected — the process may have failed to start. Check Docker logs for details.
                    </p>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {/* Docs hint */}
        <div style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(0,240,255,0.04)', border: '1px solid rgba(0,240,255,0.1)' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', margin: 0, lineHeight: 1.6 }}>
            💡 <strong style={{ color: 'var(--text-muted)' }}>What is MCP?</strong> Model Context Protocol lets your agents use external tools —
            file systems, browsers, databases, APIs — via a standard JSON-RPC interface.
            Browse <a href="https://github.com/modelcontextprotocol/servers" target="_blank" rel="noreferrer"
              style={{ color: '#00f0ff' }}>modelcontextprotocol/servers</a> for ready-made servers.
            After adding a server, assign the <code style={{ color: '#00f0ff' }}>mcp_all</code> skill (or the server's name) to an agent.
          </p>
        </div>
      </div>
    </div>
  );
}
