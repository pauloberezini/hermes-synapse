import React, { useEffect, useState } from 'react';
import { 
  MessageSquare, 
  Layers, 
  Settings, 
  Trash2, 
  Plus, 
  CheckCircle2, 
  XCircle, 
  Square, 
  Play, 
  Send
} from 'lucide-react';
import type { ChatMessage, SystemConfig } from '../types';
import { styles } from '../styles';
import { renderMarkdown } from '../utils';

// ── Constants ─────────────────────────────────────────────────────────────────

const AVAILABLE_MODELS = [
  { value: 'qwen3:8b',                               label: 'Qwen 3 8B — Ollama default ✓' },
  { value: 'google/gemini-2.5-flash',              label: 'Gemini 2.5 Flash — cloud, fast' },
  { value: 'google/gemini-2.5-pro',                label: 'Gemini 2.5 Pro — best quality' },
  { value: 'anthropic/claude-sonnet-4-5',          label: 'Claude Sonnet 4.5 — balanced' },
  { value: 'anthropic/claude-opus-4',              label: 'Claude Opus 4 — strongest' },
  { value: 'openai/gpt-4o',                        label: 'GPT-4o — well-rounded' },
  { value: 'openai/gpt-4o-mini',                   label: 'GPT-4o Mini — cheap' },
  { value: 'deepseek/deepseek-r1',                 label: 'DeepSeek R1 — reasoning' },
  { value: 'deepseek/deepseek-v3-0324',            label: 'DeepSeek V3 — fast & cheap' },
  { value: 'meta-llama/llama-3.3-70b-instruct',   label: 'Llama 3.3 70B — open weights' },
  { value: '__custom__',                           label: 'Custom model…' },
];

const modelSupportsTools = (model: string) => {
  if (!model) return true;
  const m = String(model).toLowerCase();
  return !m.includes('deepseek-r1') && !m.includes('/r1') && !m.includes('/o1') && !m.includes('o1-');
};

// Chip toggle for skills
function SkillChips({ selected, onChange, skillMap }: {
  selected: string[];
  onChange: (skills: string[]) => void;
  skillMap: Record<string, string[]>;
}) {
  const toggle = (skill: string) => {
    onChange(selected.includes(skill)
      ? selected.filter(s => s !== skill)
      : [...selected, skill]);
  };
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
      {Object.keys(skillMap).map(skill => {
        const active = selected.includes(skill);
        return (
          <button
            key={skill}
            type="button"
            onClick={() => toggle(skill)}
            title={skillMap[skill].join(', ')}
            style={{
              padding: '5px 12px',
              borderRadius: '20px',
              border: active ? '1px solid #00f0ff' : '1px solid rgba(255,255,255,0.12)',
              background: active ? 'rgba(0,240,255,0.12)' : 'rgba(255,255,255,0.03)',
              color: active ? '#00f0ff' : 'rgba(255,255,255,0.5)',
              fontSize: '0.75rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s',
              letterSpacing: '0.3px',
            }}
          >
            {skill}
          </button>
        );
      })}
    </div>
  );
}

// Temperature slider
function TempSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <input
        type="range"
        min={0} max={1} step={0.05}
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ flex: 1, accentColor: '#00f0ff' }}
      />
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '0.9rem',
        color: value < 0.3 ? '#10b981' : value > 0.7 ? '#f59e0b' : '#00f0ff',
        minWidth: '36px',
        textAlign: 'right',
      }}>
        {value.toFixed(2)}
      </span>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', minWidth: '60px' }}>
        {value < 0.3 ? '❄ precise' : value > 0.7 ? '🔥 creative' : '⚡ balanced'}
      </span>
    </div>
  );
}

