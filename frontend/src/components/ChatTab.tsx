import React from 'react';
import { 
  Mic, 
  MicOff, 
  Volume2, 
  VolumeX, 
  Bell,
  BellOff,
  Trash2, 
  Plus, 
  MessageSquare, 
  Paperclip, 
  Square, 
  Play, 
  Pause,
  Send,
  MoreVertical,
  Archive,
  Copy,
  Cpu,
  Lock,
  Edit2,
  FileText,
  Download,
  Clock,
  Zap,
  Maximize2,
  Check,
  X as XIcon
} from 'lucide-react';
import type { ChatMessage, SystemConfig, ChatSession } from '../types';
import { styles } from '../styles';
import { renderMarkdown, formatMessageTimestamp } from '../utils';
import { AgentSelect } from './AgentSelect';

interface ChatTabProps {
  currentChatId: string;
  chatSessions: ChatSession[];
  messages: ChatMessage[];
  inputValue: string;
  setInputValue: (val: string) => void;
  isSpeaking: boolean;
  setIsSpeaking: (val: boolean) => void;
  micState: 'off' | 'listening' | 'capturing';
  micEnabled: boolean;
  setMicEnabled: (val: boolean | ((prev: boolean) => boolean)) => void;
  isTTSEnabled: boolean;
  setIsTTSEnabled: (val: boolean | ((prev: boolean) => boolean)) => void;
  timerSoundEnabled?: boolean;
  setTimerSoundEnabled?: (val: boolean | ((prev: boolean) => boolean)) => void;
  isGenerating: boolean;
  playingMsgIndex: number | null;
  setPlayingMsgIndex: (idx: number | null) => void;
  config: SystemConfig;
  isConnected: boolean;
  isUploading: boolean;
  // File attachment for chat context
  attachedFile: { name: string; content: string; type?: string; pages?: number; truncated?: boolean } | null;
  setAttachedFile: (file: { name: string; content: string; type?: string; pages?: number; truncated?: boolean } | null) => void;
  handleChatFileAttach: (e: React.ChangeEvent<HTMLInputElement>) => void;

  speakText: (text: string, index: number) => void;
  handleClearChat: () => void;
  handleSendMessage: (e: React.FormEvent) => void;
  selectChat: (chatId: string) => void;
  handleCreateNewSession: () => void;
  fetchChatSessions: () => void;
  getSessionLabel: (sessionId: string) => string;
  mainChatEndRef: React.RefObject<HTMLDivElement | null>;
  subagents: any[];
  handleSetSessionAgent: (sessionId: string, agentId: string) => void;
  fetchWithAuth: (url: string, options?: RequestInit) => Promise<Response>;
}

const detectMissingEnvKey = (content: string): string | null => {
  const match = content.match(/Set `([A-Z0-9_]+)` in your\.env/);
  return match ? match[1] : null;
};

interface MissingEnvConfigCardProps {
  messageIndex: number;
  envKey: string;
  onSave: (value: string) => Promise<boolean>;
}

