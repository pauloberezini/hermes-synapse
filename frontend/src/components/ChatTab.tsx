import React from 'react';
import { 
  Mic, 
  MicOff, 
  Volume2, 
  VolumeX, 
  Trash2, 
  Plus, 
  MessageSquare, 
  Paperclip, 
  Square, 
  Play, 
  Send,
  MoreVertical,
  Archive,
  Copy,
  Cpu,
  Lock
} from 'lucide-react';
import type { ChatMessage, SystemConfig } from '../types';
import { styles } from '../styles';
import { renderMarkdown } from '../utils';

interface ChatTabProps {
  currentChatId: string;
  chatSessions: string[];
  messages: ChatMessage[];
  inputValue: string;
  setInputValue: (val: string) => void;
  isSpeaking: boolean;
  setIsSpeaking: (val: boolean) => void;
  micState: 'off' | 'listening' | 'capturing' | 'transcribing';
  micEnabled: boolean;
  onVoiceToggle: () => void;
  isTTSEnabled: boolean;
  setIsTTSEnabled: (val: boolean | ((prev: boolean) => boolean)) => void;
  isGenerating: boolean;
  playingMsgIndex: number | null;
  setPlayingMsgIndex: (idx: number | null) => void;
  config: SystemConfig;
  isConnected: boolean;
  isUploading: boolean;
  
