import React, { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, Terminal, CheckCircle2, XCircle, ChevronDown, ChevronRight, Globe, Code } from 'lucide-react';
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

  // General Form state
  const [name, setName] = useState('');
  const [serverType, setServerType] = useState<'stdio' | 'openapi'>('stdio');

  // Stdio transport state
  const [command, setCommand] = useState('npx');
  const [argsStr, setArgsStr] = useState('');
  const [env, setEnv] = useState<Record<string, string>>({});

  // OpenAPI transport state
  const [openapiUrl, setOpenapiUrl] = useState('');
  const [authType, setAuthType] = useState<'none' | 'oauth2' | 'static'>('none');
  const [authTokenUrl, setAuthTokenUrl] = useState('');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [staticToken, setStaticToken] = useState('');

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
      let finalCommand = command;
      let finalArgs: string[] = [];
      let finalEnv: Record<string, string> = {};

      if (serverType === 'openapi') {
        if (!openapiUrl.trim()) {
          alert('Please enter the OpenAPI spec JSON URL.');
          setSaving(false);
          return;
        }
        finalCommand = 'python3';
        finalArgs = ['/app/backend/mcp_openapi_proxy.py'];
        finalEnv = {
          OPENAPI_URL: openapiUrl.trim(),
        };

        if (authType === 'oauth2') {
          if (authTokenUrl) finalEnv.AUTH_TOKEN_URL = authTokenUrl.trim();
          if (authUsername) finalEnv.AUTH_USERNAME = authUsername.trim();
          if (authPassword) finalEnv.AUTH_PASSWORD = authPassword.trim();
        } else if (authType === 'static') {
          if (staticToken) finalEnv.STATIC_BEARER_TOKEN = staticToken.trim();
        }
      } else {
        if (!command.trim()) {
          alert('Please enter a command.');
          setSaving(false);
          return;
        }
        finalArgs = argsStr.split(/\s+/).filter(Boolean);
        finalEnv = env;
      }

      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH() },
        body: JSON.stringify({ name: name.trim().toLowerCase().replace(/[^a-z0-9_-]/g, ''), command: finalCommand, args: finalArgs, env: finalEnv }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        // Reset states
        setName(''); setCommand('npx'); setArgsStr(''); setEnv({});
        setOpenapiUrl(''); setAuthType('none'); setAuthTokenUrl(''); setAuthUsername(''); setAuthPassword(''); setStaticToken('');
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

            {/* Server Type Tabs */}
            <div style={{ display: 'flex', gap: '10px', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px' }}>
              <button
                type="button"
                onClick={() => setServerType('stdio')}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  padding: '8px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '0.8rem',
                  fontWeight: 600, background: serverType === 'stdio' ? 'rgba(0,240,255,0.15)' : 'rgba(255,255,255,0.02)',
                  color: serverType === 'stdio' ? '#00f0ff' : 'var(--text-dim)', transition: 'all 0.2s'
                }}
              >
                <Code size={14} />
                <span>Local Command (Stdio)</span>
              </button>
              <button
                type="button"
                onClick={() => setServerType('openapi')}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  padding: '8px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '0.8rem',
                  fontWeight: 600, background: serverType === 'openapi' ? 'rgba(0,240,255,0.15)' : 'rgba(255,255,255,0.02)',
                  color: serverType === 'openapi' ? '#00f0ff' : 'var(--text-dim)', transition: 'all 0.2s'
                }}
              >
                <Globe size={14} />
                <span>Remote REST API (OpenAPI)</span>
              </button>
            </div>

            {/* Server name */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Server unique name (latin, lowercase, no spaces)</label>
              <input className="form-input" value={name} onChange={e => setName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))} placeholder="e.g. filesystem or market_data" required />
            </div>

            {serverType === 'stdio' ? (
              /* Stdio Command Fields */
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Command</label>
                  <input className="form-input" value={command} onChange={e => setCommand(e.target.value)} placeholder="e.g. npx" required />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Args (space-separated)</label>
                  <input className="form-input" value={argsStr} onChange={e => setArgsStr(e.target.value)} placeholder="e.g. -y @modelcontextprotocol/server-filesystem /data" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }} />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Environment variables</label>
                  <EnvEditor value={env} onChange={setEnv} />
                </div>
              </>
            ) : (
              /* OpenAPI REST Fields */
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>OpenAPI Specification URL (openapi.json or swagger.json)</label>
                  <input className="form-input" value={openapiUrl} onChange={e => setOpenapiUrl(e.target.value)} placeholder="e.g. https://mcp-antonbustrov.waw0.amvera.tech/openapi.json" required />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Authentication Method</label>
                  <select
                    className="form-input"
                    value={authType}
                    onChange={e => setAuthType(e.target.value as any)}
                  >
                    <option value="none">No authentication</option>
                    <option value="oauth2">OAuth2 Password Grant (username/password)</option>
                    <option value="static">Static Bearer Token (API Key / JWT)</option>
                  </select>
                </div>

                {authType === 'oauth2' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                      <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Token Endpoint URL</label>
                      <input className="form-input" value={authTokenUrl} onChange={e => setAuthTokenUrl(e.target.value)} placeholder="e.g. https://mcp-antonbustrov.waw0.amvera.tech/token" />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Username</label>
                        <input className="form-input" value={authUsername} onChange={e => setAuthUsername(e.target.value)} placeholder="user" />
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Password</label>
                        <input type="password" className="form-input" value={authPassword} onChange={e => setAuthPassword(e.target.value)} placeholder="••••••••" />
                      </div>
                    </div>
                  </div>
                )}

                {authType === 'static' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Static Bearer Token</label>
                    <input type="password" className="form-input" value={staticToken} onChange={e => setStaticToken(e.target.value)} placeholder="ey..." />
                  </div>
                )}
              </>
            )}

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

            {/* Quick templates (only for stdio mode) */}
            {serverType === 'stdio' && (
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
            )}
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
            💡 <strong style={{ color: 'var(--text-muted)' }}>Choosing Server Type:</strong> Use <strong style={{ color: 'var(--text-muted)' }}>Local Command (Stdio)</strong> for local MCP servers (npx, python scripts). Use <strong style={{ color: 'var(--text-muted)' }}>Remote REST API (OpenAPI)</strong> to dynamically connect any FastAPI / Swagger service — simply paste the URL and login credentials if auth is required.
          </p>
        </div>
      </div>
    </div>
  );
}
