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
  Copy
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
  micState: 'off' | 'listening' | 'capturing';
  micEnabled: boolean;
  setMicEnabled: (val: boolean | ((prev: boolean) => boolean)) => void;
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
  mainChatEndRef
}: ChatTabProps) {
  const [activeMenu, setActiveMenu] = React.useState<string | null>(null);

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
              <span className="pulse-dot" style={{ width: 10, height: 10, background: '#00f0ff', boxShadow: '0 0 6px #00f0ff' }} />
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>MIC</span>
            </div>
          )}
          {micState === 'capturing' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="pulse-dot" style={{ width: 10, height: 10, background: '#ff9f00', boxShadow: '0 0 8px #ff9f00' }} />
              <span style={{ fontSize: '0.75rem', color: '#ff9f00', fontFamily: 'var(--font-mono)' }}>REC</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
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
            }}
          >
            {micEnabled ? <Mic size={14} /> : <MicOff size={14} />}
            <span>{micState === 'capturing' ? 'REC...' : micEnabled ? 'Mic on' : 'Mic off'}</span>
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
                ? '1px solid rgba(0, 240, 255, 0.4)'
                : '1px solid rgba(255,255,255,0.15)',
              color: isTTSEnabled ? 'var(--accent-cyan)' : 'var(--text-dim)',
              boxShadow: isTTSEnabled ? '0 0 8px rgba(0,240,255,0.2)' : 'none',
              transition: 'all 0.2s',
            }}
          >
            {isTTSEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
            <span>{isTTSEnabled ? 'Voice on' : 'Voice off'}</span>
          </button>
          <button onClick={handleClearChat} className="btn-primary" style={{ padding: '6px 12px', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#ef4444' }}>
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
            {chatSessions.map(s => {
              const isActive = currentChatId === s;
              const label = getSessionLabel(s);
              
              return (
                <div 
                  key={s}
                  onMouseLeave={() => setActiveMenu(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: isActive ? '1px solid rgba(0,240,255,0.4)' : '1px solid rgba(255,255,255,0.03)',
                    backgroundColor: isActive ? 'rgba(0,240,255,0.04)' : 'rgba(255,255,255,0.01)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    position: 'relative'
                  }}
                  onClick={() => selectChat(s)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                    <MessageSquare size={14} style={{ color: isActive ? 'var(--accent-cyan)' : 'var(--text-dim)', flexShrink: 0 }} />
                    <span style={{ fontSize: '0.8rem', fontWeight: isActive ? 600 : 500, color: isActive ? '#fff' : 'var(--text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {label}
                    </span>
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
                              const res = await fetch(`http://localhost:8000/api/history/${s}/fork`, { method: 'POST' });
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
                                  const res = await fetch(`http://localhost:8000/api/history/dashboard`, { method: 'DELETE' });
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
                                    const res = await fetch(`http://localhost:8000/api/history/${s}/archive`, { method: 'POST' });
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
                                    const res = await fetch(`http://localhost:8000/api/history/${s}`, { method: 'DELETE' });
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
                          {msg.role === 'user' ? 'CREATOR' : 'JARVIS'}
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
                        {msg.id && (
                          <span style={styles.chatIdLabel}>ID: {msg.id}</span>
                        )}
                      </div>
                    </div>
                    <div style={styles.msgText}>{renderMarkdown(msg.content)}</div>
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
              placeholder={isUploading ? "Uploading file..." : "Enter command or request for Jarvis, Sir..."}
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
  );
}