// Model selector with custom option
function ModelSelect({ value, onChange, className, models }: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
  models: { id: string; name: string }[];
}) {
  const listToUse = React.useMemo(() => models && models.length > 0 ? models : [], [models]);
  const isCustom = listToUse.length > 0 
    ? !listToUse.some(m => m.id === value)
    : !AVAILABLE_MODELS.slice(0, -1).some(m => m.value === value);

  const [showCustom, setShowCustom] = useState(isCustom);
  const [customVal, setCustomVal] = useState(isCustom ? value : '');

  useEffect(() => {
    const isModelInList = listToUse.length > 0
      ? listToUse.some(m => m.id === value)
      : AVAILABLE_MODELS.some(m => m.value === value);
    if (!isModelInList && value) {
      setShowCustom(true);
      setCustomVal(value);
    } else {
      setShowCustom(false);
    }
  }, [value, listToUse]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <select
        value={showCustom ? '__custom__' : value}
        onChange={e => {
          if (e.target.value === '__custom__') {
            setShowCustom(true);
          } else {
            setShowCustom(false);
            onChange(e.target.value);
          }
        }}
        className={className || 'form-input'}
      >
        {listToUse.length > 0 ? (
          <>
            {listToUse.map(m => (
              <option key={m.id} value={m.id}>{m.name || m.id}</option>
            ))}
            <option value="__custom__">Custom model…</option>
          </>
        ) : (
          AVAILABLE_MODELS.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))
        )}
      </select>
      {showCustom && (
        <input
          type="text"
          className="form-input"
          placeholder="e.g. openai/o3-mini or mistralai/mistral-7b"
          value={customVal}
          onChange={e => { setCustomVal(e.target.value); onChange(e.target.value); }}
        />
      )}
    </div>
  );
}

// ── Props interface ────────────────────────────────────────────────────────────

interface SubagentsTabProps {
  currentChatId: string;
  subagents: any[];
  messages: ChatMessage[];
  inputValue: string;
  setInputValue: (val: string) => void;
  isSpeaking: boolean;
  setIsSpeaking: (val: boolean) => void;
  isGenerating: boolean;
  playingMsgIndex: number | null;
  setPlayingMsgIndex: (idx: number | null) => void;
  config: SystemConfig;
  isConnected: boolean;
  
  newAgentId: string;
  setNewAgentId: (val: string) => void;
  newAgentName: string;
  setNewAgentName: (val: string) => void;
  newAgentPrompt: string;
  setNewAgentPrompt: (val: string) => void;
  newAgentModel: string;
  setNewAgentModel: (val: string) => void;
  newAgentSkills: string;
  setNewAgentSkills: (val: string) => void;
  newAgentTemperature: number;
  setNewAgentTemperature: (val: number) => void;
  isCreatingAgent: boolean;
  
  editingAgentId: string;
  setEditingAgentId: (val: string) => void;
  editAgentName: string;
  setEditAgentName: (val: string) => void;
  editAgentPrompt: string;
  setEditAgentPrompt: (val: string) => void;
  editAgentModel: string;
  setEditAgentModel: (val: string) => void;
  editAgentSkills: string;
  setEditAgentSkills: (val: string) => void;
  editAgentTemperature: number;
  setEditAgentTemperature: (val: number) => void;
  isUpdatingAgent: boolean;
  
