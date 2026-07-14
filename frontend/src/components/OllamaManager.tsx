import { AlertTriangle, Box, CheckCircle2, Cpu, Download, HardDrive, Loader2, Play, RefreshCw, Server, Trash2, Unplug } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { OllamaModel, OllamaStatus } from '../types';

interface OllamaManagerProps {
  selectedModel: string;
  onSelectModel: (model: string) => void;
}

function formatBytes(value?: number) {
  if (!value || value < 1) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const unit = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** unit).toFixed(unit > 2 ? 1 : 0)} ${units[unit]}`;
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(detail?.message || detail || data.error || `HTTP ${response.status}`);
  }
  return data as T;
}

export function OllamaManager({ selectedModel, onSelectModel }: OllamaManagerProps) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [running, setRunning] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pullName, setPullName] = useState('');
  const [pulling, setPulling] = useState(false);
  const [pullStatus, setPullStatus] = useState('');
  const [pullProgress, setPullProgress] = useState(0);
  const [busyModel, setBusyModel] = useState('');

  const runningNames = useMemo(() => new Set(running.map(model => model.name || model.model || '')), [running]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const nextStatus = await apiJson<OllamaStatus>('/api/ollama/status');
      setStatus(nextStatus);
      if (!nextStatus.available) {
        setModels([]);
        setRunning([]);
        setError(nextStatus.error || 'Ollama is unavailable.');
        return;
      }
      const [modelData, runningData] = await Promise.all([
        apiJson<{ models: OllamaModel[] }>('/api/ollama/models'),
        apiJson<{ models: OllamaModel[] }>('/api/ollama/running'),
      ]);
      setModels(modelData.models || []);
      setRunning(runningData.models || []);
      setError('');
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Could not connect to Ollama.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const pullModel = async () => {
    const model = pullName.trim();
    if (!model || pulling) return;
    setPulling(true);
    setPullStatus('Connecting to registry…');
    setPullProgress(0);
    setError('');
    try {
      const response = await fetch('/api/ollama/models/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });
      if (!response.ok || !response.body) throw new Error(`Pull failed: HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.error) throw new Error(event.error);
          setPullStatus(event.status || 'Downloading…');
          if (event.total && event.completed != null) setPullProgress(Math.min(100, Math.round(event.completed / event.total * 100)));
        }
        if (done) break;
      }
      setPullStatus('Model installed');
      setPullProgress(100);
      setPullName('');
      onSelectModel(model);
      await refresh();
    } catch (pullError) {
      setError(pullError instanceof Error ? pullError.message : 'Model pull failed.');
      setPullStatus('');
    } finally {
      setPulling(false);
    }
  };

  const unloadModel = async (model: string) => {
    setBusyModel(model);
    try {
      await apiJson('/api/ollama/models/unload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model }) });
      await refresh();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Could not unload model.');
    } finally {
      setBusyModel('');
    }
  };

  const deleteModel = async (model: string) => {
    if (!window.confirm(`Delete local model “${model}”? This removes its files from Ollama.`)) return;
    setBusyModel(model);
    try {
      await apiJson(`/api/ollama/models/${encodeURIComponent(model)}`, { method: 'DELETE' });
      if (selectedModel === model) onSelectModel('');
      await refresh();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Could not delete model.');
    } finally {
      setBusyModel('');
    }
  };

  return (
    <section className="ollama-manager" aria-labelledby="ollama-manager-title">
      <header>
        <div className="ollama-manager-title"><span><Server size={18} /></span><div><h3 id="ollama-manager-title">Ollama Runtime</h3><p>{status?.base_url || 'Native local model provider'}</p></div></div>
        <div className={`ollama-health ${status?.available ? 'is-online' : 'is-offline'}`} role="status">
          {loading ? <Loader2 size={14} className="spin-slow" /> : status?.available ? <CheckCircle2 size={14} /> : <Unplug size={14} />}
          <span>{loading ? 'Checking…' : status?.available ? `Online · v${status.version || '?'}` : 'Offline'}</span>
        </div>
        <button type="button" className="ollama-refresh" onClick={() => void refresh()} disabled={loading} aria-label="Refresh Ollama"><RefreshCw size={15} /></button>
      </header>

      {error && <div className="ollama-error" role="alert"><AlertTriangle size={15} /><span>{error}</span></div>}

      <div className="ollama-runtime-stats">
        <div><HardDrive size={15} /><span>Installed</span><strong>{status?.models_count ?? models.length}</strong></div>
        <div><Cpu size={15} /><span>Loaded</span><strong>{status?.running_count ?? running.length}</strong></div>
        <div><Box size={15} /><span>Selected</span><strong title={selectedModel}>{selectedModel || 'None'}</strong></div>
      </div>

      <div className="ollama-pull">
        <label><Download size={16} /><input value={pullName} onChange={event => setPullName(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void pullModel(); } }} placeholder="Model name, e.g. qwen3:8b" disabled={pulling || !status?.available} aria-label="Model to pull" /></label>
        <button type="button" onClick={() => void pullModel()} disabled={!pullName.trim() || pulling || !status?.available}>{pulling ? <Loader2 size={15} className="spin-slow" /> : <Download size={15} />}{pulling ? 'Pulling' : 'Pull model'}</button>
      </div>
      {pullStatus && <div className="ollama-pull-progress" role="status"><span>{pullStatus}<strong>{pullProgress}%</strong></span><i><b style={{ width: `${pullProgress}%` }} /></i></div>}

      <div className="ollama-model-list" role="list" aria-label="Installed Ollama models">
        {!loading && status?.available && !models.length && <div className="ollama-no-models">No local models installed. Pull a model above.</div>}
        {models.map(model => {
          const name = model.name || model.model || '';
          const isRunning = runningNames.has(name);
          const busy = busyModel === name;
          return (
            <article key={name} role="listitem" className={`${selectedModel === name ? 'is-selected' : ''}`}>
              <button type="button" className="ollama-model-select" onClick={() => onSelectModel(name)} aria-pressed={selectedModel === name}>
                <span className="ollama-model-icon"><Box size={17} /></span>
                <span className="ollama-model-info"><strong title={name}>{name}</strong><small>{model.details?.parameter_size || 'Local model'} · {model.details?.quantization_level || model.details?.family || 'Ollama'} · {formatBytes(model.size)}</small></span>
                <span className={`ollama-running ${isRunning ? 'is-running' : ''}`}>{isRunning ? <><Play size={11} fill="currentColor" />Loaded</> : 'Idle'}</span>
              </button>
              <div className="ollama-model-actions">
                {isRunning && <button type="button" onClick={() => void unloadModel(name)} disabled={busy} title="Unload from memory"><Unplug size={14} /></button>}
                <button type="button" className="danger" onClick={() => void deleteModel(name)} disabled={busy} title="Delete local model">{busy ? <Loader2 size={14} className="spin-slow" /> : <Trash2 size={14} />}</button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
