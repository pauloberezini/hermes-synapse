import { useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { CheckCircle2, Edit3, Plus, Trash2 } from 'lucide-react';
import type { AgentModel } from '../types';
import { styles } from '../styles';

interface AgentsAdminTabProps {
  agents: AgentModel[];
  models: { id: string; name: string }[];
  fetchAgents: () => void;
  t: (key: string) => string;
}

const emptyAgent: AgentModel = {
  id: '',
  name: '',
  system_prompt: '',
  model: 'qwen3:8b',
  agent_type: 'agent',
  role: 'Specialist',
  status: 'idle',
  is_enabled: true,
  model_provider: 'ollama',
  model_type: 'local',
  skills: '',
  temperature: 0.7,
  model_params: {},
};

export function AgentsAdminTab({ agents, models, fetchAgents, t }: AgentsAdminTabProps) {
  const [draft, setDraft] = useState<AgentModel>(emptyAgent);
  const [paramsText, setParamsText] = useState('{}');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const selected = useMemo(() => agents.find(agent => agent.id === draft.id), [agents, draft.id]);

  useEffect(() => {
    setParamsText(JSON.stringify(draft.model_params || {}, null, 2));
  }, [draft.id, draft.model_params]);

  const startCreate = () => {
    setDraft({ ...emptyAgent, id: `agent_${Date.now().toString().slice(-5)}` });
    setParamsText('{}');
    setError('');
  };

  const startEdit = (agent: AgentModel) => {
    setDraft({
      ...emptyAgent,
      ...agent,
      model_params: agent.model_params || {},
    });
    setParamsText(JSON.stringify(agent.model_params || {}, null, 2));
    setError('');
  };

  const saveAgent = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    let modelParams: Record<string, unknown> = {};
    try {
      modelParams = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch {
      setSaving(false);
      setError('model_params must be valid JSON.');
      return;
    }

    const cleanId = draft.id.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    try {
      const token = localStorage.getItem('jarvis_auth_token');
      const response = await fetch('/api/agents', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          ...draft,
          id: cleanId,
          model_params: modelParams,
          status: draft.is_enabled ? (draft.status || 'idle') : 'disabled',
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      setDraft({ ...emptyAgent });
      setParamsText('{}');
      fetchAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const deleteAgent = async (agent: AgentModel) => {
    if (!window.confirm(`Delete agent "${agent.name}"?`)) return;
    const response = await fetch(`/api/subagents/${agent.id}`, { method: 'DELETE' });
    if (response.ok) {
      fetchAgents();
      if (draft.id === agent.id) setDraft({ ...emptyAgent });
    }
  };

  const toggleAgent = async (agent: AgentModel) => {
    const nextEnabled = !agent.is_enabled;
    const token = localStorage.getItem('jarvis_auth_token');
    await fetch('/api/agents', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        ...agent,
        is_enabled: nextEnabled,
        status: nextEnabled ? 'idle' : 'disabled',
        model_params: agent.model_params || {},
      }),
    });
    fetchAgents();
  };

  const field = (label: string, child: ReactNode) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600 }}>
      {label}
      {child}
    </label>
  );

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>{t('agentAdminTitle')}</h2>
          <p style={styles.tabSubtitle}>{t('agentAdminSubtitle')}</p>
        </div>
        <button className="btn-primary" onClick={startCreate}>
          <Plus size={16} />
          <span>{t('createAgent')}</span>
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 430px) 1fr', gap: 20, minHeight: 0, flex: 1 }}>
        <div className="glass-panel" style={{ padding: 16, overflowY: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {agents.map(agent => (
              <div key={agent.id} style={{
                padding: 12,
                borderRadius: 8,
                border: draft.id === agent.id ? '1px solid rgba(0,240,255,0.35)' : '1px solid rgba(255,255,255,0.06)',
                background: draft.id === agent.id ? 'rgba(0,240,255,0.07)' : 'rgba(255,255,255,0.025)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ color: '#fff', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{agent.name}</div>
                    <div style={{ color: 'var(--text-dim)', fontSize: '0.75rem', marginTop: 3 }}>{agent.role || 'Specialist'} · {agent.model_type || 'external'} · {agent.model_provider || 'openrouter'}</div>
                    <div style={{ color: agent.is_enabled ? 'var(--success)' : 'var(--danger)', fontSize: '0.72rem', marginTop: 6, fontWeight: 700 }}>{agent.is_enabled ? t('enabled') : t('disabled')} · {agent.status || 'idle'}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button className="icon-btn" title={t('editAgent')} onClick={() => startEdit(agent)}><Edit3 size={14} /></button>
                    <button className="icon-btn" title={agent.is_enabled ? t('disable') : t('enable')} onClick={() => toggleAgent(agent)}><CheckCircle2 size={14} /></button>
                    <button className="icon-btn danger" title={t('deleteAgent')} onClick={() => deleteAgent(agent)}><Trash2 size={14} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <form className="glass-panel" onSubmit={saveAgent} style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: 4 }}>{selected ? t('editAgent') : t('createAgent')}</h3>
            <p style={{ color: 'var(--text-dim)', fontSize: '0.82rem' }}>ID: {draft.id || 'new-agent'}</p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {field('ID', <input className="form-input" required value={draft.id} onChange={e => setDraft({ ...draft, id: e.target.value.replace(/[^a-zA-Z0-9_-]/g, '') })} />)}
            {field('Name', <input className="form-input" required value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} />)}
            {field(t('role'), <input className="form-input" value={draft.role || ''} onChange={e => setDraft({ ...draft, role: e.target.value })} />)}
            {field(t('status'), <input className="form-input" value={draft.status || 'idle'} onChange={e => setDraft({ ...draft, status: e.target.value })} />)}
            {field(t('modelType'), (
              <select className="form-input" value={draft.model_type || 'external'} onChange={e => setDraft({ ...draft, model_type: e.target.value })}>
                <option value="external">{t('external')}</option>
                <option value="local">{t('local')}</option>
              </select>
            ))}
            {field(t('provider'), <input className="form-input" value={draft.model_provider || 'openrouter'} onChange={e => setDraft({ ...draft, model_provider: e.target.value })} placeholder="openrouter / ollama / local" />)}
          </div>

          {field(t('model'), (
            <select className="form-input" value={draft.model} onChange={e => setDraft({ ...draft, model: e.target.value })}>
              {[{ id: draft.model, name: draft.model }, ...models].filter((m, idx, arr) => m.id && arr.findIndex(x => x.id === m.id) === idx).map(model => (
                <option key={model.id} value={model.id}>{model.name || model.id}</option>
              ))}
            </select>
          ))}

          {field(t('skills'), <input className="form-input" value={draft.skills || ''} onChange={e => setDraft({ ...draft, skills: e.target.value })} placeholder="web_search,python_sandbox" />)}
          {field(t('instructions'), <textarea className="form-input" rows={8} required value={draft.system_prompt} onChange={e => setDraft({ ...draft, system_prompt: e.target.value })} />)}
          {field('model_params JSON', <textarea className="form-input" rows={5} value={paramsText} onChange={e => setParamsText(e.target.value)} />)}

          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            <input type="checkbox" checked={!!draft.is_enabled} onChange={e => setDraft({ ...draft, is_enabled: e.target.checked })} />
            {t('enabled')}
          </label>

          {error && <div style={{ color: 'var(--danger)', fontSize: '0.85rem' }}>{error}</div>}

          <button className="btn-primary" type="submit" disabled={saving || !draft.id || !draft.name || !draft.system_prompt} style={{ alignSelf: 'flex-start' }}>
            <CheckCircle2 size={16} />
            <span>{saving ? 'Saving...' : t('saveAgent')}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
