import React, { useState, useEffect } from 'react';
import { Cpu, Shield, Activity, Database, Zap } from 'lucide-react';
import { styles } from '../styles';
import type { SystemConfig } from '../types';

interface ConfigTabProps {
  editedModel: string;
  setEditedModel: (model: string) => void;
  editedPrompt: string;
  setEditedPrompt: (prompt: string) => void;
  isSavingConfig: boolean;
  handleSaveConfig: (e: React.FormEvent) => void;
  models: { id: string; name: string }[];
  runtimeConfig: Partial<SystemConfig>;
  setRuntimeConfig: React.Dispatch<React.SetStateAction<Partial<SystemConfig>>>;
}

export function ConfigTab({
  editedModel,
  setEditedModel,
  editedPrompt,
  setEditedPrompt,
  isSavingConfig,
  handleSaveConfig,
  models,
  runtimeConfig,
  setRuntimeConfig
}: ConfigTabProps) {
  
  // Check if editedModel is part of the returned models list.
  // If not, treat as custom.
  const hasModel = models && models.some(m => m.id === editedModel);
  const [showCustom, setShowCustom] = useState(!hasModel && editedModel !== '');
  const [customVal, setCustomVal] = useState(!hasModel ? editedModel : '');

  useEffect(() => {
    const isModelInList = models && models.some(m => m.id === editedModel);
    if (!isModelInList && editedModel) {
      setShowCustom(true);
      setCustomVal(editedModel);
    } else {
      setShowCustom(false);
    }
  }, [editedModel, models]);

  const updateRuntime = (patch: Partial<SystemConfig>) => {
    setRuntimeConfig(prev => ({ ...prev, ...patch }));
  };

  const numberValue = (key: keyof SystemConfig, fallback: number) => {
    const value = runtimeConfig[key];
    return typeof value === 'number' ? value : fallback;
  };

  const boolValue = (key: keyof SystemConfig, fallback: boolean) => {
    const value = runtimeConfig[key];
    return typeof value === 'boolean' ? value : fallback;
  };

  const gridStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: '14px'
  };

  const compactInputStyle: React.CSSProperties = {
    width: '100%',
    backgroundColor: 'var(--bg-deep)',
    minHeight: '40px'
  };

  const toggleRowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    padding: '12px',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    background: 'rgba(255, 255, 255, 0.025)'
  };

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>SYSTEM CORE PARAMETERS</h2>
          <p style={styles.tabSubtitle}>Configuration of personality and utilized LLM models</p>
        </div>
      </div>

      <form onSubmit={handleSaveConfig} style={styles.configForm} className="glass-panel">
        <div style={styles.formGroup}>
          <label style={styles.formLabel}>
            <Cpu size={16} style={{ color: '#00f0ff' }} />
            <span>Base Intelligence Model (LLM)</span>
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <select 
              value={showCustom ? '__custom__' : editedModel}
              onChange={(e) => {
                if (e.target.value === '__custom__') {
                  setShowCustom(true);
                } else {
                  setShowCustom(false);
                  setEditedModel(e.target.value);
                }
              }}
              style={styles.formSelect}
              className="form-input"
            >
              {models && models.length > 0 ? (
                <>
                  {models.map(m => (
                    <option key={m.id} value={m.id}>{m.name || m.id}</option>
                  ))}
                  <option value="__custom__">Custom model…</option>
                </>
              ) : (
                <>
                  <option value="google/gemini-2.5-flash">google/gemini-2.5-flash</option>
                  <option value="google/gemini-2.5-pro">google/gemini-2.5-pro (Recommended)</option>
                  <option value="deepseek/deepseek-v4-flash">deepseek/deepseek-v4-flash</option>
                  <option value="meta-llama/llama-3.3-70b-instruct">meta-llama/llama-3.3-70b-instruct</option>
                  <option value="deepseek/deepseek-chat">deepseek/deepseek-chat</option>
                  <option value="anthropic/claude-3.5-sonnet">anthropic/claude-3.5-sonnet</option>
                  <option value="__custom__">Custom model…</option>
                </>
              )}
            </select>
            {showCustom && (
              <input
                type="text"
                className="form-input"
                placeholder="e.g. openai/o3-mini"
                value={customVal}
                onChange={e => {
                  setCustomVal(e.target.value);
                  setEditedModel(e.target.value);
                }}
              />
            )}
          </div>
          <span style={styles.formHelp}>Model is selected from those available on OpenRouter. Models with function calling support are recommended.</span>
        </div>

        <div style={styles.formGroup}>
          <label style={styles.formLabel}>
            <Shield size={16} style={{ color: '#00f0ff' }} />
            <span>Assistant Personality (System Prompt)</span>
          </label>
          <textarea 
            value={editedPrompt}
            onChange={(e) => setEditedPrompt(e.target.value)}
            style={styles.formTextarea}
            className="form-input"
            rows={10}
          />
          <span style={styles.formHelp}>Hardcodes the character, tone of communication, response style of Vexa, and user addressing rules.</span>
        </div>

        <div style={styles.formGroup}>
          <label style={styles.formLabel}>
            <Zap size={16} style={{ color: '#00f0ff' }} />
            <span>Speed and Memory Instructions</span>
          </label>
          <div style={gridStyle}>
            <label style={toggleRowStyle}>
              <span>
                <strong>Fast local mode</strong>
                <span style={{ ...styles.formHelp, display: 'block' }}>Short prompt, small history, tight token limits.</span>
              </span>
              <input
                type="checkbox"
                checked={boolValue('fast_mode', true)}
                onChange={e => updateRuntime({ fast_mode: e.target.checked })}
              />
            </label>

            <label style={toggleRowStyle}>
              <span>
                <strong>Long-term memory</strong>
                <span style={{ ...styles.formHelp, display: 'block' }}>Remember stable facts and preferences.</span>
              </span>
              <input
                type="checkbox"
                checked={boolValue('memory_enabled', true)}
                onChange={e => updateRuntime({ memory_enabled: e.target.checked })}
              />
            </label>

            <label style={toggleRowStyle}>
              <span>
                <strong>Auto-save memories</strong>
                <span style={{ ...styles.formHelp, display: 'block' }}>Learns from “remember...” and profile phrases.</span>
              </span>
              <input
                type="checkbox"
                checked={boolValue('memory_auto_save', true)}
                onChange={e => updateRuntime({ memory_auto_save: e.target.checked })}
              />
            </label>

            <label style={toggleRowStyle}>
              <span>
                <strong>Automatic RAG context</strong>
                <span style={{ ...styles.formHelp, display: 'block' }}>More recall from documents, slower responses.</span>
              </span>
              <input
                type="checkbox"
                checked={boolValue('auto_rag', false)}
                onChange={e => updateRuntime({ auto_rag: e.target.checked })}
              />
            </label>
          </div>

          <div style={{ ...gridStyle, marginTop: '14px' }}>
            <label style={styles.formGroup}>
              <span style={styles.formLabel}><Database size={16} style={{ color: '#00f0ff' }} />Memory facts per request</span>
              <input
                type="number"
                min={0}
                max={20}
                value={numberValue('memory_max_items', 4)}
                onChange={e => updateRuntime({ memory_max_items: Number(e.target.value) })}
                style={compactInputStyle}
                className="form-input"
              />
            </label>

            <label style={styles.formGroup}>
              <span style={styles.formLabel}>History messages</span>
              <input
                type="number"
                min={0}
                max={50}
                value={numberValue('max_history_len', 6)}
                onChange={e => updateRuntime({ max_history_len: Number(e.target.value) })}
                style={compactInputStyle}
                className="form-input"
              />
            </label>

            <label style={styles.formGroup}>
              <span style={styles.formLabel}>Max answer tokens</span>
              <input
                type="number"
                min={32}
                max={4096}
                value={numberValue('max_tokens', 256)}
                onChange={e => updateRuntime({ max_tokens: Number(e.target.value) })}
                style={compactInputStyle}
                className="form-input"
              />
            </label>

            <label style={styles.formGroup}>
              <span style={styles.formLabel}>Tool answer tokens</span>
              <input
                type="number"
                min={64}
                max={4096}
                value={numberValue('tool_max_tokens', 512)}
                onChange={e => updateRuntime({ tool_max_tokens: Number(e.target.value) })}
                style={compactInputStyle}
                className="form-input"
              />
            </label>

            <label style={styles.formGroup}>
              <span style={styles.formLabel}>Temperature</span>
              <input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={numberValue('temperature', 0.2)}
                onChange={e => updateRuntime({ temperature: Number(e.target.value) })}
                style={compactInputStyle}
                className="form-input"
              />
            </label>
          </div>
          <span style={styles.formHelp}>
            Recommended for your local 35B model: Fast mode on, Long-term memory on, Auto RAG off, 3-5 memory facts per request.
          </span>
        </div>

        <button type="submit" className="btn-primary" disabled={isSavingConfig} style={{ alignSelf: 'flex-start' }}>
          <Activity size={16} />
          <span>{isSavingConfig ? 'Writing to core...' : 'Save and load prompt'}</span>
        </button>
      </form>
    </div>
  );
}