  speakText: (text: string, index: number) => void;
  handleClearChat: () => void;
  handleSendMessage: (e: React.FormEvent) => void;
  handleFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  selectChat: (chatId: string) => void;
  handleCreateNewSession: () => void;
  fetchChatSessions: () => void;
  getSessionLabel: (sessionId: string) => string;
  mainChatEndRef: React.RefObject<HTMLDivElement | null>;
  t?: (key: string) => string;
  onStopGeneration?: () => void;
  onRetryLast?: () => void;
  hasLastUserMessage?: boolean;
  onChangeModel?: () => void;
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
  onVoiceToggle,
  isTTSEnabled,
  setIsTTSEnabled,
  isGenerating,
  playingMsgIndex,
  setPlayingMsgIndex,
  config,
  isConnected,
  isUploading,
  speakText,
  handleClearChat,
  handleSendMessage,
  handleFileUpload,
  selectChat,
  handleCreateNewSession,
  fetchChatSessions,
  getSessionLabel,
  mainChatEndRef,
  t,
  onStopGeneration,
  onRetryLast,
  hasLastUserMessage,
  onChangeModel
}: ChatTabProps) {
  const [activeMenu, setActiveMenu] = React.useState<string | null>(null);
  const [expandedMeta, setExpandedMeta] = React.useState<number | null>(null);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);
  const [sessionFilter, setSessionFilter] = React.useState('');
  const tr = React.useCallback((key: string, fallback: string) => {
    const value = t ? t(key) : key;
    return value === key ? fallback : value;
  }, [t]);

  const messageContent = (msg: ChatMessage) => {
    if ((msg.content || '').trim()) return msg.content;
    if (msg.streaming) return '';
    return msg.role === 'assistant'
      ? tr('chatEmptyResponse', 'The model returned no text. You can retry or refine the request.')
      : '';
  };

  const statusLabel = (status?: string) => {
    switch (status) {
      case 'empty': return tr('chatStatusEmpty', 'Empty response');
      case 'refusal': return tr('chatStatusRefusal', 'Refused');
      case 'timeout': return tr('chatStatusTimeout', 'Timeout');
      case 'provider_error': return tr('chatStatusProviderError', 'Provider error');
      case 'parse_error': return tr('chatStatusParseError', 'Parse error');
      default: return tr('chatStatusSuccess', 'Success');
    }
  };

  const statusColor = (status?: string) => {
    switch (status) {
      case 'empty': return 'var(--accent-orange)';
      case 'refusal': return 'var(--accent-orange)';
      case 'timeout':
      case 'provider_error':
      case 'parse_error': return 'var(--danger)';
      default: return 'var(--success)';
    }
  };

  const copyRequestId = (requestId: string) => {
    try {
      navigator.clipboard?.writeText(requestId);
      setCopiedId(requestId);
      window.setTimeout(() => setCopiedId(null), 1500);
    } catch { /* clipboard unavailable */ }
  };

  const filteredSessions = React.useMemo(() => {
    const q = sessionFilter.trim().toLowerCase();
    if (!q) return chatSessions;
    return chatSessions.filter(s =>
      s === 'dashboard' || getSessionLabel(s).toLowerCase().includes(q) || s.toLowerCase().includes(q)
    );
  }, [chatSessions, sessionFilter, getSessionLabel]);

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div>
            <h2 className="glow-text-cyan" style={styles.tabTitle}>COMMUNICATION LINK</h2>
            <p style={styles.tabSubtitle}>Voice and text control stream for the assistant</p>
          </div>
          {/* Active Session Label */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '16px', background: 'rgba(255, 255, 255, 0.02)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>SESSION:</span>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
              {currentChatId === 'dashboard' ? 'Main Terminal' : getSessionLabel(currentChatId)}
            </span>
          </div>

          {/* TTS speaking pulse indicator */}
          {isSpeaking && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="pulse-dot" style={{ width: 10, height: 10 }} />
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>VOICE</span>
            </div>
          )}
          {/* Mic state indicator */}
          {micState === 'listening' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="pulse-dot" style={{ width: 10, height: 10, background: 'var(--accent-cyan)', boxShadow: '0 0 8px rgba(115, 217, 255, 0.55)' }} />
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>MIC</span>
            </div>
          )}
          {micState === 'capturing' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="pulse-dot" style={{ width: 10, height: 10, background: 'var(--accent-orange)', boxShadow: '0 0 8px rgba(255, 195, 72, 0.65)' }} />
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-orange)', fontFamily: 'var(--font-mono)' }}>REC</span>
            </div>
          )}
          {micState === 'transcribing' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="pulse-dot" style={{ width: 10, height: 10, background: 'var(--accent-violet)', boxShadow: '0 0 8px rgba(155, 136, 255, 0.65)' }} />
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-violet)', fontFamily: 'var(--font-mono)' }}>STT</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {/* Mic toggle button */}
          <button
            id="mic-toggle-btn"
            onClick={onVoiceToggle}
            className="btn-primary"
            disabled={micState === 'transcribing' || !isConnected || isUploading}
            title={micState === 'capturing' ? 'Stop recording and send to Vexa' : 'Record voice command'}
            style={{
              padding: '6px 12px',
              border: micState === 'capturing'
                ? '1px solid rgba(255, 195, 72, 0.62)'
                : micState === 'transcribing'
                  ? '1px solid rgba(155, 136, 255, 0.5)'
                : micEnabled
                  ? '1px solid rgba(115, 217, 255, 0.42)'
                  : '1px solid rgba(255,255,255,0.15)',
              color: micState === 'capturing' ? 'var(--accent-orange)' : micState === 'transcribing' ? 'var(--accent-violet)' : micEnabled ? 'var(--accent-cyan)' : 'var(--text-dim)',
              boxShadow: micState === 'capturing'
                ? '0 0 10px rgba(255, 195, 72, 0.28)'
                : micState === 'transcribing' ? '0 0 10px rgba(155, 136, 255, 0.24)'
                : micEnabled ? '0 0 8px rgba(115, 217, 255, 0.22)' : 'none',
              transition: 'all 0.2s',
            }}
          >
            {micEnabled ? <Mic size={14} /> : <MicOff size={14} />}
            <span>{micState === 'capturing' ? 'REC...' : micState === 'transcribing' ? 'STT...' : 'Record'}</span>
          </button>
          {/* TTS toggle */}
          <button
            id="tts-toggle-btn"
            onClick={() => {
              if (isTTSEnabled) { window.speechSynthesis?.cancel(); setIsSpeaking(false); }
              setIsTTSEnabled(v => !v);
            }}
            className="btn-primary"
            title={isTTSEnabled ? 'Turn off voice' : 'Turn on voice'}
            style={{
              padding: '6px 12px',
              border: isTTSEnabled
                ? '1px solid rgba(155, 136, 255, 0.45)'
                : '1px solid rgba(255,255,255,0.15)',
              color: isTTSEnabled ? 'var(--accent-violet)' : 'var(--text-dim)',
              boxShadow: isTTSEnabled ? '0 0 8px rgba(155, 136, 255, 0.24)' : 'none',
              transition: 'all 0.2s',
            }}
          >
            {isTTSEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
            <span>{isTTSEnabled ? 'Voice on' : 'Voice off'}</span>
          </button>
          <button onClick={handleClearChat} className="btn-primary" style={{ padding: '6px 12px', border: '1px solid rgba(255, 93, 143, 0.4)', color: 'var(--danger)' }}>
            <Trash2 size={14} />
            <span>Clear Chat</span>
          </button>
        </div>
      </div>

      {/* Split layout: sessions sidebar on the left, chat workspace on the right */}
      <div style={{ display: 'flex', gap: '20px', height: 'calc(100vh - 220px)', flex: 1, minHeight: 0 }} className="chat-layout">
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
              border: '1px solid rgba(155, 136, 255, 0.34)',
              background: 'linear-gradient(135deg, rgba(155, 136, 255, 0.18) 0%, rgba(115, 217, 255, 0.06) 100%)',
              color: '#fff',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
              transition: 'all 0.2s',
              width: '100%',
              boxShadow: '0 0 12px rgba(155, 136, 255, 0.12)'
            }}
          >
            <Plus size={16} style={{ color: 'var(--accent-cyan)' }} />
            <span>New Chat</span>
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', marginBottom: '5px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '1px' }}>ACTIVE SESSIONS</span>
          </div>

          <input
            type="text"
            value={sessionFilter}
            onChange={(e) => setSessionFilter(e.target.value)}
            placeholder={tr('chatSearchAgents', 'Search sessions…')}
            aria-label={tr('chatSearchAgents', 'Search sessions')}
            className="form-input"
            style={{ padding: '6px 10px', fontSize: '0.78rem', marginBottom: '4px' }}
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto', paddingRight: '4px' }}>
            {filteredSessions.map(s => {
              const isActive = currentChatId === s;
              const label = getSessionLabel(s);
              const isDashboard = s === 'dashboard';
              
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
                      : (isActive ? '1px solid rgba(0, 240, 255, 0.4)' : '1px solid rgba(255, 255, 255, 0.03)'),
                    backgroundColor: isDashboard
                      ? (isActive ? 'rgba(0, 240, 255, 0.08)' : 'rgba(0, 240, 255, 0.02)')
                      : (isActive ? 'rgba(0, 240, 255, 0.04)' : 'rgba(255, 255, 255, 0.01)'),
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    position: 'relative',
                    boxShadow: isDashboard ? '0 0 10px rgba(0, 240, 255, 0.04)' : 'none'
                  }}
                  onClick={() => selectChat(s)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                    {isDashboard ? (
                      <Cpu size={14} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    ) : (
                      <MessageSquare size={14} style={{ color: isActive ? 'var(--accent-cyan)' : 'var(--text-dim)', flexShrink: 0 }} />
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', minWidth: 0 }}>
                        <span style={{ fontSize: '0.8rem', fontWeight: (isActive || isDashboard) ? 600 : 500, color: (isActive || isDashboard) ? '#fff' : 'var(--text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {label}
                        </span>
                        {isDashboard && (
                          <span title="Protected core session" style={{ display: 'flex', alignItems: 'center' }}>
                            <Lock size={10} style={{ color: 'rgba(0, 240, 255, 0.4)', flexShrink: 0 }} />
                          </span>
                        )}
                      </div>
                      {isDashboard && (
                        <span style={{ fontSize: '0.6rem', color: 'rgba(0, 240, 255, 0.65)', fontWeight: 500, letterSpacing: '0.5px' }}>MAIN ORCHESTRATOR</span>
                      )}
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
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            setActiveMenu(null);
                            try {
                              const res = await fetch(`/api/history/${s}/fork`, { method: 'POST' });
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
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              setActiveMenu(null);
                              if (window.confirm('Sir, are you sure you want to completely purge the history of the Main Terminal?')) {
                                try {
                                  const res = await fetch(`/api/history/dashboard`, { method: 'DELETE' });
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
                        ) : (
                          <>
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                setActiveMenu(null);
                                if (window.confirm(`Archive session "${label}"?`)) {
                                  try {
                                    const res = await fetch(`/api/history/${s}/archive`, { method: 'POST' });
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
                                    const res = await fetch(`/api/history/${s}`, { method: 'DELETE' });
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
        <div style={{ ...styles.chatArea, flex: 1, height: '100%' }} className="glass-panel">
          {!isConnected && (
            <div role="status" style={{
              background: 'rgba(255, 93, 143, 0.1)',
              border: '1px solid rgba(255, 93, 143, 0.3)',
              color: 'var(--danger)',
              padding: '6px 12px',
              borderRadius: 8,
              fontSize: '0.75rem',
              marginBottom: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}>
              <span className="pulse-dot" style={{ width: 8, height: 8, background: 'var(--danger)' }} />
              {tr('chatOffline', 'Assistant is offline. Reconnecting…')}
            </div>
          )}
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
                      backgroundColor: msg.role === 'user' ? 'rgba(255, 195, 72, 0.12)' : 'rgba(155, 136, 255, 0.08)',
                      borderColor: msg.role === 'user' ? 'rgba(255, 195, 72, 0.3)' : 'rgba(155, 136, 255, 0.22)',
                      alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start'
                    }}
                  >
                    <div style={styles.msgHeader}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={msg.role === 'user' ? styles.userLabel : styles.assistantLabel}>
                          {msg.role === 'user' ? 'CREATOR' : 'VEXA'}
                        </span>
                        {msg.role === 'assistant' && msg.cost_usd !== undefined && msg.cost_usd > 0 && (
                          <span style={{
                            fontSize: '0.7rem',
                            color: 'var(--success)',
                            backgroundColor: 'rgba(95, 240, 191, 0.1)',
                            border: '1px solid rgba(95, 240, 191, 0.2)',
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
                            onClick={() => speakText(messageContent(msg), index)}
                            title={playingMsgIndex === index ? 'Stop' : 'Play voice'}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              padding: '2px 4px',
                              borderRadius: '4px',
                              color: playingMsgIndex === index ? 'var(--accent-orange)' : 'rgba(115, 217, 255, 0.58)',
                              display: 'flex',
                              alignItems: 'center',
                              transition: 'color 0.2s, transform 0.15s',
                              transform: playingMsgIndex === index ? 'scale(1.15)' : 'scale(1)',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.color = playingMsgIndex === index ? 'var(--accent-orange)' : 'var(--accent-cyan)')}
                            onMouseLeave={e => (e.currentTarget.style.color = playingMsgIndex === index ? 'var(--accent-orange)' : 'rgba(115, 217, 255, 0.58)')}
                          >
                            {playingMsgIndex === index
                              ? <Square size={12} fill="currentColor" />
                              : <Play size={12} fill="currentColor" />}
                          </button>
                        )}
                        {msg.id && (
                          <span style={styles.chatIdLabel}>ID: {msg.id}</span>
                        )}
                      </div>
                    </div>
                    {msg.thinking && (
                      <details className="chat-thinking" open={msg.streaming && !msg.content}>
                        <summary>{tr('chatThinking', 'Model thinking')}</summary>
                        <div>{msg.thinking}</div>
                      </details>
                    )}
                    <div style={styles.msgText} className={msg.streaming ? 'chat-streaming-text' : undefined}>
                      {messageContent(msg) ? renderMarkdown(messageContent(msg)) : msg.streaming ? <span className="chat-stream-placeholder">Generating</span> : null}
                    </div>

                    {msg.role === 'assistant' && msg.meta && (
                      <div style={{ marginTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 6 }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, fontSize: '0.68rem', fontFamily: 'var(--font-mono)' }}>
                          <span style={{ color: statusColor(msg.meta.status), fontWeight: 600 }}>
                            {statusLabel(msg.meta.status)}
                          </span>
                          {typeof msg.meta.latency_ms === 'number' && (
                            <span style={{ color: 'var(--text-dim)' }}>
                              {tr('chatLatency', 'Latency')}: {msg.meta.latency_ms} ms
                            </span>
                          )}
                          {(msg.meta.input_tokens != null || msg.meta.output_tokens != null) && (
                            <span style={{ color: 'var(--text-dim)' }}>
                              {tr('chatTokens', 'Tokens')}: {msg.meta.input_tokens ?? 0}/{msg.meta.output_tokens ?? 0}
                            </span>
                          )}
                          {(msg.meta.status === 'empty' || msg.meta.status === 'timeout' ||
                            msg.meta.status === 'provider_error' || msg.meta.status === 'parse_error') && hasLastUserMessage && (
                            <button
                              onClick={() => onRetryLast?.()}
                              disabled={isGenerating}
                              className="btn-primary"
                              style={{ padding: '2px 8px', fontSize: '0.68rem' }}
                            >{tr('chatRetry', 'Retry')}</button>
                          )}
                          {(msg.meta.status === 'empty' || msg.meta.status === 'refusal') && (
                            <button
                              onClick={() => onChangeModel?.()}
                              className="btn-primary"
                              style={{ padding: '2px 8px', fontSize: '0.68rem' }}
                            >{tr('chatChangeModel', 'Change model')}</button>
                          )}
                          <button
                            onClick={() => setExpandedMeta(expandedMeta === index ? null : index)}
                            aria-expanded={expandedMeta === index}
                            className="btn-primary"
                            style={{ padding: '2px 8px', fontSize: '0.68rem' }}
                          >{tr('chatTechDetails', 'Technical details')}</button>
                        </div>

                        {expandedMeta === index && (
                          <div style={{ marginTop: 6, fontSize: '0.66rem', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                            {msg.meta.model && <div>{tr('chatModel', 'Model')}: {msg.meta.model}</div>}
                            {msg.meta.provider && <div>{tr('chatProvider', 'Provider')}: {msg.meta.provider}</div>}
                            {msg.meta.finish_reason && <div>{tr('chatFinishReason', 'Finish reason')}: {msg.meta.finish_reason}</div>}
                            {typeof msg.meta.tool_iterations === 'number' && <div>Tool iterations: {msg.meta.tool_iterations}</div>}
                            {msg.meta.request_id && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span>ID: {msg.meta.request_id}</span>
                                <button
                                  onClick={() => copyRequestId(msg.meta!.request_id as string)}
                                  title={tr('chatCopyRequestId', 'Copy request ID')}
                                  style={{ background: 'none', border: 'none', color: 'var(--accent-cyan)', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center' }}
                                >
                                  <Copy size={11} />
                                </button>
                                {copiedId === msg.meta.request_id && (
                                  <span style={{ color: 'var(--success)' }}>{tr('chatCopied', 'Copied')}</span>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {messages.length === 0 && !isGenerating && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, color: 'var(--text-dim)', gap: 8, padding: 40 }}>
                <MessageSquare size={28} style={{ opacity: 0.5 }} />
                <span style={{ fontSize: '0.85rem', textAlign: 'center' }}>
                  {tr('chatEmptyState', 'No messages yet. Send a request to start the conversation.')}
                </span>
              </div>
            )}
            
            {isGenerating && !messages.some(message => message.streaming) && (
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

          {/* Chat Input */}
          <form onSubmit={handleSendMessage} style={styles.chatInputRow}>
            <label style={{ ...styles.uploadBtn, cursor: (!isConnected || isUploading) ? 'not-allowed' : 'pointer' }}>
              <input 
                type="file" 
                onChange={handleFileUpload} 
                style={{ display: 'none' }} 
                disabled={!isConnected || isUploading}
                accept=".csv,.xlsx,.xls"
              />
              <Paperclip size={18} style={{ color: (!isConnected || isUploading) ? 'var(--text-dim)' : 'var(--accent-cyan)' }} />
            </label>
            <textarea 
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={isUploading ? "Uploading file..." : "Enter command or request for Vexa, Sir..."}
              aria-label="Message input"
              style={styles.chatInput}
              className="form-input"
              disabled={!isConnected || isUploading}
              rows={1}
            />
            {isGenerating && (
              <button
                type="button"
                onClick={() => onStopGeneration?.()}
                className="btn-primary"
                aria-label={tr('chatStop', 'Stop')}
                title={tr('chatStop', 'Stop generation')}
                style={{
                  border: '1px solid rgba(255, 195, 72, 0.5)',
                  color: 'var(--accent-orange)',
                  backgroundColor: 'rgba(255, 195, 72, 0.06)'
                }}
              >
                <Square size={14} fill="currentColor" />
                <span>{tr('chatStop', 'Stop')}</span>
              </button>
            )}
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
                  border: '1px solid rgba(255, 93, 143, 0.4)',
                  color: 'var(--danger)',
                  backgroundColor: 'rgba(255, 93, 143, 0.06)'
                }}
                title="Interrupt current assistant speech"
              >
                <Square size={14} fill="currentColor" />
                <span>Interrupt speech</span>
              </button>
            )}
            <button
              type="submit"
              className="btn-primary"
              aria-label={tr('chatSend', 'Send')}
              disabled={!isConnected || isUploading || isGenerating || !inputValue.trim()}
              title={isGenerating ? tr('chatWaitActive', 'Please wait for the current response to finish.') : tr('chatSend', 'Send')}
            >
              <Send size={16} />
              <span>{tr('chatSend', 'Send')}</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
