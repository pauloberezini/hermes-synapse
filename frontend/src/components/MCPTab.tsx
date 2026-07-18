import React, { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, Terminal, CheckCircle2, ChevronDown, ChevronRight, Globe } from 'lucide-react';
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

const API = '/api/mcp/servers';

export function MCPTab() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [name, setName] = useState('');
  const [openapiUrl, setOpenapiUrl] = useState('');
  const [authType, setAuthType] = useState<'none' | 'static'>('none');

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
    if (!name.trim()) return;

    setSaving(true);
    try {
      if (!openapiUrl.trim()) {
        alert('Please enter the OpenAPI spec JSON URL.');
        setSaving(false);
        return;
      }
      const finalEnv: Record<string, string> = { OPENAPI_URL: openapiUrl.trim() };
      if (authType === 'static') finalEnv.STATIC_BEARER_TOKEN = '${STATIC_BEARER_TOKEN}';

      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH() },
        body: JSON.stringify({
          name: name.trim().toLowerCase().replace(/[^a-z0-9_-]/g, ''),
          command: 'python3',
          args: ['/app/backend/mcp_openapi_proxy.py'],
          env: finalEnv,
        }),
      });
      const data = await res.json();
      if (data.status === 'awaiting_approval') {
        setName('');
        setOpenapiUrl('');
        setAuthType('none');
        setShowForm(false);
        alert(`Validated R4 connection request ${data.task_id}. Approve it twice in Processes & Control.`);
        load();
      } else {
        alert(data.detail || data.warning || 'Connection proposal was not created.');
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
          <p style={styles.tabSubtitle}>Model Context Protocol — connect external tools and APIs to your agents</p>
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
          <form onSubmit={handleSave} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }} className="glass-panel">
            <h3 style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, margin: 0 }} className="glow-text-cyan">NEW MCP SERVER</h3>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 10px', border: '1px solid rgba(0,240,255,0.16)', borderRadius: '6px', color: '#75d9ef', background: 'rgba(0,140,190,0.06)', fontSize: '0.78rem', fontWeight: 600 }}>
              <Globe size={14} />
              <span>Governed OpenAPI Bridge · R4</span>
            </div>

            {/* Server name */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Server unique name (latin, lowercase, no spaces)</label>
              <input className="form-input" value={name} onChange={e => setName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))} placeholder="e.g. filesystem or market_data" required />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>OpenAPI Specification URL</label>
              <input className="form-input" value={openapiUrl} onChange={e => setOpenapiUrl(e.target.value)} placeholder="https://service.example/openapi.json" required />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Authentication</label>
              <select
                className="form-input"
                value={authType}
                onChange={e => setAuthType(e.target.value as 'none' | 'static')}
              >
                <option value="none">No authentication</option>
                <option value="static">STATIC_BEARER_TOKEN environment reference</option>
              </select>
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
          servers.map(server => {
            const isOpenAPI = server.args.includes('/app/backend/mcp_openapi_proxy.py');
            return (
              <div key={server.name} className="glass-panel" style={{ padding: '16px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
                  onClick={() => setExpandedCard(expandedCard === server.name ? null : server.name)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {expandedCard === server.name ? <ChevronDown size={16} style={{ color: 'var(--text-dim)' }} /> : <ChevronRight size={16} style={{ color: 'var(--text-dim)' }} />}
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>{server.name}</span>
                        <span style={{
                          fontSize: '0.65rem',
                          background: isOpenAPI ? 'rgba(16,185,129,0.1)' : 'rgba(0,240,255,0.1)',
                          border: isOpenAPI ? '1px solid rgba(16,185,129,0.2)' : '1px solid rgba(0,240,255,0.2)',
                          color: isOpenAPI ? '#10b981' : '#00f0ff',
                          borderRadius: '4px',
                          padding: '1px 5px',
                          fontWeight: 600
                        }}>
                          {isOpenAPI ? 'REST/OpenAPI' : 'Stdio Command'}
                        </span>
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                        {isOpenAPI ? server.env.OPENAPI_URL : `${server.command} ${server.args.join(' ')}`}
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
                    <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '4px 12px', fontSize: '0.8rem' }}>
                      {isOpenAPI ? (
                        <>
                          <span style={{ color: 'var(--text-muted)' }}>Specification URL:</span>
                          <span style={{ fontFamily: 'var(--font-mono)', color: '#00f0ff', wordBreak: 'break-all' }}>{server.env.OPENAPI_URL}</span>
                          {server.env.AUTH_TOKEN_URL && (
                            <>
                              <span style={{ color: 'var(--text-muted)' }}>Auth Endpoint:</span>
                              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>{server.env.AUTH_TOKEN_URL}</span>
                            </>
                          )}
                          {server.env.AUTH_USERNAME && (
                            <>
                              <span style={{ color: 'var(--text-muted)' }}>Login Account:</span>
                              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>{server.env.AUTH_USERNAME}</span>
                            </>
                          )}
                          {server.env.STATIC_BEARER_TOKEN && (
                            <>
                              <span style={{ color: 'var(--text-muted)' }}>Static Token:</span>
                              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>••••••••••••••••</span>
                            </>
                          )}
                        </>
                      ) : (
                        <>
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
                        </>
                      )}
                    </div>
                    {!server.connected && (
                      <p style={{ fontSize: '0.75rem', color: '#f59e0b', margin: 0 }}>
                        ⚠ Server is not connected — the process may have failed to start or spec was unreachable. Check logs for details.
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* Docs hint */}
        <div style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(0,240,255,0.04)', border: '1px solid rgba(0,240,255,0.1)' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', margin: 0, lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--text-muted)' }}>Governed connection:</strong> OpenAPI bridges are validated first and activated only after two explicit approvals in Processes &amp; Control.
          </p>
        </div>
      </div>
    </div>
  );
}