  speakText: (text: string, index: number) => void;
  handleSendMessage: (e: React.FormEvent) => void;
  selectChat: (chatId: string) => void;
  handleCreateSubagent: (e: React.FormEvent) => void;
  handleUpdateSubagent: (e: React.FormEvent) => void;
  handleDeleteSubagent: (agentId: string) => void;
  setCurrentChatId: (chatId: string) => void;
  subagentChatEndRef: React.RefObject<HTMLDivElement | null>;
  models: { id: string; name: string }[];
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SubagentsTab({
  currentChatId,
  subagents,
  messages,
  inputValue,
  setInputValue,
  isSpeaking,
  setIsSpeaking,
  isGenerating,
  playingMsgIndex,
  setPlayingMsgIndex,
  config,
  isConnected,
  newAgentId, setNewAgentId,
  newAgentName, setNewAgentName,
  newAgentPrompt, setNewAgentPrompt,
  newAgentModel, setNewAgentModel,
  newAgentSkills, setNewAgentSkills,
  newAgentTemperature, setNewAgentTemperature,
  isCreatingAgent,
  editingAgentId, setEditingAgentId,
  editAgentName, setEditAgentName,
  editAgentPrompt, setEditAgentPrompt,
  editAgentModel, setEditAgentModel,
  editAgentSkills, setEditAgentSkills,
  editAgentTemperature, setEditAgentTemperature,
  isUpdatingAgent,
  speakText,
  handleSendMessage,
  selectChat,
  handleCreateSubagent,
  handleUpdateSubagent,
  handleDeleteSubagent,
  setCurrentChatId,
  subagentChatEndRef,
  models,
}: SubagentsTabProps) {

  const [skillMap, setSkillMap] = useState<Record<string, string[]>>({});
  const messageContent = (msg: ChatMessage) => {
    if ((msg.content || '').trim()) return msg.content;
    return msg.role === 'assistant'
      ? 'Пустой ответ модели. Попробуйте повторить запрос или уточнить формулировку.'
      : '';
  };

  useEffect(() => {
    const token = localStorage.getItem('jarvis_auth_token');
    fetch('/api/skills', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.json())
      .then(data => setSkillMap(data))
      .catch(() => {});
  }, []);

  // helpers to convert comma-string <-> string[]
  const parseSkills = (s: string) => s ? s.split(',').map(x => x.trim()).filter(Boolean) : [];
  const joinSkills = (arr: string[]) => arr.join(',');

  const formSection = (label: string, children: React.ReactNode) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>{label}</label>
      {children}
    </div>
  );

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>SUB-AGENT FACTORY</h2>
          <p style={styles.tabSubtitle}>Creation and coordination of specialized virtual assistants</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', height: 'calc(100% - 60px)', flex: 1, minHeight: 0 }} className="subagents-layout">
        {/* Sidebar */}
        <div style={{ width: '260px', display: 'flex', flexDirection: 'column', gap: '10px', borderRight: '1px solid rgba(255,255,255,0.05)', paddingRight: '15px', flexShrink: 0 }}>
          <button
            onClick={() => selectChat('dashboard')}
            style={{
              display: 'flex', alignItems: 'center', gap: '10px', padding: '10px',
              borderRadius: '8px',
              border: currentChatId === 'dashboard' ? '1px solid rgba(0,240,255,0.4)' : '1px solid rgba(255,255,255,0.05)',
              backgroundColor: currentChatId === 'dashboard' ? 'rgba(0,240,255,0.05)' : 'rgba(6, 9, 19, 0.6)',
              color: '#fff', textAlign: 'left', cursor: 'pointer', width: '100%', transition: 'all 0.2s'
            }}
          >
            <MessageSquare size={16} style={{ color: 'var(--accent-cyan)' }} />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Vexa Main</span>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>Personal Assistant</span>
            </div>
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', marginBottom: '5px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '1px' }}>MY SUB-AGENTS</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto', paddingRight: '4px' }}>
            {subagents.map(agent => (
              <div
                key={agent.id}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 10px', borderRadius: '8px',
                  border: currentChatId === agent.id ? '1px solid rgba(0,240,255,0.4)' : '1px solid rgba(255,255,255,0.03)',
                  backgroundColor: currentChatId === agent.id ? 'rgba(0,240,255,0.04)' : 'rgba(255,255,255,0.01)',
                  cursor: 'pointer', transition: 'all 0.2s'
                }}
                onClick={() => selectChat(agent.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                  <Layers size={14} style={{ color: 'var(--accent-orange)', flexShrink: 0 }} />
                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{agent.name}</span>
                    <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '4px' }}>
                      <span>{agent.model.split('/').pop()}</span>
                      {agent.skills && <span style={{ color: 'rgba(0,240,255,0.5)' }}>· {agent.skills.split(',').length} skill{agent.skills.split(',').length !== 1 ? 's' : ''}</span>}
                      {!modelSupportsTools(agent.model) && (
                        <span style={{ color: '#f59e0b', padding: '0px 4px', borderRadius: '3px', backgroundColor: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)', fontSize: '0.55rem', fontWeight: 600, letterSpacing: '0.3px' }}>
                          NO TOOLS
                        </span>
                      )}
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingAgentId(agent.id);
                      setEditAgentName(agent.name);
                      setEditAgentPrompt(agent.system_prompt);
                      setEditAgentModel(agent.model);
                      setEditAgentSkills(agent.skills || '');
                      setEditAgentTemperature(agent.temperature ?? 0.7);
                      setCurrentChatId('__edit__');
                    }}
                    style={{ background: 'none', border: 'none', color: 'rgba(0,240,255,0.6)', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', borderRadius: '4px' }}
                    title="Edit sub-agent"
                  >
                    <Settings size={12} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteSubagent(agent.id); }}
                    style={{ background: 'none', border: 'none', color: 'rgba(239,68,68,0.6)', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', borderRadius: '4px' }}
                    title="Delete sub-agent"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={() => setCurrentChatId('__create__')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
              padding: '10px', borderRadius: '8px', border: '1px dashed rgba(0,240,255,0.3)',
              backgroundColor: currentChatId === '__create__' ? 'rgba(0,240,255,0.05)' : 'transparent',
              color: 'var(--accent-cyan)', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer', marginTop: '10px', transition: 'all 0.2s'
            }}
          >
            <Plus size={14} />
            <span>Create Agent</span>
          </button>
        </div>

        {/* Dynamic Content Pane */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
          {currentChatId === '__create__' ? (
            <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px', height: '100%', overflowY: 'auto' }} className="glass-panel">
              <div>
                <h3 style={{ fontSize: '1.2rem', color: '#fff', fontWeight: 600, marginBottom: '4px' }} className="glow-text-cyan">CREATE NEW SUB-AGENT</h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Configure a specialized virtual assistant to solve your tasks</p>
              </div>

              <form onSubmit={handleCreateSubagent} style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '680px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  {formSection('Unique ID (latin, no spaces)',
                    <input type="text" value={newAgentId} onChange={e => setNewAgentId(e.target.value.replace(/[^a-zA-Z0-9_-]/g, ''))} placeholder="e.g. sports_analyst" className="form-input" required />
                  )}
                  {formSection('Sub-agent name',
                    <input type="text" value={newAgentName} onChange={e => setNewAgentName(e.target.value)} placeholder="e.g. Sports Betting Analyst" className="form-input" required />
                  )}
                </div>

                {formSection('Instructions / System Prompt',
                  <textarea value={newAgentPrompt} onChange={e => setNewAgentPrompt(e.target.value)} placeholder="Describe character, knowledge, tone, and instructions…" className="form-input" rows={7} required />
                )}

                {formSection('AI Model',
                  <>
                    <ModelSelect value={newAgentModel} onChange={setNewAgentModel} models={models} />
                    {!modelSupportsTools(newAgentModel) && (
                      <span style={{ fontSize: '0.75rem', color: '#f59e0b', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        ⚠️ This reasoning model does not support direct tool calling. Jarvis will run research/code tools on its behalf if scheduled in the query plan.
                      </span>
                    )}
                  </>
                )}

                {formSection(
                  `Skills & Tool Access${newAgentSkills ? ` — ${parseSkills(newAgentSkills).length} selected` : ' — none (safe defaults)'}`,
                  Object.keys(skillMap).length > 0
                    ? <SkillChips selected={parseSkills(newAgentSkills)} onChange={arr => setNewAgentSkills(joinSkills(arr))} skillMap={skillMap} />
                    : <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Loading skills…</span>
                )}

                {formSection(`Temperature — ${newAgentTemperature.toFixed(2)}`,
                  <TempSlider value={newAgentTemperature} onChange={setNewAgentTemperature} />
                )}

                <button type="submit" className="btn-primary" disabled={isCreatingAgent} style={{ alignSelf: 'flex-start', marginTop: '8px' }}>
                  <Plus size={16} />
                  <span>{isCreatingAgent ? 'Creating…' : 'Initialize Sub-agent'}</span>
                </button>
              </form>
            </div>
          ) : currentChatId === '__edit__' ? (
            <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px', height: '100%', overflowY: 'auto' }} className="glass-panel">
              <div>
                <h3 style={{ fontSize: '1.2rem', color: '#fff', fontWeight: 600, marginBottom: '4px' }} className="glow-text-cyan">EDIT SUB-AGENT SETTINGS</h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Modify configuration for sub-agent <strong>{editingAgentId}</strong></p>
              </div>

              <form onSubmit={handleUpdateSubagent} style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '680px' }}>
                {formSection('Sub-agent ID (read-only)',
                  <input type="text" value={editingAgentId} disabled className="form-input" style={{ opacity: 0.6, cursor: 'not-allowed' }} />
                )}

                {formSection('Sub-agent name',
                  <input type="text" value={editAgentName} onChange={e => setEditAgentName(e.target.value)} placeholder="e.g. Sports Betting Analyst" className="form-input" required />
                )}

                {formSection('Instructions / System Prompt',
                  <textarea value={editAgentPrompt} onChange={e => setEditAgentPrompt(e.target.value)} placeholder="Describe character, knowledge, tone, and instructions…" className="form-input" rows={7} required />
                )}

                {formSection('AI Model',
                  <>
                    <ModelSelect value={editAgentModel} onChange={setEditAgentModel} models={models} />
                    {!modelSupportsTools(editAgentModel) && (
                      <span style={{ fontSize: '0.75rem', color: '#f59e0b', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        ⚠️ This reasoning model does not support direct tool calling. Jarvis will run research/code tools on its behalf if scheduled in the query plan.
                      </span>
                    )}
                  </>
                )}

                {formSection(
                  `Skills & Tool Access${editAgentSkills ? ` — ${parseSkills(editAgentSkills).length} selected` : ' — none (safe defaults)'}`,
                  Object.keys(skillMap).length > 0
                    ? <SkillChips selected={parseSkills(editAgentSkills)} onChange={arr => setEditAgentSkills(joinSkills(arr))} skillMap={skillMap} />
                    : <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Loading skills…</span>
                )}

                {formSection(`Temperature — ${editAgentTemperature.toFixed(2)}`,
                  <TempSlider value={editAgentTemperature} onChange={setEditAgentTemperature} />
                )}

                <div style={{ display: 'flex', gap: '10px' }}>
                  <button type="submit" className="btn-primary" disabled={isUpdatingAgent} style={{ alignSelf: 'flex-start', marginTop: '8px' }}>
                    <CheckCircle2 size={16} />
                    <span>{isUpdatingAgent ? 'Saving…' : 'Save Changes'}</span>
                  </button>
                  <button type="button" onClick={() => selectChat(editingAgentId)}
                    style={{ alignSelf: 'flex-start', marginTop: '8px', backgroundColor: 'rgba(255,255,255,0.05)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0px 16px', height: '42px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <XCircle size={16} />
                    <span>Cancel</span>
                  </button>
                </div>
              </form>
            </div>
          ) : (
            /* Chat Pane */
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
              <div style={{ ...styles.chatArea, flex: 1, marginBottom: '15px' }} className="glass-panel">
                <div style={styles.chatScroller}>
                  {messages.map((msg, index) => (
                    <div key={index} style={{ ...styles.msgBubbleWrapper, justifyContent: msg.role === 'user' ? 'flex-end' : (msg.role === 'system' ? 'center' : 'flex-start') }}>
                      {msg.role === 'system' ? (
                        <div style={styles.systemMsg}>{messageContent(msg)}</div>
                      ) : (
                        <div style={{ ...styles.msgBubble, backgroundColor: msg.role === 'user' ? 'rgba(255, 159, 0, 0.12)' : 'rgba(0, 240, 255, 0.05)', borderColor: msg.role === 'user' ? 'rgba(255, 159, 0, 0.3)' : 'rgba(0, 240, 255, 0.2)', alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                          <div style={styles.msgHeader}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={msg.role === 'user' ? styles.userLabel : styles.assistantLabel}>
                                {msg.role === 'user' ? 'CREATOR' : (currentChatId === 'dashboard' ? 'VEXA' : (subagents.find(a => a.id === currentChatId)?.name.toUpperCase() || 'SUB-AGENT'))}
                              </span>
                              {msg.role === 'assistant' && msg.cost_usd !== undefined && msg.cost_usd > 0 && (
                                <span style={{ fontSize: '0.7rem', color: 'var(--success)', backgroundColor: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '1px 5px', borderRadius: '4px', fontFamily: 'var(--font-mono)', fontWeight: 600, letterSpacing: '0.5px' }}>
                                  ${msg.cost_usd.toFixed(5)}
                                </span>
                              )}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              {msg.role === 'assistant' && (
                                <button onClick={() => speakText(messageContent(msg), index)} title={playingMsgIndex === index ? 'Stop' : 'Play voice'}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', borderRadius: '4px', color: playingMsgIndex === index ? '#ff9f00' : 'rgba(0, 240, 255, 0.45)', display: 'flex', alignItems: 'center', transition: 'color 0.2s, transform 0.15s', transform: playingMsgIndex === index ? 'scale(1.15)' : 'scale(1)' }}>
                                  {playingMsgIndex === index ? <Square size={12} fill="currentColor" /> : <Play size={12} fill="currentColor" />}
                                </button>
                              )}
                            </div>
                          </div>
                          <div style={styles.msgText}>{renderMarkdown(messageContent(msg))}</div>
                        </div>
                      )}
                    </div>
                  ))}

                  {isGenerating && (
                    <div className="hud-container">
                      <div className="hud-scanner">
                        <div className="hud-ring-outer" />
                        <div className="hud-ring-inner" />
                        <div className="hud-core" />
                      </div>
                      <div className="hud-telemetry">
                        <span className="hud-title">COGNITIVE COMPILING...</span>
                        <span className="hud-status">ENGAGING NEURAL ORCHESTRATION GRAPH [MODEL: {
                          currentChatId === 'dashboard'
                            ? (config?.model?.split('/').pop() || 'GEMINI')
                            : (subagents.find(a => a.id === currentChatId)?.model.split('/').pop() || 'GEMINI')
                        }]</span>
                        <div className="hud-bar-wrapper"><div className="hud-bar-fill" /></div>
                      </div>
                    </div>
                  )}
                  <div ref={subagentChatEndRef} />
                </div>
              </div>

              <form onSubmit={handleSendMessage} style={styles.chatInputRow}>
                <textarea
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }}
                  placeholder={`Request for assistant "${currentChatId === 'dashboard' ? 'Vexa' : (subagents.find(a => a.id === currentChatId)?.name || 'Sub-agent')}"...`}
                  style={styles.chatInput}
                  className="form-input"
                  disabled={!isConnected}
                  rows={1}
                />
                {isSpeaking && (
                  <button type="button" onClick={() => { window.speechSynthesis?.cancel(); setIsSpeaking(false); setPlayingMsgIndex(null); }}
                    className="btn-primary" style={{ border: '1px solid rgba(239, 68, 68, 0.4)', color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.05)' }}>
                    <Square size={14} fill="currentColor" />
                    <span>Interrupt speech</span>
                  </button>
                )}
                <button type="submit" className="btn-primary" disabled={!isConnected || !inputValue.trim()}>
                  <Send size={16} />
                  <span>Send</span>
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