function MissingEnvConfigCard({ messageIndex, envKey, onSave }: MissingEnvConfigCardProps) {
  const [inputValue, setInputValue] = React.useState('');
  const [status, setStatus] = React.useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const handleSave = async () => {
    if (!inputValue.trim()) return;
    setStatus('saving');
    const ok = await onSave(inputValue.trim());
    setStatus(ok ? 'saved' : 'error');
  };

  return (
    <div style={{
      marginTop: '10px',
      padding: '12px 14px',
      background: 'rgba(255, 159, 0, 0.07)',
      border: '1px solid rgba(255, 159, 0, 0.3)',
      borderRadius: '8px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', color: '#ff9f00', fontWeight: 600 }}>
        <span>🔑</span>
        <span>Configure missing API key</span>
      </div>
      <div style={{ fontSize: '0.73rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
        <code style={{ color: '#ff9f00' }}>{envKey}</code> is not set. Enter it below to enable this skill for this session.
      </div>
      {status === 'saved' ? (
        <div style={{ fontSize: '0.78rem', color: 'var(--success)', fontWeight: 600 }}>
          ✓ Key saved for this session. Try your request again.
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            id={`env-key-input-${messageIndex}`}
            type="password"
            placeholder={`Enter ${envKey}…`}
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            style={{
              flex: 1,
              padding: '6px 10px',
              background: 'rgba(0,0,0,0.3)',
              border: '1px solid rgba(255,159,0,0.35)',
              borderRadius: '6px',
              color: 'var(--text-primary)',
              fontSize: '0.78rem',
              fontFamily: 'var(--font-mono)',
              outline: 'none'
            }}
          />
          <button
            id={`env-key-save-${messageIndex}`}
            onClick={handleSave}
            disabled={status === 'saving' || !inputValue.trim()}
            style={{
              padding: '6px 14px',
              background: 'rgba(255,159,0,0.18)',
              border: '1px solid rgba(255,159,0,0.4)',
              borderRadius: '6px',
              color: '#ff9f00',
              fontSize: '0.78rem',
              fontWeight: 600,
              cursor: 'pointer',
              opacity: (status === 'saving' || !inputValue.trim()) ? 0.5 : 1
            }}
          >
            {status === 'saving' ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
      {status === 'error' && (
        <div style={{ fontSize: '0.73rem', color: 'var(--error)' }}>
          Failed to save. Check your connection or add it manually to .env.
        </div>
      )}
    </div>
  );
}


export function ChatTab({
  currentChatId,
  chatSessions,
  messages,
  inputValue,
  setInputValue,
  isSpeaking,
  setIsSpeaking,
  micState,
  micEnabled,
  setMicEnabled,
  isTTSEnabled,
  setIsTTSEnabled,
  timerSoundEnabled = false,
  setTimerSoundEnabled,
  isGenerating,

  playingMsgIndex,
  setPlayingMsgIndex,
  config,
  isConnected,
  isUploading,
  attachedFile,
  setAttachedFile,
  handleChatFileAttach,
  speakText,
  handleClearChat,
  handleSendMessage,
  selectChat,
  handleCreateNewSession,
  fetchChatSessions,
  getSessionLabel,
  mainChatEndRef,
  subagents,
  handleSetSessionAgent,
  fetchWithAuth
}: ChatTabProps) {
  const [activeMenu, setActiveMenu] = React.useState<string | null>(null);
  const [editingSessionId, setEditingSessionId] = React.useState<string | null>(null);
  const [editingSessionTitle, setEditingSessionTitle] = React.useState<string>('');



  const handleRenameSession = async (sessionId: string, newTitle: string) => {
    if (!newTitle.trim()) return;
    try {
      const res = await fetchWithAuth(`http://localhost:8000/api/history/${sessionId}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() })
      });
      if (res.ok) {
        fetchChatSessions();
      }
    } catch (err) {
      console.error('Error renaming session:', err);
    }
  };

  const handleExportTrajectory = (sessionId: string, format: string = 'sharegpt', extension: string = 'jsonl') => {
    const url = `http://localhost:8000/api/sessions/${sessionId}/export-trajectory?format=${format}&extension=${extension}&download=true`;
    window.open(url, '_blank');
  };

  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const [fullscreenMsg, setFullscreenMsg] = React.useState<ChatMessage | null>(null);
  const [copiedFullscreen, setCopiedFullscreen] = React.useState(false);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && fullscreenMsg) {
        setFullscreenMsg(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [fullscreenMsg]);

  // Auto-resize textarea as content changes
  React.useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [inputValue]);

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <h2 className="glow-text-cyan" style={styles.tabTitle}>COMMUNICATION LINK</h2>
            <p style={styles.tabSubtitle}>Voice and text control stream for the assistant</p>
          </div>

          {/* Active Session Metadata Group */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255, 255, 255, 0.03)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>SESSION:</span>
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                {currentChatId === 'dashboard' ? 'Main Terminal' : getSessionLabel(currentChatId)}
              </span>
            </div>

            {/* Active Session Orchestrator Selector */}
            {currentChatId !== 'dashboard' && !subagents.some(a => a.id === currentChatId) && (
              <AgentSelect
                labelPrefix="ORCHESTRATOR:"
                value={chatSessions.find(s => s.id === currentChatId)?.agent_id || 'jarvis'}
                onChange={(agentId) => handleSetSessionAgent(currentChatId, agentId)}
                agents={[
                  { id: 'jarvis', name: 'Jarvis (Main)', agent_type: 'orchestrator' },
                  ...(Array.isArray(subagents) ? subagents : [])
                ]}
              />
            )}

            {/* TTS speaking pulse indicator */}
            {isSpeaking && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0, 240, 255, 0.08)', padding: '5px 10px', borderRadius: '6px', border: '1px solid rgba(0, 240, 255, 0.2)' }}>
                <span className="pulse-dot" style={{ width: 8, height: 8 }} />
                <span style={{ fontSize: '0.72rem', color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>SPEAKING</span>
              </div>
            )}
            {/* Mic state indicator */}
            {micState === 'listening' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0, 240, 255, 0.08)', padding: '5px 10px', borderRadius: '6px', border: '1px solid rgba(0, 240, 255, 0.2)' }}>
                <span className="pulse-dot" style={{ width: 8, height: 8, background: '#00f0ff', boxShadow: '0 0 6px #00f0ff' }} />
                <span style={{ fontSize: '0.72rem', color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>MIC LISTENING</span>
              </div>
            )}
            {micState === 'capturing' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255, 159, 0, 0.1)', padding: '5px 10px', borderRadius: '6px', border: '1px solid rgba(255, 159, 0, 0.3)' }}>
                <span className="pulse-dot" style={{ width: 8, height: 8, background: '#ff9f00', boxShadow: '0 0 8px #ff9f00' }} />
                <span style={{ fontSize: '0.72rem', color: '#ff9f00', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>REC...</span>
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Mic toggle button */}
          <button
            id="mic-toggle-btn"
            onClick={() => setMicEnabled(v => !v)}
            className="btn-primary"
            title={micEnabled ? 'Turn off microphone' : 'Turn on microphone (say "Jarvis")'}
            style={{
              padding: '6px 12px',
              border: micState === 'capturing'
                ? '1px solid rgba(255,159,0,0.6)'
                : micEnabled
                  ? '1px solid rgba(0,240,255,0.4)'
                  : '1px solid rgba(255,255,255,0.15)',
              color: micState === 'capturing' ? '#ff9f00' : micEnabled ? 'var(--accent-cyan)' : 'var(--text-dim)',
              boxShadow: micState === 'capturing'
                ? '0 0 10px rgba(255,159,0,0.3)'
                : micEnabled ? '0 0 8px rgba(0,240,255,0.2)' : 'none',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem'
            }}
          >
            {micEnabled ? <Mic size={14} /> : <MicOff size={14} />}
            <span>{micState === 'capturing' ? 'REC...' : micEnabled ? 'Mic ON' : 'Mic OFF'}</span>
          </button>
          {/* TTS toggle */}
          <button
            id="tts-toggle-btn"
            onClick={() => {
              window.speechSynthesis?.cancel();
              setIsSpeaking(false);
              setPlayingMsgIndex?.(null);
              setIsTTSEnabled(v => !v);
            }}
            className="btn-primary"
            title={isTTSEnabled ? 'Turn off voice' : 'Turn on voice'}
            style={{
              padding: '6px 12px',
              border: isTTSEnabled
                ? '1px solid rgba(0, 240, 255, 0.4)'
                : '1px solid rgba(255,255,255,0.15)',
              color: isTTSEnabled ? 'var(--accent-cyan)' : 'var(--text-dim)',
              boxShadow: isTTSEnabled ? '0 0 8px rgba(0,240,255,0.2)' : 'none',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem'
            }}
          >
            {isTTSEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
            <span>{isTTSEnabled ? 'Voice ON' : 'Voice OFF'}</span>
          </button>
          {/* Timer Alarm Sound Toggle */}
          <button
            id="timer-sound-toggle-btn"
            onClick={() => setTimerSoundEnabled && setTimerSoundEnabled(v => !v)}
            className="btn-primary"
            title={timerSoundEnabled ? 'Turn off timer alarm sound' : 'Turn on timer alarm sound'}
            style={{
              padding: '6px 12px',
              border: timerSoundEnabled
                ? '1px solid rgba(0, 240, 255, 0.4)'
                : '1px solid rgba(255,255,255,0.15)',
              color: timerSoundEnabled ? 'var(--accent-cyan)' : 'var(--text-dim)',
              boxShadow: timerSoundEnabled ? '0 0 8px rgba(0,240,255,0.2)' : 'none',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem'
            }}
          >
            {timerSoundEnabled ? <Bell size={14} /> : <BellOff size={14} />}
            <span>{timerSoundEnabled ? 'Sound ON' : 'Sound OFF'}</span>
          </button>

          <button onClick={handleClearChat} className="btn-primary" style={{ padding: '6px 12px', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem' }}>
            <Trash2 size={14} />
            <span>Clear Chat</span>
          </button>
        </div>
      </div>

      {/* Split layout: sessions sidebar on the left, chat workspace on the right */}
      <div style={{ display: 'flex', gap: '20px', flex: 1, minHeight: 0 }} className="chat-layout">
        {/* Sessions Sidebar */}
        <div style={{
          width: '260px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          borderRight: '1px solid rgba(255,255,255,0.05)',
          paddingRight: '15px',
          flexShrink: 0,
          height: '100%',
          minHeight: 0
        }}>
          <button 
            onClick={handleCreateNewSession}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              padding: '10px 14px',
              borderRadius: '8px',
              border: '1px solid rgba(0, 240, 255, 0.3)',
              background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.15) 0%, rgba(0, 240, 255, 0.02) 100%)',
              color: '#fff',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
              transition: 'all 0.2s',
              width: '100%',
              boxShadow: '0 0 10px rgba(0, 240, 255, 0.08)'
            }}
          >
            <Plus size={16} style={{ color: 'var(--accent-cyan)' }} />
            <span>New Chat</span>
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', marginBottom: '5px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '1px' }}>ACTIVE SESSIONS</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto', paddingRight: '4px' }}>
            {(Array.isArray(chatSessions) ? chatSessions : []).map(session => {
              const s = session.id;
              const isActive = currentChatId === s;
              const label = session.title || getSessionLabel(s);
              const isDashboard = s === 'dashboard';
              const isScheduled = Boolean(session.is_scheduled || s.startsWith('task_'));
              const scheduleInfo = session.schedule_info || {};
              const taskStatus = scheduleInfo.status || 'running';
              const taskType = session.schedule_type || scheduleInfo.type || 'task';

              let iconColor = isActive ? 'var(--accent-cyan)' : 'var(--text-dim)';
              if (isScheduled) {
                if (taskStatus === 'paused') iconColor = '#ff9f00';
                else if (taskStatus === 'completed') iconColor = '#10b981';
                else iconColor = 'var(--accent-cyan)';
              }

              return (
                <div 
                  key={s}
                  onMouseLeave={() => setActiveMenu(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: isDashboard ? '10px 12px' : '8px 12px',
                    borderRadius: '8px',
                    border: isDashboard 
                      ? (isActive ? '1px solid rgba(0, 240, 255, 0.7)' : '1px solid rgba(0, 240, 255, 0.25)')
                      : isScheduled
                        ? (isActive ? '1px solid rgba(0, 240, 255, 0.6)' : '1px solid rgba(0, 240, 255, 0.15)')
                        : (isActive ? '1px solid rgba(0, 240, 255, 0.4)' : '1px solid rgba(255, 255, 255, 0.03)'),
                    backgroundColor: isDashboard
                      ? (isActive ? 'rgba(0, 240, 255, 0.08)' : 'rgba(0, 240, 255, 0.02)')
                      : isScheduled
                        ? (isActive ? 'rgba(0, 240, 255, 0.06)' : 'rgba(0, 240, 255, 0.015)')
                        : (isActive ? 'rgba(0, 240, 255, 0.04)' : 'rgba(255, 255, 255, 0.01)'),
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    position: 'relative',
                    boxShadow: isDashboard ? '0 0 10px rgba(0, 240, 255, 0.04)' : 'none'
                  }}
                  onClick={() => {
                    if (editingSessionId !== s) {
                      selectChat(s);
                    }
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                    {isDashboard ? (
                      <Cpu size={14} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    ) : isScheduled ? (
                      <Clock size={14} style={{ color: iconColor, flexShrink: 0 }} />
                    ) : (
                      <MessageSquare size={14} style={{ color: isActive ? 'var(--accent-cyan)' : 'var(--text-dim)', flexShrink: 0 }} />
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', minWidth: 0, width: '100%' }}>
                        {editingSessionId === s ? (
                          <input
                            value={editingSessionTitle}
                            onChange={(e) => setEditingSessionTitle(e.target.value)}
                            onKeyDown={async (e) => {
                              if (e.key === 'Enter') {
                                await handleRenameSession(s, editingSessionTitle);
                                setEditingSessionId(null);
                              } else if (e.key === 'Escape') {
                                setEditingSessionId(null);
                              }
                            }}
                            onBlur={async () => {
                              await handleRenameSession(s, editingSessionTitle);
                              setEditingSessionId(null);
                            }}
                            autoFocus
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              fontSize: '0.8rem',
                              background: 'rgba(0, 0, 0, 0.4)',
                              border: '1px solid rgba(0, 240, 255, 0.5)',
                              borderRadius: '4px',
                              color: '#fff',
                              padding: '2px 6px',
                              width: '100%',
                              outline: 'none',
                            }}
                          />
                        ) : (
                          <span style={{ fontSize: '0.8rem', fontWeight: (isActive || isDashboard || isScheduled) ? 600 : 500, color: (isActive || isDashboard) ? '#fff' : 'var(--text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {label}
                          </span>
                        )}
                        {isDashboard && (
                          <span title="Protected core session" style={{ display: 'flex', alignItems: 'center' }}>
                            <Lock size={10} style={{ color: 'rgba(0, 240, 255, 0.4)', flexShrink: 0 }} />
                          </span>
                        )}
                        {isScheduled && !editingSessionId && (
                          <span style={{
                            fontSize: '0.55rem',
                            fontWeight: 700,
                            padding: '1px 4px',
                            borderRadius: '3px',
                            background: taskStatus === 'paused' ? 'rgba(255,159,0,0.15)' : taskStatus === 'completed' ? 'rgba(16,185,129,0.15)' : 'rgba(0,240,255,0.15)',
                            color: taskStatus === 'paused' ? '#ff9f00' : taskStatus === 'completed' ? '#10b981' : 'var(--accent-cyan)',
                            border: `1px solid ${taskStatus === 'paused' ? 'rgba(255,159,0,0.3)' : taskStatus === 'completed' ? 'rgba(16,185,129,0.3)' : 'rgba(0,240,255,0.3)'}`,
                            flexShrink: 0
                          }}>
                            {taskType.toUpperCase()}
                          </span>
                        )}
                      </div>
                      {isDashboard ? (
                        <span style={{ fontSize: '0.6rem', color: 'rgba(0, 240, 255, 0.65)', fontWeight: 500, letterSpacing: '0.5px' }}>MAIN ORCHESTRATOR</span>
                      ) : isScheduled ? (
                        <span style={{ fontSize: '0.62rem', color: taskStatus === 'paused' ? '#ff9f00' : taskStatus === 'completed' ? '#10b981' : 'var(--text-dim)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {taskStatus.toUpperCase()} {scheduleInfo.interval_hours ? `• Every ${scheduleInfo.interval_hours}h` : scheduleInfo.duration ? `• ${scheduleInfo.duration}s` : ''}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div style={{ position: 'relative' }}>
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveMenu(activeMenu === s ? null : s);
                      }}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--text-dim)',
                        cursor: 'pointer',
                        padding: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        borderRadius: '4px'
                      }}
                      title="Session options"
                    >
                      <MoreVertical size={14} />
                    </button>
                    
                    {activeMenu === s && (
                      <div style={{
                        position: 'absolute',
                        right: '0',
                        top: '100%',
                        marginTop: '4px',
                        background: 'rgba(15, 20, 25, 0.95)',
                        border: '1px solid rgba(0, 240, 255, 0.2)',
                        borderRadius: '8px',
                        padding: '4px',
                        zIndex: 100,
                        display: 'flex',
                        flexDirection: 'column',
                        minWidth: '120px',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
                      }}>
                        {!isDashboard && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setActiveMenu(null);
                              setEditingSessionId(s);
                              setEditingSessionTitle(label);
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                            style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: '#fff', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                          ><Edit2 size={12}/> Rename</button>
                        )}
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            setActiveMenu(null);
                            try {
                              const res = await fetchWithAuth(`http://localhost:8000/api/history/${s}/fork`, {
                                method: 'POST'
                              });
                              if (res.ok) {
                                const data = await res.json();
                                fetchChatSessions();
                                setTimeout(() => selectChat(data.new_session_id), 100);
                              }
                            } catch(err) { console.error(err); }
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                          onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                          style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: '#fff', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                        ><Copy size={12}/> Fork</button>
                        
                        {s === 'dashboard' ? (
                          <>
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                setActiveMenu(null);
                                if (window.confirm('Sir, are you sure you want to completely purge the history of the Main Terminal?')) {
                                  try {
                                    const res = await fetchWithAuth(`http://localhost:8000/api/history/dashboard`, {
                                      method: 'DELETE'
                                    });
                                    if (res.ok) {
                                      selectChat('dashboard');
                                    }
                                  } catch(err) { console.error(err); }
                                }
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(239,68,68,0.1)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: 'rgba(239,68,68,0.9)', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                            ><Trash2 size={12}/> Purge</button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveMenu(null);
                                handleExportTrajectory(s, 'sharegpt', 'jsonl');
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: '#00f0ff', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                            ><Download size={12}/> Export (ShareGPT)</button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveMenu(null);
                                handleExportTrajectory(s, 'sharegpt', 'jsonl');
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: '#00f0ff', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                            ><Download size={12}/> Export (ShareGPT)</button>
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                setActiveMenu(null);
                                if (window.confirm(`Archive session "${label}"?`)) {
                                  try {
                                    const res = await fetchWithAuth(`http://localhost:8000/api/history/${s}/archive`, {
                                      method: 'POST'
                                    });
                                    if (res.ok) {
                                      if (currentChatId === s) selectChat('dashboard');
                                      fetchChatSessions();
                                    }
                                  } catch(err) { console.error(err); }
                                }
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: '#fff', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                            ><Archive size={12}/> Archive</button>

                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                setActiveMenu(null);
                                if (window.confirm(`Are you sure you want to delete session "${label}"?`)) {
                                  try {
                                    const res = await fetchWithAuth(`http://localhost:8000/api/history/${s}`, {
                                      method: 'DELETE'
                                    });
                                    if (res.ok) {
                                      if (currentChatId === s) selectChat('dashboard');
                                      fetchChatSessions();
                                    }
                                  } catch (err) { console.error(err); }
                                }
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(239,68,68,0.1)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', color: 'rgba(239,68,68,0.9)', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', borderRadius: '4px', fontSize: '0.75rem', transition: 'background-color 0.2s' }}
                            ><Trash2 size={12}/> Delete</button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Chat Area */}
        <div style={{ ...styles.chatArea, flex: 1, height: '100%', display: 'flex', flexDirection: 'column' }} className="glass-panel">
          {/* Scheduled Task Control Header Card */}
          {(() => {
            const activeSessionObj = (Array.isArray(chatSessions) ? chatSessions : []).find(s => s.id === currentChatId);
            const isCurrentScheduled = Boolean(activeSessionObj?.is_scheduled || currentChatId.startsWith('task_'));
            if (!isCurrentScheduled) return null;

            const scheduleInfo = activeSessionObj?.schedule_info || {};
            const jobId = activeSessionObj?.job_id || (currentChatId.startsWith('task_') ? currentChatId.replace('task_', '') : null);
            const taskStatus = scheduleInfo?.status || 'running';
            const taskType = activeSessionObj?.schedule_type || scheduleInfo?.type || 'scheduled';

            return (
              <div style={{
                padding: '14px 20px',
                background: '#0b0f19',
                borderBottom: '1px solid rgba(0, 240, 255, 0.25)',
                boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '16px',
                flexWrap: 'wrap',
                flexShrink: 0,
                zIndex: 10
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: '240px' }}>
                  <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    background: taskStatus === 'paused' ? 'rgba(255,159,0,0.1)' : taskStatus === 'completed' ? 'rgba(16,185,129,0.1)' : 'rgba(0, 240, 255, 0.1)',
                    border: `1px solid ${taskStatus === 'paused' ? 'rgba(255,159,0,0.3)' : taskStatus === 'completed' ? 'rgba(16,185,129,0.3)' : 'rgba(0, 240, 255, 0.3)'}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0
                  }}>
                    <Clock size={18} style={{ color: taskStatus === 'paused' ? '#ff9f00' : taskStatus === 'completed' ? '#10b981' : 'var(--accent-cyan)' }} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff' }}>
                        {(() => {
                          const title = activeSessionObj?.title || getSessionLabel(currentChatId);
                          if (title && !title.startsWith('task_')) return title;
                          const resolved = getSessionLabel(currentChatId);
                          return (resolved && !resolved.startsWith('task_')) ? resolved : 'Scheduled Task';
                        })()}
                      </span>
                      <span style={{
                        fontSize: '0.62rem',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: taskStatus === 'paused' ? 'rgba(255,159,0,0.15)' : taskStatus === 'completed' ? 'rgba(16,185,129,0.15)' : 'rgba(0,240,255,0.15)',
                        color: taskStatus === 'paused' ? '#ff9f00' : taskStatus === 'completed' ? '#10b981' : 'var(--accent-cyan)',
                        border: `1px solid ${taskStatus === 'paused' ? 'rgba(255,159,0,0.3)' : taskStatus === 'completed' ? 'rgba(16,185,129,0.3)' : 'rgba(0,240,255,0.3)'}`
                      }}>
                        {taskStatus.toUpperCase()}
                      </span>
                      <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)', background: 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: '4px' }}>
                        TYPE: {taskType.toUpperCase()}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {scheduleInfo?.prompt ? `Prompt: "${scheduleInfo.prompt}"` : 'Scheduled Automation Workflow'}
                    </div>
                  </div>
                </div>

                {/* Controls */}
                {jobId && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                      onClick={async () => {
                        try {
                          const res = await fetchWithAuth(`http://localhost:8000/api/timers/${jobId}/run`, { method: 'POST' });
                          if (res.ok) fetchChatSessions();
                        } catch(e) { console.error(e); }
                      }}
                      className="btn-primary"
                      style={{ padding: '6px 12px', border: '1px solid rgba(0,240,255,0.4)', color: 'var(--accent-cyan)', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '5px' }}
                      title="Run task immediately"
                    >
                      <Zap size={13} />
                      <span>Run Now</span>
                    </button>

                    {taskStatus === 'running' ? (
                      <button
                        onClick={async () => {
                          try {
                            const res = await fetchWithAuth(`http://localhost:8000/api/timers/${jobId}/pause`, { method: 'POST' });
                            if (res.ok) fetchChatSessions();
                          } catch(e) { console.error(e); }
                        }}
                        className="btn-primary"
                        style={{ padding: '6px 12px', border: '1px solid rgba(255,159,0,0.4)', color: '#ff9f00', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '5px' }}
                        title="Pause task schedule"
                      >
                        <Pause size={13} />
                        <span>Pause</span>
                      </button>
                    ) : taskStatus === 'paused' ? (
                      <button
                        onClick={async () => {
                          try {
                            const res = await fetchWithAuth(`http://localhost:8000/api/timers/${jobId}/resume`, { method: 'POST' });
                            if (res.ok) fetchChatSessions();
                          } catch(e) { console.error(e); }
                        }}
                        className="btn-primary"
                        style={{ padding: '6px 12px', border: '1px solid rgba(16,185,129,0.4)', color: '#10b981', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '5px' }}
                        title="Resume task schedule"
                      >
                        <Play size={13} />
                        <span>Resume</span>
                      </button>
                    ) : null}

                    <button
                      onClick={async () => {
                        if (window.confirm("Cancel and delete this scheduled task?")) {
                          try {
                            const res = await fetchWithAuth(`http://localhost:8000/api/timers/${jobId}`, { method: 'DELETE' });
                            if (res.ok) fetchChatSessions();
                          } catch(e) { console.error(e); }
                        }
                      }}
                      className="btn-primary"
                      style={{ padding: '6px 10px', border: '1px solid rgba(239,68,68,0.4)', color: '#ef4444', fontSize: '0.75rem' }}
                      title="Cancel task"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                )}
              </div>
            );
          })()}

          <div style={styles.chatScroller}>
            {messages.map((msg, index) => (
              <div 
                key={index} 
                style={{
                  ...styles.msgBubbleWrapper,
                  justifyContent: msg.role === 'user' ? 'flex-end' : (msg.role === 'system' ? 'center' : 'flex-start')
                }}
              >
                {msg.role === 'system' ? (
                  <div style={styles.systemMsg}>{msg.content}</div>
                ) : (
                  <div 
                    style={{
                      ...styles.msgBubble,
                      backgroundColor: msg.role === 'user' ? 'rgba(255, 159, 0, 0.12)' : 'rgba(0, 240, 255, 0.05)',
                      borderColor: msg.role === 'user' ? 'rgba(255, 159, 0, 0.3)' : 'rgba(0, 240, 255, 0.2)',
                      alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start'
                    }}
                  >
                    <div style={styles.msgHeader}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={msg.role === 'user' ? styles.userLabel : styles.assistantLabel}>
                          {msg.role === 'user' ? 'CREATOR' : (() => {
                            const activeSessionAgentId = chatSessions.find(s => s.id === currentChatId)?.agent_id || currentChatId;
                            const matchedAgent = (Array.isArray(subagents) ? subagents : []).find(a => a.id === activeSessionAgentId);
                            return matchedAgent ? matchedAgent.name.toUpperCase() : 'JARVIS';
                          })()}
                        </span>
                        {msg.role === 'assistant' && msg.cost_usd !== undefined && msg.cost_usd > 0 && (
                          <span style={{
                            fontSize: '0.7rem',
                            color: 'var(--success)',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            border: '1px solid rgba(16, 185, 129, 0.2)',
                            padding: '1px 5px',
                            borderRadius: '4px',
                            fontFamily: 'var(--font-mono)',
                            fontWeight: 600,
                            letterSpacing: '0.5px'
                          }}>
                            ${msg.cost_usd.toFixed(5)}
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {/* Per-message play/stop button — only on assistant messages */}
                        {msg.role === 'assistant' && (
                          <button
                            onClick={() => speakText(msg.content, index)}
                            title={playingMsgIndex === index ? 'Stop' : 'Play voice'}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              padding: '2px 4px',
                              borderRadius: '4px',
                              color: playingMsgIndex === index ? '#ff9f00' : 'rgba(0, 240, 255, 0.45)',
                              display: 'flex',
                              alignItems: 'center',
                              transition: 'color 0.2s, transform 0.15s',
                              transform: playingMsgIndex === index ? 'scale(1.15)' : 'scale(1)',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.color = playingMsgIndex === index ? '#ff9f00' : 'var(--accent-cyan)')}
                            onMouseLeave={e => (e.currentTarget.style.color = playingMsgIndex === index ? '#ff9f00' : 'rgba(0, 240, 255, 0.45)')}
                          >
                            {playingMsgIndex === index
                              ? <Square size={12} fill="currentColor" />
                              : <Play size={12} fill="currentColor" />}
                          </button>
                        )}
                        {/* Maximize / Fullscreen button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setFullscreenMsg(msg);
                          }}
                          title="Expand response to fullscreen"
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            padding: '2px 4px',
                            borderRadius: '4px',
                            color: 'rgba(0, 240, 255, 0.45)',
                            display: 'flex',
                            alignItems: 'center',
                            transition: 'color 0.2s, transform 0.15s'
                          }}
                          onMouseEnter={e => (e.currentTarget.style.color = 'var(--accent-cyan)')}
                          onMouseLeave={e => (e.currentTarget.style.color = 'rgba(0, 240, 255, 0.45)')}
                        >
                          <Maximize2 size={12} />
                        </button>
                        {msg.id && (
                          <span style={styles.chatIdLabel}>ID: {msg.id}</span>
                        )}
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', opacity: 0.85, letterSpacing: '0.3px' }}>
                          {formatMessageTimestamp(msg.timestamp || msg.created_at)}
                        </span>
                      </div>
                    </div>
                    <div 
                      style={{ ...styles.msgText, cursor: 'pointer' }}
                      onDoubleClick={() => setFullscreenMsg(msg)}
                      title="Double-click to expand response"
                    >
                      {renderMarkdown(msg.content)}
                    </div>
                    {/* Inline missing-env configuration card */}
                    {msg.role === 'assistant' && (() => {
                      const missingKey = detectMissingEnvKey(msg.content);
                      if (!missingKey) return null;
                      return (
                        <MissingEnvConfigCard
                          messageIndex={index}
                          envKey={missingKey}
                          onSave={async (val) => {
                            try {
                              const res = await fetchWithAuth('http://localhost:8000/api/settings/env', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ key: missingKey, value: val })
                              });
                              return res.ok;
                            } catch {
                              return false;
                            }
                          }}
                        />
                      );
                    })()}
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
                  <span className="hud-status">ENGAGING NEURAL ORCHESTRATION GRAPH [MODEL: {config?.model?.split('/').pop() || 'GEMINI'}]</span>
                  <div className="hud-bar-wrapper">
                    <div className="hud-bar-fill" />
                  </div>
                </div>
              </div>
            )}

            <div ref={mainChatEndRef} />
          </div>

          {/* Chat Input Area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {/* Attached file badge */}
            {attachedFile && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 12px',
                background: 'rgba(0, 240, 255, 0.06)',
                borderTop: '1px solid rgba(0, 240, 255, 0.18)',
                borderLeft: '1px solid rgba(0, 240, 255, 0.18)',
                borderRight: '1px solid rgba(0, 240, 255, 0.18)',
                borderRadius: '8px 8px 0 0',
                fontSize: '0.78rem',
                color: 'var(--accent-cyan)',
                fontFamily: 'var(--font-mono)',
              }}>
                <FileText size={13} style={{ flexShrink: 0 }} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 320 }}>
                  {attachedFile.name}
                </span>
                <span style={{ color: 'var(--text-dim)', fontSize: '0.72rem', flexShrink: 0 }}>
                  {attachedFile.pages
                    ? `${attachedFile.pages} pages${attachedFile.truncated ? ' (truncated)' : ''}`
                    : `(${Math.round(new TextEncoder().encode(attachedFile.content).length / 1024 * 10) / 10} KB)`
                  }
                </span>
                <button
                  type="button"
                  onClick={() => setAttachedFile(null)}
                  title="Remove attachment"
                  style={{
                    marginLeft: 'auto',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-dim)',
                    padding: '2px',
                    display: 'flex',
                    alignItems: 'center',
                    flexShrink: 0,
                  }}
                >
                  <XIcon size={13} />
                </button>
              </div>
            )}

            {/* Chat Input Row */}
            <form onSubmit={handleSendMessage} style={{
              ...styles.chatInputRow,
              ...(attachedFile ? { borderRadius: '0 0 8px 8px', borderTop: 'none' } : {})
            }}>
              {/* Text-file attach button (paperclip) */}
              <label
                title="Attach a text file as chat context (.md, .txt, .json, .py, …)"
                style={{ ...styles.uploadBtn, cursor: (!isConnected || isUploading) ? 'not-allowed' : 'pointer' }}
              >
                <input
                  type="file"
                  onChange={handleChatFileAttach}
                  style={{ display: 'none' }}
                  disabled={!isConnected || isUploading}
                  accept=".md,.txt,.json,.yaml,.yml,.py,.js,.ts,.tsx,.jsx,.sh,.csv,.xml,.html,.css,.env,.toml,.ini,.log,.pdf"
                />
                <Paperclip size={18} style={{ color: (!isConnected || isUploading) ? 'var(--text-dim)' : (attachedFile ? '#10b981' : 'var(--accent-cyan)') }} />
              </label>
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    e.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder={isUploading ? "Uploading file..." : attachedFile ? `Ask Jarvis about "${attachedFile.name}"...` : "Enter command or request for Jarvis, Sir..."}
                style={styles.chatInput}
                className="form-input"
                disabled={!isConnected || isUploading}
                rows={1}
              />
              {isSpeaking && (
                <button
                  type="button"
                  onClick={() => {
                    window.speechSynthesis?.cancel();
                    setIsSpeaking(false);
                    setPlayingMsgIndex(null);
                  }}
                  className="btn-primary"
                  style={{
                    border: '1px solid rgba(239, 68, 68, 0.4)',
                    color: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.05)'
                  }}
                  title="Interrupt current assistant speech"
                >
                  <Square size={14} fill="currentColor" />
                  <span>Interrupt speech</span>
                </button>
              )}
              <button type="submit" className="btn-primary" disabled={!isConnected || isUploading || !inputValue.trim()}>
                <Send size={16} />
                <span>Send</span>
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Fullscreen Message View Modal */}
      {fullscreenMsg && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 99999,
            backgroundColor: 'rgba(3, 10, 20, 0.96)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            display: 'flex',
            flexDirection: 'column',
            animation: 'fadeIn 0.15s ease-out'
          }}
        >
          {/* Top Bar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 36px',
            borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
            backgroundColor: 'rgba(0, 240, 255, 0.03)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <span style={{
                padding: '4px 12px',
                borderRadius: '6px',
                fontSize: '0.78rem',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.5px',
                backgroundColor: fullscreenMsg.role === 'user' ? 'rgba(255, 159, 0, 0.15)' : 'rgba(0, 240, 255, 0.15)',
                color: fullscreenMsg.role === 'user' ? 'var(--accent-orange)' : 'var(--accent-cyan)',
                border: `1px solid ${fullscreenMsg.role === 'user' ? 'rgba(255, 159, 0, 0.3)' : 'rgba(0, 240, 255, 0.3)'}`
              }}>
                {fullscreenMsg.role === 'user' ? 'CREATOR' : 'JARVIS ASSISTANT'}
              </span>
              {fullscreenMsg.id && (
                <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                  ID: {fullscreenMsg.id}
                </span>
              )}
              <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                {formatMessageTimestamp(fullscreenMsg.timestamp || fullscreenMsg.created_at)}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {/* Copy Button */}
              <button
                onClick={() => {
                  navigator.clipboard.writeText(fullscreenMsg.content);
                  setCopiedFullscreen(true);
                  setTimeout(() => setCopiedFullscreen(false), 2000);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(255, 255, 255, 0.06)',
                  border: '1px solid rgba(255, 255, 255, 0.12)',
                  color: copiedFullscreen ? '#10b981' : 'var(--text-primary)',
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
                title="Copy message text"
              >
                {copiedFullscreen ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                <span>{copiedFullscreen ? 'Copied!' : 'Copy'}</span>
              </button>

              {/* Close Button */}
              <button
                onClick={() => setFullscreenMsg(null)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 18px',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#ef4444',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
                title="Close fullscreen view (Esc)"
              >
                <XIcon size={16} />
                <span>Close (Esc)</span>
              </button>
            </div>
          </div>

          {/* Fullscreen Body Scroll */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '40px 60px',
            maxWidth: '1280px',
            width: '100%',
            margin: '0 auto',
            boxSizing: 'border-box'
          }}>
            <div style={{
              fontSize: '1.05rem',
              lineHeight: 1.7,
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-main)'
            }}>
              {renderMarkdown(fullscreenMsg.content)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
