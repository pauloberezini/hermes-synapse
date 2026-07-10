import React, { useState, useEffect } from 'react';
import { Cpu, Shield, Activity, Globe } from 'lucide-react';
import { styles } from '../styles';

const LANGUAGES = [
  { code: 'ru', label: '🇷🇺 Russian' },
  { code: 'en', label: '🇺🇸 English' },
  { code: 'he', label: '🇮🇱 Hebrew' },
  { code: 'de', label: '🇩🇪 German' },
  { code: 'es', label: '🇪🇸 Spanish' },
  { code: 'fr', label: '🇫🇷 French' },
];

interface ConfigTabProps {
  editedModel: string;
  setEditedModel: (model: string) => void;
  editedPrompt: string;
  setEditedPrompt: (prompt: string) => void;
  isSavingConfig: boolean;
  handleSaveConfig: (e: React.FormEvent) => void;
  models: { id: string; name: string }[];
  language: string;
  onLanguageChange: (lang: string) => void;
}

export function ConfigTab({
  editedModel,
  setEditedModel,
  editedPrompt,
  setEditedPrompt,
  isSavingConfig,
  handleSaveConfig,
  models,
  language,
  onLanguageChange,
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

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>SYSTEM CORE PARAMETERS</h2>
          <p style={styles.tabSubtitle}>Configuration of personality and utilized LLM models</p>
        </div>
      </div>

      {/* ── Language Setting (instant save, no submit) ── */}
      <div className="glass-panel" style={{ ...styles.configForm, marginBottom: '16px' }}>
        <div style={styles.formGroup}>
          <label style={styles.formLabel}>
            <Globe size={16} style={{ color: '#00f0ff' }} />
            <span>Response Language</span>
          </label>
          <select
            id="language-select"
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
            style={styles.formSelect}
            className="form-input"
          >
            {LANGUAGES.map(l => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
          <span style={styles.formHelp}>
            Agents will respond in this language. Also sets voice (TTS) and microphone (STT) locale. Takes effect immediately — no save required.
          </span>
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
          <span style={styles.formHelp}>Hardcodes the character, tone of communication, response style of Jarvis, and user addressing rules.</span>
        </div>

        <button type="submit" className="btn-primary" disabled={isSavingConfig} style={{ alignSelf: 'flex-start' }}>
          <Activity size={16} />
          <span>{isSavingConfig ? 'Writing to core...' : 'Save and load prompt'}</span>
        </button>
      </form>
    </div>
  );
}
