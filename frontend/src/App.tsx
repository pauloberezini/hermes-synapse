import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  MessageSquare, 
  Settings, 
  Terminal, 
  Activity, 
  Cpu, 
  Database,
  Layers,
  Wrench,
  BookOpen,
  Network,
  Server
} from 'lucide-react';

import type { ChatMessage, DecisionLog, ActivityLog, SystemConfig } from './types';
import { styles } from './styles';
import { 
  WAKE_WORDS, 
  playBeep, 
  playAlarmSound, 
  stopAlarmSound, 
  initFetchInterceptor 
} from './utils';

// Import sub-components
import { ChatTab } from './components/ChatTab';
import { ConfigTab } from './components/ConfigTab';
import { LogsTab } from './components/LogsTab';
import { ActivityTab } from './components/ActivityTab';
import { MemoryTab } from './components/MemoryTab';
import { ToolsTab } from './components/ToolsTab';
import { SubagentsTab } from './components/SubagentsTab';
import { ObsidianTab } from './components/ObsidianTab';
import { NetworkTab } from './components/NetworkTab';
import { MCPTab } from './components/MCPTab';

// Initialize global fetch interceptor
initFetchInterceptor();

export default function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'config' | 'logs' | 'activity' | 'memory' | 'tools' | 'subagents' | 'obsidian' | 'network' | 'mcp'>('chat');
  const [chatSessions, setChatSessions] = useState<string[]>(['dashboard']);
  const [isConnected, setIsConnected] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!localStorage.getItem('jarvis_auth_token'));
  const [otpCode, setOtpCode] = useState('');
  const [authStatus, setAuthStatus] = useState<'idle' | 'sending' | 'sent' | 'verifying' | 'error' | 'success'>('idle');
  const [authError, setAuthError] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: 'Greetings, Sir. Connection to the Hermes network is complete. Awaiting your instructions.' }
  ]);
  const [logs, setLogs] = useState<DecisionLog[]>([]);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([]);
  const [config, setConfig] = useState<SystemConfig>({
    system_prompt: '',
    model: 'google/gemini-2.5-pro'
  });
  
  // Document / Memory States
  const [documents, setDocuments] = useState<{ id: string; title: string }[]>([]);
  const [noteTitle, setNoteTitle] = useState('');
  const [noteContent, setNoteContent] = useState('');
  const [isIndexing, setIsIndexing] = useState(false);
  const [memorySearchQuery, setMemorySearchQuery] = useState('');
  const [memorySearchResults, setMemorySearchResults] = useState<{ title: string; content: string; score: number }[] | null>(null);
  const [isSearchingMemory, setIsSearchingMemory] = useState(false);

  // Tools and system stats states
  const [timers, setTimers] = useState<{ id: string; label: string; duration?: number; time_left: number; status: string; created_at: string; type?: string; target_time?: string }[]>([]);
  const [systemStats, setSystemStats] = useState<{ cpu_load_percent: number; ram_used_percent: number; ram_total_gb: number; disk_used_percent: number; disk_total_gb: number; disk_used_gb: number; status: string } | null>(null);

  // Market & Price Alert States (only alerts count is kept for ActivityTab)
  const [priceAlerts, setPriceAlerts] = useState<{ id: string; symbol: string; display_name: string; target_price: number; condition: string; created_at: string }[]>([]);

  const [uploads, setUploads] = useState<{ name: string; size_bytes: number }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isTTSEnabled, setIsTTSEnabled] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [playingMsgIndex, setPlayingMsgIndex] = useState<number | null>(null);
  const [micEnabled, setMicEnabled] = useState(false);
  const [micState, setMicState] = useState<'off' | 'listening' | 'capturing'>('off');
  
  const [inputValue, setInputValue] = useState('');
  const [selectedLog, setSelectedLog] = useState<DecisionLog | null>(null);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  
  // Prompt edit states
  const [editedPrompt, setEditedPrompt] = useState('');
  const [editedModel, setEditedModel] = useState('');
  
  const wsRef = useRef<WebSocket | null>(null);
  const mainChatEndRef = useRef<HTMLDivElement | null>(null);
  const subagentChatEndRef = useRef<HTMLDivElement | null>(null);
  const lastSentTimeRef = useRef<number>(0);
  const ttsEnabledRef = useRef(true);       // ref so WS handler always sees current value
  const recognitionRef = useRef<any>(null); // SpeechRecognition instance
  const micStateRef = useRef<'off' | 'listening' | 'capturing'>('off');
  const captureTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingCommandRef = useRef('');

  const [subagents, setSubagents] = useState<{ 
    id: string; 
    name: string; 
    system_prompt: string; 
    model: string;
    agent_type?: string;
    parent_id?: string | null;
    skills?: string;
    x?: number;
    y?: number;
  }[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string>('dashboard');
  const currentChatIdRef = useRef('dashboard');
  
  const [newAgentId, setNewAgentId] = useState('');
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentPrompt, setNewAgentPrompt] = useState('');
  const [newAgentModel, setNewAgentModel] = useState('google/gemini-2.5-flash');
  const [newAgentSkills, setNewAgentSkills] = useState('');
  const [newAgentTemperature, setNewAgentTemperature] = useState(0.7);
  const [isCreatingAgent, setIsCreatingAgent] = useState(false);

  // Connection channel session states
  const [showNewSessionModal, setShowNewSessionModal] = useState(false);
  const [newSessionNameInput, setNewSessionNameInput] = useState('');

  const [editingAgentId, setEditingAgentId] = useState('');
  const [editAgentName, setEditAgentName] = useState('');
  const [editAgentPrompt, setEditAgentPrompt] = useState('');
  const [editAgentModel, setEditAgentModel] = useState('google/gemini-2.5-flash');
  const [editAgentSkills, setEditAgentSkills] = useState('');
  const [editAgentTemperature, setEditAgentTemperature] = useState(0.7);
  const [isUpdatingAgent, setIsUpdatingAgent] = useState(false);
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => { currentChatIdRef.current = currentChatId; }, [currentChatId]);

  // Keep ttsEnabledRef in sync with its state
  useEffect(() => { ttsEnabledRef.current = isTTSEnabled; }, [isTTSEnabled]);

  // ── TTS helper ─────────────────────────────────────────────────────────────
  const speakText = useCallback((rawText: string, msgIndex?: number) => {
    if (!('speechSynthesis' in window)) return;
    // If already playing this message — stop it
    if (msgIndex !== undefined && msgIndex === playingMsgIndex) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      setPlayingMsgIndex(null);
      return;
    }
    // Filter out Markdown tables and dividers line-by-line first
    const lines = rawText.split('\n');
    const filteredLines = lines.filter(line => {
      const trimmed = line.trim();
      if ((trimmed.match(/\|/g) || []).length >= 2) {
        return false;
      }
      if (/^[-\=_*]{3,}$/.test(trimmed)) {
        return false;
      }
      return true;
    });
    const textWithoutTables = filteredLines.join('\n');

    // Strip markdown before speaking
    const clean = textWithoutTables
      .replace(/```[\s\S]*?```/g, 'code block.')
      .replace(/`[^`]+`/g, '')
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/__(.+?)__/g, '$1')
      .replace(/\*(.+?)\*/g, '$1')
      .replace(/_(.+?)_/g, '$1')
      .replace(/#{1,6}\s/g, '')
      .replace(/!?\[.*?\]\(.*?\)/g, '')
      .replace(/[\r\n]+/g, '. ')
      .replace(/[^a-zA-Zа-яА-ЯёЁ0-9\+\-\=\.,\?!:;\s]/g, ' ')
      .replace(/\.{2,}/g, '.')
      .replace(/\s+/g, ' ')
      .trim();
    if (!clean) return;

    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(clean);
    utter.lang = 'ru-RU';
    utter.rate = 1.05;
    utter.pitch = 0.95;

    // Prefer a Russian male voice
    const voices = window.speechSynthesis.getVoices();
    const ruVoices = voices.filter(v => v.lang.startsWith('ru'));
    
    // Try to find a male voice by checking common male names or tags
    const maleVoice = ruVoices.find(v => 
      v.name.toLowerCase().includes('yuri') || 
      v.name.toLowerCase().includes('pavel') || 
      v.name.toLowerCase().includes('male') ||
      v.name.toLowerCase().includes('boris')
    );
    
    if (maleVoice) {
      utter.voice = maleVoice;
    } else if (ruVoices.length > 0) {
      utter.voice = ruVoices[ruVoices.length - 1];
    }

    if (msgIndex !== undefined) setPlayingMsgIndex(msgIndex);
    utter.onstart  = () => setIsSpeaking(true);
    utter.onend    = () => { setIsSpeaking(false); setPlayingMsgIndex(null); };
    utter.onerror  = () => { setIsSpeaking(false); setPlayingMsgIndex(null); };
    window.speechSynthesis.speak(utter);
  }, [playingMsgIndex]);

  // ── Voice command helpers ───────────────────────────────────────────────────
  const sendVoiceCommand = useCallback((text: string) => {
    const command = text.trim();
    pendingCommandRef.current = '';
    micStateRef.current = 'listening';
    setMicState('listening');
    if (!command) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    // Interrupt TTS before sending so Jarvis doesn't talk over himself
    window.speechSynthesis?.cancel();
    wsRef.current.send(JSON.stringify({ type: 'chat_message', content: command, chat_id: currentChatIdRef.current }));
    setIsGenerating(true);
  }, []);

  const sendVoiceCommandRef = useRef(sendVoiceCommand);
  useEffect(() => { sendVoiceCommandRef.current = sendVoiceCommand; }, [sendVoiceCommand]);

  const scheduleSend = useCallback(() => {
    if (captureTimerRef.current) clearTimeout(captureTimerRef.current);
    captureTimerRef.current = setTimeout(() => {
      sendVoiceCommandRef.current(pendingCommandRef.current);
    }, 1800);
  }, []);

  const scheduleSendRef = useRef(scheduleSend);
  useEffect(() => { scheduleSendRef.current = scheduleSend; }, [scheduleSend]);

  // ── Mic useEffect — starts/stops SpeechRecognition ─────────────────────────
  useEffect(() => {
    console.log('[Mic] useEffect fired, micEnabled=', micEnabled);
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { if (micEnabled) alert('Voice input is not supported by your browser'); return; }
    if (!micEnabled) {
      micStateRef.current = 'off';
      setMicState('off');
      if (captureTimerRef.current) clearTimeout(captureTimerRef.current);
      try { recognitionRef.current?.abort(); } catch (_) {}
      recognitionRef.current = null;
      return;
    }

    let active = true;

    const recognition = new SR();
    recognitionRef.current = recognition;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'ru-RU';
    recognition.maxAlternatives = 1;

    const stopWords = [
      '\u0441\u0442\u043e\u043f',
      '\u043c\u043e\u043b\u0447\u0438',
      '\u043f\u043e\u043c\u043e\u043b\u0447\u0438',
      '\u0445\u0432\u0430\u0442\u0438\u0442',
      '\u0442\u0438\u0445\u043e',
      '\u0432\u044b\u043a\u043b\u044e\u0447\u0438',
      '\u043f\u0440\u0435\u043a\u0440\u0430\u0442\u0438',
      '\u043e\u0442\u043c\u0435\u043d\u0430',
      'stop', 'quiet', 'cancel'
    ];

    recognition.onresult = (event: any) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += t; else interim += t;
      }
      const text = (final || interim).toLowerCase().trim();
      console.log('[Mic] onresult text=', text, 'state=', micStateRef.current);
      if (!text) return;

      const words = text.split(/\s+/);
      const isStopWord = words.some(w => stopWords.includes(w));
      const hasWake = WAKE_WORDS.some(w => text.includes(w));

      if ((hasWake && isStopWord) || (micStateRef.current === 'capturing' && isStopWord && words.length <= 2)) {
        playBeep(600, 0.15);
        setTimeout(() => playBeep(450, 0.20), 150);
        window.speechSynthesis?.cancel();
        setIsSpeaking(false);
        setPlayingMsgIndex(null);
        stopAlarmSound();
        if (captureTimerRef.current) clearTimeout(captureTimerRef.current);
        pendingCommandRef.current = '';
        micStateRef.current = 'listening';
        setMicState('listening');
        return;
      }

      if (micStateRef.current === 'listening') {
        const hit = WAKE_WORDS.find(w => text.includes(w));
        if (hit) {
          const afterWake = text.substring(text.indexOf(hit) + hit.length).trim();
          playBeep(880, 0.18);
          setTimeout(() => playBeep(1100, 0.12), 200);
          micStateRef.current = 'capturing';
          setMicState('capturing');
          pendingCommandRef.current = afterWake;
          if (afterWake && final) { scheduleSendRef.current(); }
        }
      } else if (micStateRef.current === 'capturing') {
        if (final) {
          pendingCommandRef.current = (pendingCommandRef.current + ' ' + final.trim()).trim();
          scheduleSendRef.current();
        } else {
          if (captureTimerRef.current) clearTimeout(captureTimerRef.current);
          captureTimerRef.current = setTimeout(() => {
            sendVoiceCommandRef.current(pendingCommandRef.current);
          }, 1800);
        }
      }
    };

    recognition.onstart = () => console.log('[Mic] recognition STARTED');

    recognition.onend = () => {
      console.log('[Mic] recognition ENDED, active=', active);
      if (active) {
        setTimeout(() => {
          if (active) {
            console.log('[Mic] restarting recognition...');
            try { recognition.start(); } catch (e) { console.error('[Mic] restart error:', e); }
          }
        }, 150);
      }
    };

    recognition.onerror = (e: any) => {
      console.warn('[Mic] recognition ERROR:', e.error);
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      if (active) {
        setTimeout(() => {
          if (active) {
            try { recognition.start(); } catch (err) { console.error('[Mic] restart after error failed:', err); }
          }
        }, 300);
      }
    };

    micStateRef.current = 'listening';
    setMicState('listening');
    console.log('[Mic] calling recognition.start()');
    try { recognition.start(); } catch (e) { console.error('[Mic] initial start error:', e); }

    return () => {
      console.log('[Mic] cleanup called, setting active=false');
      active = false;
      micStateRef.current = 'off';
      setMicState('off');
      try { recognition.abort(); } catch (_) {}
      recognitionRef.current = null;
    };
  }, [micEnabled]);

  // Request browser notification permission once on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.getVoices();
      window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }
  }, []);

  // Listen for unauthorized events to clear auth state
  useEffect(() => {
    const handleUnauthorized = () => {
      setIsAuthenticated(false);
    };
    window.addEventListener('jarvis-unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('jarvis-unauthorized', handleUnauthorized);
    };
  }, []);

  const handleRequestOtp = async () => {
    setAuthStatus('sending');
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/auth/request-code', {
        method: 'POST'
      });
      const data = await res.json();
      if (data.status === 'success') {
        setAuthStatus('sent');
      } else {
        setAuthStatus('error');
        setAuthError(data.message || 'Error sending code.');
      }
    } catch (err) {
      setAuthStatus('error');
      setAuthError('Error connecting to backend.');
    }
  };

  const verifyOtpCode = async (code: string) => {
    if (!code.trim()) return;
    setAuthStatus('verifying');
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/auth/verify-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('jarvis_auth_token', data.token);
        setIsAuthenticated(true);
        setAuthStatus('success');
        setOtpCode('');
      } else {
        const data = await res.json();
        setAuthStatus('error');
        setAuthError(data.detail || 'Invalid access code.');
      }
    } catch (err) {
      setAuthStatus('error');
      setAuthError('Error verifying code.');
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    verifyOtpCode(otpCode);
  };

  useEffect(() => {
    if (otpCode.length === 6 && authStatus !== 'verifying') {
      verifyOtpCode(otpCode);
    }
  }, [otpCode, authStatus]);

  // Initialize and maintain WebSocket connection
  useEffect(() => {
    if (!isAuthenticated) return;
    
    let reconnectTimeoutId: any = null;
    let isCleanedUp = false;

    const connectWS = () => {
      if (isCleanedUp) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const token = localStorage.getItem('jarvis_auth_token') || '';
      const wsUrl = `${protocol}//${window.location.hostname}:8000/api/ws?token=${encodeURIComponent(token)}`;
      
      console.log(`Connecting to WebSocket: ${wsUrl}`);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        console.log('WebSocket connected.');
      };

      ws.onclose = () => {
        setIsConnected(false);
        console.log('WebSocket disconnected. Reconnecting in 3s...');
        if (!isCleanedUp) {
          reconnectTimeoutId = setTimeout(connectWS, 3000);
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WS Event received:', data);
          
          if (data.type === 'init') {
            setConfig(data.config);
            setEditedPrompt(data.config.system_prompt);
            setEditedModel(data.config.model);
            if (data.logs) {
              setLogs(data.logs);
            }
            if (data.history && data.history.length > 0) {
              setMessages(data.history);
            }
            if (data.activity_logs) {
              setActivityLogs(data.activity_logs);
            }
          } else if (data.type === 'chat_message') {
            const msgChatId = data.chat_id || 'dashboard';
            if (msgChatId === currentChatIdRef.current) {
              setMessages((prev) => [...prev, {
                id: data.id,
                role: data.role,
                content: data.content,
                chat_id: msgChatId,
                cost_usd: data.cost_usd
              }]);
            }
            if (data.role === 'assistant') {
              setIsGenerating(false);
              if (data.suppress_tts) {
                window.speechSynthesis?.cancel();
                setIsSpeaking(false);
                setPlayingMsgIndex(null);
              } else if (ttsEnabledRef.current && msgChatId === currentChatIdRef.current) {
                speakText(data.content as string);
              }
              if (
                'Notification' in window &&
                Notification.permission === 'granted' &&
                document.visibilityState !== 'visible'
              ) {
                const preview = (data.content as string)
                  .replace(/\*\*|__|\*|_|`/g, '')
                  .trim()
                  .slice(0, 80);
                new Notification('JARVIS', {
                  body: preview || 'New Jarvis response',
                  icon: '/favicon.ico',
                  tag: 'jarvis-reply',
                  silent: false,
                });
              }
            }
          } else if (data.type === 'user_message_id_update') {
            const msgChatId = data.chat_id || 'dashboard';
            if (msgChatId === currentChatIdRef.current) {
              setMessages((prev) => prev.map(m => 
                m.role === 'user' && m.content === data.content && !m.id
                  ? { ...m, id: data.id }
                  : m
              ));
            }
          } else if (data.type === 'logs_update') {
            setLogs(data.logs);
          } else if (data.type === 'activity_log') {
            setActivityLogs((prev) => {
              const updated = [data.log, ...prev];
              return updated.slice(0, 200);
            });
          } else if (data.type === 'config_update') {
            setConfig({ system_prompt: data.system_prompt, model: data.model });
            setEditedPrompt(data.system_prompt);
            setEditedModel(data.model);
          } else if (data.type === 'timer_completed') {
            setTimers((prev) => {
              const exists = prev.some(t => t.id === data.timer.id);
              if (exists) {
                return prev.map(t => t.id === data.timer.id ? { ...t, status: 'completed', time_left: 0 } : t);
              }
              return [...prev, { ...data.timer, time_left: 0, status: 'completed' }];
            });
            playAlarmSound();
            speakText(`Sir, the timer "${data.timer.label}" is complete.`);
          } else if (data.type === 'alarm_fired') {
            setTimers((prev) => {
              const exists = prev.some(t => t.id === data.alarm.id);
              if (exists) {
                return prev.map(t => t.id === data.alarm.id ? { ...t, status: 'completed', time_left: 0 } : t);
              }
              return [...prev, { ...data.alarm, time_left: 0, status: 'completed' }];
            });
            playAlarmSound();
            speakText(`Sir, the alarm "${data.alarm.label}" has gone off.`);
          } else if (data.type === 'trace_update') {
            if (data.trace.agent !== 'Router') {
              setMessages((prev) => [...prev, {
                role: 'system',
                content: `⚙️ [${data.trace.agent}] ${data.trace.action}: ${data.trace.message.split('\n')[0]}`
              }]);
            }
          }
        } catch (err) {
          console.error('Error parsing WS frame:', err);
        }
      };
    };

    connectWS();

    return () => {
      isCleanedUp = true;
      if (reconnectTimeoutId) {
        clearTimeout(reconnectTimeoutId);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const fetchDocuments = () => {
    fetch('http://localhost:8000/api/documents')
      .then(res => res.json())
      .then(data => setDocuments(data))
      .catch(err => console.log('Error fetching documents:', err));
  };

  const fetchUploads = () => {
    fetch('http://localhost:8000/api/uploads')
      .then(res => res.json())
      .then(data => setUploads(data))
      .catch(err => console.log('Error fetching uploads:', err));
  };

  const fetchChatSessions = () => {
    fetch('http://localhost:8000/api/history/sessions')
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setChatSessions(data);
        }
      })
      .catch(err => console.log('Error fetching sessions:', err));
  };

  const getSessionLabel = (id: string) => {
    if (id === 'dashboard') return 'Main Terminal';
    if (id.startsWith('chat_')) {
      const parts = id.split('_');
      if (parts.length >= 3) {
        const namePart = parts.slice(1, -1).join('_');
        const decoded = namePart.replace(/_/g, ' ');
        return decoded.charAt(0).toUpperCase() + decoded.slice(1);
      } else if (parts.length === 2) {
        const ts = parseInt(parts[1], 10);
        if (!isNaN(ts)) {
          return new Date(ts).toLocaleString('ru-RU', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        }
      }
    }
    return id;
  };

  const handleCreateNewSessionConfirm = (name: string) => {
    let sessionId = '';
    const trimmed = name.trim();
    if (trimmed) {
      const sanitized = trimmed.toLowerCase().replace(/[^a-z0-9а-яё_-]/g, '_');
      sessionId = `chat_${sanitized}_${Date.now().toString().slice(-4)}`;
    } else {
      sessionId = `chat_${Date.now()}`;
    }
    
    selectChat(sessionId);
    setChatSessions(prev => {
      if (prev.includes(sessionId)) return prev;
      return [...prev, sessionId];
    });
  };

  const handleCreateNewSession = () => {
    setNewSessionNameInput('');
    setShowNewSessionModal(true);
  };

  const fetchSubagents = () => {
    fetch('http://localhost:8000/api/subagents')
      .then(res => res.json())
      .then(data => setSubagents(data))
      .catch(err => console.log('Error fetching subagents:', err));
  };

  const selectChat = (chatId: string, currentSubagentsList?: any[]) => {
    const listToSearch = currentSubagentsList || subagents;
    setCurrentChatId(chatId);
    setMessages([]); // clear temporarily
    fetch(`http://localhost:8000/api/history/${chatId}`)
      .then(res => res.json())
      .then(data => {
        if (data && data.length > 0) {
          setMessages(data);
        } else {
          if (chatId === 'dashboard') {
            setMessages([{ role: 'assistant', content: 'Greetings, Sir. Connection to the Hermes network is complete. Awaiting your instructions.' }]);
          } else {
            const agent = listToSearch.find((a: any) => a.id === chatId);
            setMessages([{ role: 'assistant', content: `Sub-agent session "${agent?.name || chatId}" initialized, Sir. Ready for work.` }]);
          }
        }
      })
      .catch(err => console.error('Error fetching history:', err));
  };

  const handleCreateSubagent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAgentId.trim() || !newAgentName.trim() || !newAgentPrompt.trim()) {
      alert('Please fill in all fields.');
      return;
    }
    setIsCreatingAgent(true);
    try {
      const cleanId = newAgentId.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
      const res = await fetch('http://localhost:8000/api/subagents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(localStorage.getItem('jarvis_auth_token') ? { 'Authorization': `Bearer ${localStorage.getItem('jarvis_auth_token')}` } : {}) },
        body: JSON.stringify({
          id: cleanId,
          name: newAgentName,
          system_prompt: newAgentPrompt,
          model: newAgentModel,
          skills: newAgentSkills,
          temperature: newAgentTemperature,
        })
      });
      if (res.ok) {
        setNewAgentId('');
        setNewAgentName('');
        setNewAgentPrompt('');
        setNewAgentSkills('');
        setNewAgentTemperature(0.7);
        alert('Sub-agent successfully created.');
        
        fetch('http://localhost:8000/api/subagents')
          .then(r => r.json())
          .then(data => {
            setSubagents(data);
            selectChat(cleanId, data);
          });
      } else {
        alert('Failed to create sub-agent.');
      }
    } catch (err) {
      console.error(err);
      alert('Error creating sub-agent.');
    } finally {
      setIsCreatingAgent(false);
    }
  };

  const handleDeleteSubagent = async (id: string) => {
    if (!confirm('Are you sure you want to delete this sub-agent? The chat history will also be deleted from the server.')) {
      return;
    }
    try {
      const res = await fetch(`http://localhost:8000/api/subagents/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchSubagents();
        if (currentChatId === id) {
          selectChat('dashboard');
        }
        alert('Sub-agent deleted.');
      } else {
        alert('Failed to delete sub-agent.');
      }
    } catch (err) {
      console.error(err);
      alert('Error during deletion.');
    }
  };

  const handleUpdateSubagent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAgentId || !editAgentName.trim() || !editAgentPrompt.trim()) {
      alert('Please fill in all fields.');
      return;
    }
    setIsUpdatingAgent(true);
    try {
      const res = await fetch('http://localhost:8000/api/subagents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(localStorage.getItem('jarvis_auth_token') ? { 'Authorization': `Bearer ${localStorage.getItem('jarvis_auth_token')}` } : {}) },
        body: JSON.stringify({
          id: editingAgentId,
          name: editAgentName,
          system_prompt: editAgentPrompt,
          model: editAgentModel,
          skills: editAgentSkills,
          temperature: editAgentTemperature,
        })
      });
      if (res.ok) {
        alert('Sub-agent successfully updated.');
        fetch('http://localhost:8000/api/subagents')
          .then(r => r.json())
          .then(data => {
            setSubagents(data);
            selectChat(editingAgentId, data);
          });
      } else {
        alert('Failed to update sub-agent.');
      }
    } catch (err) {
      console.error(err);
      alert('Error updating sub-agent.');
    } finally {
      setIsUpdatingAgent(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch('http://localhost:8000/api/upload', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        fetchUploads();
        alert(`File ${file.name} successfully uploaded.`);
      } else {
        alert('Error uploading file.');
      }
    } catch (err) {
      console.error(err);
      alert('Backend connection error during file upload.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleCancelTimer = (id: string) => {
    fetch(`http://localhost:8000/api/timers/${id}`, {
      method: 'DELETE',
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'cancelled') {
          setTimers(prev => prev.filter(t => t.id !== id));
        }
      })
      .catch(err => console.error('Error cancelling timer:', err));
  };

  const fetchMarketAlerts = () => {
    fetch('http://localhost:8000/api/market/alerts')
      .then(res => res.json())
      .then(data => setPriceAlerts(data))
      .catch(err => console.log('Error fetching market alerts:', err));
  };

  const handleClearActivityLogs = () => {
    fetch('http://localhost:8000/api/activity/logs', {
      method: 'DELETE'
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setActivityLogs([]);
        }
      })
      .catch(err => console.log('Error clearing activity logs:', err));
  };

  const fetchModels = () => {
    const token = localStorage.getItem('jarvis_auth_token');
    fetch('http://localhost:8000/api/models', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setModels(data);
        }
      })
      .catch(err => console.error('Error fetching models:', err));
  };

  // Fetch initial logs & config from REST API as fallback
  useEffect(() => {
    if (!isAuthenticated) return;

    fetch('http://localhost:8000/api/config')
      .then(res => res.json())
      .then(data => {
        if (data && data.system_prompt !== undefined) {
          setConfig(data);
          setEditedPrompt(data.system_prompt);
          setEditedModel(data.model);
        }
      })
      .catch(() => console.log('REST config fetch skipped/failed (using WS instead)'));

    fetch('http://localhost:8000/api/logs')
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setLogs(data);
        }
      })
      .catch(() => console.log('REST logs fetch skipped/failed'));
      
    fetchDocuments();
    fetchUploads();
    fetchSubagents();
    fetchChatSessions();
    fetchModels();
  }, [isAuthenticated]);

  // Fetch system stats and timers when the "tools" tab is active
  useEffect(() => {
    if (activeTab !== 'tools') return;

    const fetchStats = () => {
      fetch('http://localhost:8000/api/system/stats')
        .then(res => res.json())
        .then(data => setSystemStats(data))
        .catch(err => console.log('Error fetching system stats:', err));
    };

    const fetchTimersData = () => {
      fetch('http://localhost:8000/api/timers')
        .then(res => res.json())
        .then(data => setTimers(data))
        .catch(err => console.log('Error fetching timers:', err));
    };

    fetchStats();
    fetchTimersData();
    fetchUploads();
    fetchMarketAlerts();

    const statsInterval = setInterval(() => {
      fetchStats();
      fetchUploads();
    }, 5000);
    const timersInterval = setInterval(fetchTimersData, 2000);
    const marketInterval = setInterval(() => {
      fetchMarketAlerts();
    }, 10000);

    return () => {
      clearInterval(statsInterval);
      clearInterval(timersInterval);
      clearInterval(marketInterval);
    };
  }, [activeTab]);

  // Local smooth countdown for timers in state
  useEffect(() => {
    const localTicker = setInterval(() => {
      setTimers(prevTimers =>
        prevTimers.map(timer => {
          if (timer.status === 'running' && timer.time_left > 0) {
            return { ...timer, time_left: timer.time_left - 1 };
          }
          return timer;
        })
      );
    }, 1000);

    return () => clearInterval(localTicker);
  }, []);

  const handleIndexNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteTitle.trim() || !noteContent.trim()) return;
    setIsIndexing(true);
    try {
      const res = await fetch('http://localhost:8000/api/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: noteTitle, content: noteContent })
      });
      if (res.ok) {
        setNoteTitle('');
        setNoteContent('');
        alert('Document indexed, Sir.');
        fetchDocuments();
      } else {
        alert('Index error.');
      }
    } catch (err) {
      console.error(err);
      alert('Connection error.');
    } finally {
      setIsIndexing(false);
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!window.confirm('Delete document from long-term memory?')) return;
    try {
      const res = await fetch(`http://localhost:8000/api/documents/${docId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchDocuments();
        alert('Document deleted.');
      } else {
        alert('Deletion error.');
      }
    } catch (err) {
      console.error(err);
      alert('Connection error.');
    }
  };

  const handleSearchMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!memorySearchQuery.trim()) return;
    setIsSearchingMemory(true);
    try {
      const res = await fetch(`http://localhost:8000/api/documents/search?q=${encodeURIComponent(memorySearchQuery)}`);
      if (res.ok) {
        const data = await res.json();
        setMemorySearchResults(data);
      } else {
        alert('Search query error.');
      }
    } catch (err) {
      console.error(err);
      alert('Backend connection error.');
    } finally {
      setIsSearchingMemory(false);
    }
  };

  const handleClearMemorySearch = () => {
    setMemorySearchQuery('');
    setMemorySearchResults(null);
  };

  // Auto-scroll chat to bottom
  useEffect(() => {
    const timer = setTimeout(() => {
      if (mainChatEndRef.current) {
        mainChatEndRef.current.scrollIntoView({ behavior: 'auto' });
      }
      if (subagentChatEndRef.current) {
        subagentChatEndRef.current.scrollIntoView({ behavior: 'auto' });
      }
    }, 50);
    return () => clearTimeout(timer);
  }, [messages, currentChatId, activeTab]);

  // Send message through WebSocket
  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const now = Date.now();
    if (now - lastSentTimeRef.current < 300) {
      console.warn("Prevented duplicate message submission");
      return;
    }
    lastSentTimeRef.current = now;

    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    setPlayingMsgIndex(null);

    wsRef.current.send(JSON.stringify({
      type: 'chat_message',
      content: inputValue,
      chat_id: currentChatId
    }));
    
    setIsGenerating(true);
    setInputValue('');
  };

  const handleClearChat = async () => {
    if (!window.confirm('Sir, are you sure you want to completely clear the history of this session?')) return;
    
    setMessages([]);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${currentChatId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchChatSessions();
        if (currentChatId === 'dashboard') {
          setMessages([{ role: 'assistant', content: 'Greetings, Sir. Connection to the Hermes network is complete. Awaiting your instructions.' }]);
        } else {
          const agent = subagents.find((a: any) => a.id === currentChatId);
          setMessages([{ role: 'assistant', content: `Sub-agent session "${agent?.name || currentChatId}" cleared, Sir. Ready for work.` }]);
        }
      }
    } catch(e) {
      console.error('Error clearing history:', e);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingConfig(true);
    try {
      const response = await fetch('http://localhost:8000/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_prompt: editedPrompt,
          model: editedModel
        })
      });
      if (response.ok) {
        const data = await response.json();
        setConfig(data.config);
        alert('System configuration updated, Sir.');
      } else {
        alert('Error updating configuration.');
      }
    } catch (err) {
      console.error(err);
      alert('Connection error with backend server.');
    } finally {
      setIsSavingConfig(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        width: '100vw',
        background: 'radial-gradient(circle at center, #0f172a 0%, #020617 100%)',
        color: '#e2e8f0',
        fontFamily: 'Inter, sans-serif',
        padding: '20px',
        boxSizing: 'border-box'
      }} className="scanlines">
        <div style={{
          width: '100%',
          maxWidth: '400px',
          padding: '40px 30px',
          borderRadius: '16px',
          boxShadow: '0 0 40px rgba(6, 182, 212, 0.15)',
          border: '1px solid rgba(6, 182, 212, 0.2)',
          textAlign: 'center'
        }} className="glass-panel">
          
          <div style={{ marginBottom: '30px' }}>
            <div className="pulse-dot" style={{ width: 16, height: 16, margin: '0 auto 12px' }} />
            <h1 className="glow-text-cyan" style={{ fontSize: '2.5rem', fontWeight: 800, letterSpacing: '2px', margin: 0 }}>HERMES</h1>
            <p style={{ color: '#06b6d4', fontSize: '0.9rem', letterSpacing: '4px', margin: '4px 0 0', textTransform: 'uppercase' }}>Secure Access Link</p>
          </div>

          <p style={{ color: '#94a3b8', fontSize: '0.95rem', lineHeight: '1.6', marginBottom: '30px' }}>
            Sir, identity confirmation is required to access the management console.
          </p>

          {authStatus === 'idle' && (
            <button
              onClick={handleRequestOtp}
              style={{
                width: '100%',
                padding: '14px',
                borderRadius: '8px',
                border: '1px solid #06b6d4',
                background: 'rgba(6, 182, 212, 0.1)',
                color: '#06b6d4',
                fontWeight: 600,
                fontSize: '1rem',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              className="glow-btn-cyan"
            >
              Request code in Telegram
            </button>
          )}

          {authStatus === 'sending' && (
            <p style={{ color: '#06b6d4', fontSize: '0.95rem' }}>Initializing session and sending code...</p>
          )}

          {(authStatus === 'sent' || authStatus === 'verifying' || authStatus === 'error') && (
            <form onSubmit={handleVerifyOtp} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <p style={{ color: '#10b981', fontSize: '0.85rem', margin: '0 0 10px' }}>
                ✓ Authorization code sent to your trusted Telegram chat.
              </p>
              
              <input
                type="text"
                maxLength={6}
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="0 0 0 0 0 0"
                style={{
                  width: '100%',
                  padding: '16px',
                  borderRadius: '8px',
                  border: '1px solid rgba(6, 182, 212, 0.3)',
                  background: 'rgba(15, 23, 42, 0.6)',
                  color: '#fff',
                  fontSize: '1.5rem',
                  letterSpacing: '12px',
                  textAlign: 'center',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
                disabled={authStatus === 'verifying'}
                autoFocus
              />

              {authError && (
                <p style={{ color: '#ef4444', fontSize: '0.85rem', margin: 0 }}>
                  ⚠️ {authError}
                </p>
              )}

              {authStatus === 'verifying' && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', padding: '10px 0' }}>
                  <span className="pulse-dot" style={{ width: 8, height: 8, background: '#06b6d4', boxShadow: '0 0 6px #06b6d4' }} />
                  <span style={{ color: '#06b6d4', fontSize: '0.9rem', fontFamily: 'var(--font-mono)' }}>VERIFYING CODE...</span>
                </div>
              )}

              <button
                type="button"
                onClick={handleRequestOtp}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#64748b',
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  marginTop: '10px'
                }}
              >
                Resend code
              </button>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-container scanlines">
      {/* 1. Left Sidebar */}
      <aside style={styles.sidebar} className="glass-panel">
        <div style={styles.logoArea}>
          <div className="pulse-dot" style={{ width: 14, height: 14 }} />
          <h1 className="glow-text-cyan" style={styles.logoTitle}>HERMES</h1>
        </div>
        <p style={styles.logoSubtitle}>SYSTEM CONSOLE v1.0</p>
        
        <nav style={styles.navMenu}>
          <button 
            style={{...styles.navBtn, ...(activeTab === 'chat' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquare size={18} />
            <span>Communication Link</span>
          </button>
          
          <button 
            style={{...styles.navBtn, ...(activeTab === 'config' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('config')}
          >
            <Settings size={18} />
            <span>Core Parameters</span>
          </button>
          
          <button 
            style={{...styles.navBtn, ...(activeTab === 'logs' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('logs')}
          >
            <Terminal size={18} />
            <span>Decision Logs</span>
          </button>
          
          <button 
            style={{...styles.navBtn, ...(activeTab === 'activity' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('activity')}
          >
            <Activity size={18} />
            <span>Activity Logs</span>
          </button>
          
          <button 
            style={{...styles.navBtn, ...(activeTab === 'memory' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('memory')}
          >
            <Database size={18} />
            <span>Memory Vault (RAG)</span>
          </button>
          
          <button 
            style={{...styles.navBtn, ...(activeTab === 'tools' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('tools')}
          >
            <Wrench size={18} />
            <span>Core Tools</span>
          </button>

          <button 
            style={{...styles.navBtn, ...(activeTab === 'subagents' ? styles.navBtnActive : {})}}
            onClick={() => {
              setActiveTab('subagents');
              selectChat(currentChatId === 'dashboard' ? 'dashboard' : currentChatId);
            }}
          >
            <Layers size={18} />
            <span>Sub-agents</span>
          </button>

          <button 
            style={{...styles.navBtn, ...(activeTab === 'network' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('network')}
          >
            <Network size={18} />
            <span>Architecture</span>
          </button>

          <button 
            style={{...styles.navBtn, ...(activeTab === 'mcp' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('mcp')}
          >
            <Server size={18} />
            <span>MCP Servers</span>
          </button>

          <button 
            style={{...styles.navBtn, ...(activeTab === 'obsidian' ? styles.navBtnActive : {})}}
            onClick={() => setActiveTab('obsidian')}
          >
            <BookOpen size={18} />
            <span>Obsidian</span>
          </button>
        </nav>

        {/* Sidebar Status Info */}
        <div style={styles.statusBox} className="glass-panel">
          <div style={styles.statusRow}>
            <span style={styles.statusLabel}>Onboard Network:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className={`pulse-dot ${isConnected ? '' : 'danger'}`} />
              <span style={{ fontSize: '0.85rem', color: isConnected ? '#10b981' : '#ef4444' }}>
                {isConnected ? 'ACTIVE' : 'DISCONNECTED'}
              </span>
            </div>
          </div>
          
          <div style={styles.statusRow}>
            <span style={styles.statusLabel}>LLM Core:</span>
            <div style={styles.modelTag}>
              <Cpu size={12} style={{ color: '#00f0ff' }} />
              <span style={styles.modelName}>{config.model.split('/').pop()}</span>
            </div>
          </div>
          
          <div style={styles.statusRow}>
            <span style={styles.statusLabel}>Call logs:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: '#00f0ff' }}>
              {logs.length} logs
            </span>
          </div>
        </div>
      </aside>

      {/* 2. Main Workspace */}
      <main style={styles.mainContent}>
        {activeTab === 'chat' && (
          <ChatTab
            currentChatId={currentChatId}
            chatSessions={chatSessions}
            messages={messages}
            inputValue={inputValue}
            setInputValue={setInputValue}
            isSpeaking={isSpeaking}
            setIsSpeaking={setIsSpeaking}
            micState={micState}
            micEnabled={micEnabled}
            setMicEnabled={setMicEnabled}
            isTTSEnabled={isTTSEnabled}
            setIsTTSEnabled={setIsTTSEnabled}
            isGenerating={isGenerating}
            playingMsgIndex={playingMsgIndex}
            setPlayingMsgIndex={setPlayingMsgIndex}
            config={config}
            isConnected={isConnected}
            isUploading={isUploading}
            speakText={speakText}
            handleClearChat={handleClearChat}
            handleSendMessage={handleSendMessage}
            handleFileUpload={handleFileUpload}
            selectChat={selectChat}
            handleCreateNewSession={handleCreateNewSession}
            fetchChatSessions={fetchChatSessions}
            getSessionLabel={getSessionLabel}
            mainChatEndRef={mainChatEndRef}
          />
        )}

        {activeTab === 'config' && (
          <ConfigTab
            editedModel={editedModel}
            setEditedModel={setEditedModel}
            editedPrompt={editedPrompt}
            setEditedPrompt={setEditedPrompt}
            isSavingConfig={isSavingConfig}
            handleSaveConfig={handleSaveConfig}
            models={models}
          />
        )}

        {activeTab === 'logs' && (
          <LogsTab
            logs={logs}
            selectedLog={selectedLog}
            setSelectedLog={setSelectedLog}
          />
        )}

        {activeTab === 'activity' && (
          <ActivityTab
            isGenerating={isGenerating}
            priceAlerts={priceAlerts}
            activityLogs={activityLogs}
            handleClearActivityLogs={handleClearActivityLogs}
          />
        )}

        {activeTab === 'memory' && (
          <MemoryTab
            noteTitle={noteTitle}
            setNoteTitle={setNoteTitle}
            noteContent={noteContent}
            setNoteContent={setNoteContent}
            isIndexing={isIndexing}
            documents={documents}
            memorySearchQuery={memorySearchQuery}
            setMemorySearchQuery={setMemorySearchQuery}
            isSearchingMemory={isSearchingMemory}
            memorySearchResults={memorySearchResults}
            handleIndexNote={handleIndexNote}
            handleSearchMemory={handleSearchMemory}
            handleClearMemorySearch={handleClearMemorySearch}
            handleDeleteDocument={handleDeleteDocument}
          />
        )}

        {activeTab === 'tools' && (
          <ToolsTab
            systemStats={systemStats}
            uploads={uploads}
            timers={timers}
            handleCancelTimer={handleCancelTimer}
          />
        )}

        {activeTab === 'subagents' && (
          <SubagentsTab
            currentChatId={currentChatId}
            subagents={subagents}
            messages={messages}
            inputValue={inputValue}
            setInputValue={setInputValue}
            isSpeaking={isSpeaking}
            setIsSpeaking={setIsSpeaking}
            isGenerating={isGenerating}
            playingMsgIndex={playingMsgIndex}
            setPlayingMsgIndex={setPlayingMsgIndex}
            config={config}
            isConnected={isConnected}
            newAgentId={newAgentId}
            setNewAgentId={setNewAgentId}
            newAgentName={newAgentName}
            setNewAgentName={setNewAgentName}
            newAgentPrompt={newAgentPrompt}
            setNewAgentPrompt={setNewAgentPrompt}
            newAgentModel={newAgentModel}
            setNewAgentModel={setNewAgentModel}
            newAgentSkills={newAgentSkills}
            setNewAgentSkills={setNewAgentSkills}
            newAgentTemperature={newAgentTemperature}
            setNewAgentTemperature={setNewAgentTemperature}
            isCreatingAgent={isCreatingAgent}
            editingAgentId={editingAgentId}
            setEditingAgentId={setEditingAgentId}
            editAgentName={editAgentName}
            setEditAgentName={setEditAgentName}
            editAgentPrompt={editAgentPrompt}
            setEditAgentPrompt={setEditAgentPrompt}
            editAgentModel={editAgentModel}
            setEditAgentModel={setEditAgentModel}
            editAgentSkills={editAgentSkills}
            setEditAgentSkills={setEditAgentSkills}
            editAgentTemperature={editAgentTemperature}
            setEditAgentTemperature={setEditAgentTemperature}
            isUpdatingAgent={isUpdatingAgent}
            speakText={speakText}
            handleSendMessage={handleSendMessage}
            selectChat={selectChat}
            handleCreateSubagent={handleCreateSubagent}
            handleUpdateSubagent={handleUpdateSubagent}
            handleDeleteSubagent={handleDeleteSubagent}
            setCurrentChatId={setCurrentChatId}
            subagentChatEndRef={subagentChatEndRef}
            models={models}
          />
        )}

        {activeTab === 'obsidian' && (
          <ObsidianTab authToken={localStorage.getItem('jarvis_auth_token')} />
        )}

        {activeTab === 'network' && (
          <NetworkTab subagents={subagents} setSubagents={setSubagents} fetchSubagents={fetchSubagents} />
        )}

        {activeTab === 'mcp' && (
          <MCPTab />
        )}
      </main>

      {/* New Session Custom Modal */}
      {showNewSessionModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          backgroundColor: 'rgba(6, 9, 19, 0.85)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            width: '400px',
            padding: '24px',
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid rgba(0, 240, 255, 0.3)',
            borderRadius: '12px',
            boxShadow: '0 0 25px rgba(0, 240, 255, 0.25)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px'
          }}>
            <div>
              <h3 style={{ fontSize: '1.2rem', color: '#fff', fontWeight: 600, marginBottom: '4px', letterSpacing: '0.5px' }} className="glow-text-cyan">
                CREATE NEW CHAT
              </h3>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Enter name for the new chat session
              </p>
            </div>
            
            <input 
              type="text"
              value={newSessionNameInput}
              onChange={(e) => setNewSessionNameInput(e.target.value)}
              placeholder="e.g. Oil Market Analysis"
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '8px',
                border: '1px solid rgba(255,255,255,0.1)',
                backgroundColor: 'rgba(0,0,0,0.3)',
                color: '#fff',
                fontSize: '0.9rem',
                outline: 'none',
                transition: 'border-color 0.2s'
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleCreateNewSessionConfirm(newSessionNameInput);
                  setShowNewSessionModal(false);
                }
              }}
              autoFocus
            />

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
              <button 
                onClick={() => setShowNewSessionModal(false)}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: '1px solid rgba(255,255,255,0.1)',
                  backgroundColor: 'transparent',
                  color: 'var(--text-dim)',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  fontWeight: 600
                }}
              >
                Cancel
              </button>
              <button 
                onClick={() => {
                  handleCreateNewSessionConfirm(newSessionNameInput);
                  setShowNewSessionModal(false);
                }}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: '1px solid rgba(0, 240, 255, 0.4)',
                  backgroundColor: 'rgba(0, 240, 255, 0.1)',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  fontWeight: 600
                }}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
