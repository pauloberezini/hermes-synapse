import React from 'react';
import { Cpu, Shield, Activity } from 'lucide-react';
import { styles } from '../styles';

interface ConfigTabProps {
  editedModel: string;
  setEditedModel: (model: string) => void;
  editedPrompt: string;
  setEditedPrompt: (prompt: string) => void;
  isSavingConfig: boolean;
  handleSaveConfig: (e: React.FormEvent) => void;
}

export function ConfigTab({
  editedModel,
  setEditedModel,
  editedPrompt,
  setEditedPrompt,
  isSavingConfig,
  handleSaveConfig
}: ConfigTabProps) {
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
          <select 
            value={editedModel}
            onChange={(e) => setEditedModel(e.target.value)}
            style={styles.formSelect}
            className="form-input"
          >
            <option value="google/gemini-2.5-pro">google/gemini-2.5-pro (Recommended)</option>
            <option value="google/gemini-2.5-flash">google/gemini-2.5-flash</option>
            <option value="deepseek/deepseek-v4-flash">deepseek/deepseek-v4-flash</option>
            <option value="meta-llama/llama-3.3-70b-instruct">meta-llama/llama-3.3-70b-instruct</option>
            <option value="deepseek/deepseek-chat">deepseek/deepseek-chat</option>
            <option value="anthropic/claude-3.5-sonnet">anthropic/claude-3.5-sonnet</option>
          </select>
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
