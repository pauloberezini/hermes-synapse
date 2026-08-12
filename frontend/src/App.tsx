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
  Server,
  Clock,
  Menu,
  X,
  BarChart3,
  Building2,
  LogOut,
  Kanban,
  ShieldCheck,
  Rss
} from 'lucide-react';

import type { ChatMessage, DecisionLog, ActivityLog, SystemConfig, AppSettings, ChatSession } from './types';

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
import { ScheduleTab } from './components/ScheduleTab';
import { SubagentsTab } from './components/SubagentsTab';
import { ObsidianTab } from './components/ObsidianTab';
import { NetworkTab } from './components/NetworkTab';
import { MCPTab } from './components/MCPTab';
import { MetricsTab } from './components/MetricsTab';
import { OfficeTab, type OfficeLiveTrace } from './components/OfficeTab';
import { TaskBoardTab } from './components/TaskBoardTab';
import { RSSTab } from './components/RSSTab';
import { AgentSelect } from './components/AgentSelect';

// Initialize global fetch interceptor
initFetchInterceptor();

// Safe localStorage helper to prevent exceptions in private mode or non-browser environments
const getSafeStorageItem = (key: string): string | null => {
  try {
    return typeof window !== 'undefined' && window.localStorage ? localStorage.getItem(key) : null;
  } catch {
    return null;
  }
};

const setSafeStorageItem = (key: string, value: string): void => {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      localStorage.setItem(key, value);
    }
  } catch {
    // Ignore quota or access errors gracefully
  }
};

// Static BCP-47 locale map — defined at module level so hooks don't need it as a dep
const langToLocale: Record<string, string> = {
  ru: 'ru-RU', en: 'en-US', he: 'he-IL', de: 'de-DE', es: 'es-ES', fr: 'fr-FR'
};

export default function App() {
  const [isOfficeEnabled, setIsOfficeEnabled] = useState<boolean>(() => {
    const saved = getSafeStorageItem('jarvis_pixel_office_enabled');
    return saved !== null ? saved === 'true' : false;
  });

  const [activeTab, setActiveTab] = useState<'chat' | 'office' | 'tasks' | 'schedule' | 'config' | 'logs' | 'metrics' | 'activity' | 'memory' | 'tools' | 'subagents' | 'obsidian' | 'network' | 'mcp' | 'rss'>(() => {
    const saved = getSafeStorageItem('jarvis_active_tab');
    const officeEnabled = getSafeStorageItem('jarvis_pixel_office_enabled') === 'true';
    if (saved === 'office' && !officeEnabled) return 'chat';
    return (saved as any) || 'chat';
  });

  const handleToggleOfficeEnabled = (enabled: boolean) => {
    setIsOfficeEnabled(enabled);
    setSafeStorageItem('jarvis_pixel_office_enabled', String(enabled));
    if (!enabled && activeTab === 'office') {
      setActiveTab('chat');
    }
  };
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const sidebarLeaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([{ id: 'dashboard', title: 'Main Terminal' }]);
  const [isConnected, setIsConnected] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!getSafeStorageItem('jarvis_auth_token'));
  const [otpCode, setOtpCode] = useState('');
  const [authStatus, setAuthStatus] = useState<'idle' | 'sending' | 'sent' | 'verifying' | 'error' | 'success'>('idle');
  const [authError, setAuthError] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: 'Greetings, Sir. Connection to the Synapse network is complete. Awaiting your instructions.' }
  ]);
  const [logs, setLogs] = useState<DecisionLog[]>([]);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [isMetricsLoading, setIsMetricsLoading] = useState(false);
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
  const [timers, setTimers] = useState<{ id: string; label: string; duration?: number; time_left: number; status: string; created_at: string; type?: string; target_time?: string; interval_hours?: number; fire_count?: number; agent_id?: string; prompt?: string }[]>([]);
  const [systemStats, setSystemStats] = useState<{ cpu_load_percent: number; ram_used_percent: number; ram_total_gb: number; disk_used_percent: number; disk_total_gb: number; disk_used_gb: number; status: string } | null>(null);

  // Market & Price Alert States (only alerts count is kept for ActivityTab)
  const [priceAlerts, setPriceAlerts] = useState<{ id: string; symbol: string; display_name: string; target_price: number; condition: string; created_at: string }[]>([]);

  const [uploads, setUploads] = useState<{ name: string; size_bytes: number }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  // File attached to the current chat message (text context, not dataset upload)
  const [attachedFile, setAttachedFile] = useState<{ name: string; content: string; type?: string; pages?: number; truncated?: boolean } | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isTTSEnabled, setIsTTSEnabled] = useState<boolean>(() => {
    const saved = getSafeStorageItem('jarvis_tts_enabled');
    return saved !== null ? saved === 'true' : true;
  });
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [playingMsgIndex, setPlayingMsgIndex] = useState<number | null>(null);
  const [micEnabled, setMicEnabled] = useState<boolean>(() => {
    return getSafeStorageItem('jarvis_mic_enabled') === 'true';
  });
  const [micState, setMicState] = useState<'off' | 'listening' | 'capturing'>('off');
  const [timerSoundEnabled, setTimerSoundEnabled] = useState<boolean>(() => {
    const saved = getSafeStorageItem('jarvis_timer_sound_enabled');
    return saved !== null ? saved === 'true' : false;
  });

  
  const [inputValue, setInputValue] = useState('');
  const [selectedLog, setSelectedLog] = useState<DecisionLog | null>(null);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [appSettings, setAppSettings] = useState<AppSettings>({ language: 'en' });
  const appSettingsRef = useRef<AppSettings>({ language: 'en' }); // always-current ref for WS/callbacks

  // Prompt edit states
  const [editedPrompt, setEditedPrompt] = useState('');
  const [editedModel, setEditedModel] = useState('');
  
  const wsRef = useRef<WebSocket | null>(null);
  const mainChatEndRef = useRef<HTMLDivElement | null>(null);
  const subagentChatEndRef = useRef<HTMLDivElement | null>(null);
  const lastSentTimeRef = useRef<number>(0);
  const ttsEnabledRef = useRef(isTTSEnabled);       // ref so WS handler always sees current value
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
  const [currentChatId, setCurrentChatId] = useState<string>(() => {
    return getSafeStorageItem('jarvis_current_chat_id') || 'dashboard';
  });
  const currentChatIdRef = useRef(getSafeStorageItem('jarvis_current_chat_id') || 'dashboard');
  
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
  const [newSessionAgentInput, setNewSessionAgentInput] = useState('jarvis');

  const [editingAgentId, setEditingAgentId] = useState('');
  const [editAgentName, setEditAgentName] = useState('');
  const [editAgentPrompt, setEditAgentPrompt] = useState('');
  const [editAgentModel, setEditAgentModel] = useState('google/gemini-2.5-flash');
  const [editAgentSkills, setEditAgentSkills] = useState('');
  const [editAgentTemperature, setEditAgentTemperature] = useState(0.7);
  const [isUpdatingAgent, setIsUpdatingAgent] = useState(false);
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [officeLiveTrace, setOfficeLiveTrace] = useState<OfficeLiveTrace | null>(null);

  useEffect(() => {
    currentChatIdRef.current = currentChatId;
    setSafeStorageItem('jarvis_current_chat_id', currentChatId);
  }, [currentChatId]);

  useEffect(() => {
    setSafeStorageItem('jarvis_active_tab', activeTab);
  }, [activeTab]);

  // Keep ttsEnabledRef in sync with its state and save to localStorage
  useEffect(() => { 
    ttsEnabledRef.current = isTTSEnabled; 
    setSafeStorageItem('jarvis_tts_enabled', String(isTTSEnabled));
  }, [isTTSEnabled]);

  useEffect(() => {
    setSafeStorageItem('jarvis_mic_enabled', String(micEnabled));
  }, [micEnabled]);
  useEffect(() => {
    setSafeStorageItem('jarvis_timer_sound_enabled', String(timerSoundEnabled));
  }, [timerSoundEnabled]);
  useEffect(() => { appSettingsRef.current = appSettings; }, [appSettings]);


  // Open Settings dropdown automatically if a settings sub-tab is active
  useEffect(() => {
    if (['config', 'subagents', 'mcp', 'obsidian', 'logs', 'activity', 'memory', 'tools', 'rss'].includes(activeTab)) {
      setSettingsOpen(true);
    }
  }, [activeTab]);

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
    const locale = langToLocale[appSettingsRef.current.language] || 'ru-RU';
    utter.lang = locale;
    utter.rate = 1.05;
    utter.pitch = 0.95;

    // Prefer a native voice for the selected language
    const voices = window.speechSynthesis.getVoices();
    const langVoices = voices.filter(v => v.lang.startsWith(appSettingsRef.current.language));
    const maleVoice = langVoices.find(v =>
      v.name.toLowerCase().includes('yuri') ||
      v.name.toLowerCase().includes('pavel') ||
      v.name.toLowerCase().includes('male') ||
      v.name.toLowerCase().includes('boris')
    );
    if (maleVoice) {
      utter.voice = maleVoice;
    } else if (langVoices.length > 0) {
      utter.voice = langVoices[langVoices.length - 1];
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
    recognition.lang = langToLocale[appSettings.language] || 'ru-RU';
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
  }, [micEnabled, appSettings.language]);


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

  const fetchWithAuth = useCallback((url: string, options: RequestInit = {}) => {
    const token = localStorage.getItem('jarvis_auth_token');
    const headers = {
      ...options.headers,
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    };

    let relativeUrl = url;
    if (url.startsWith('http://localhost:8000/api')) {
      relativeUrl = url.replace('http://localhost:8000', '');
    }

    const doFetch = (targetUrl: string) => fetch(targetUrl, { ...options, headers }).then(res => {
      if (res.status === 401) {
        localStorage.removeItem('jarvis_auth_token');
        setIsAuthenticated(false);
      }
      return res;
    });

    return doFetch(relativeUrl).catch((firstErr) => {
      if (relativeUrl !== url) {
        return doFetch(url);
      }
      throw firstErr;
    });
  }, []);

  const fetchChatSessions = useCallback(() => {
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/history/sessions')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => {
        if (Array.isArray(data)) {
          setChatSessions(data);
        }
      })
      .catch(err => console.log('Error fetching sessions:', err));
  }, [isAuthenticated, fetchWithAuth]);

  const fetchTimersData = useCallback(() => {
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/timers')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => { if (Array.isArray(data)) setTimers(data); })
      .catch(err => console.log('Error fetching timers:', err));
  }, [isAuthenticated, fetchWithAuth]);


  const handleRequestOtp = async () => {
    setAuthStatus('sending');
    setAuthError('');
    try {
      let res: Response;
      try {
        res = await fetch('/api/auth/request-code', { method: 'POST' });
        if (!res.ok && res.status === 404) throw new Error('404');
      } catch (firstErr) {
        res = await fetch('http://localhost:8000/api/auth/request-code', { method: 'POST' });
      }
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
      let res: Response;
      try {
        res = await fetch('/api/auth/verify-code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code })
        });
        if (!res.ok && res.status === 404) throw new Error('404');
      } catch (firstErr) {
        res = await fetch('http://localhost:8000/api/auth/verify-code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code })
        });
      }
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

  const handleLogout = useCallback(() => {
    localStorage.removeItem('jarvis_auth_token');
    setIsAuthenticated(false);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setAuthStatus('idle');
  }, []);

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
                cost_usd: data.cost_usd,
                timestamp: data.timestamp || new Date().toISOString()
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
            fetchChatSessions();
          } else if (data.type === 'scheduled_task_executed') {
            fetchChatSessions();
            fetchTimersData();
            if (data.session_id && data.session_id === currentChatIdRef.current) {
              fetchWithAuth(`http://localhost:8000/api/history/${data.session_id}`)
                .then(res => res.ok ? res.json() : Promise.reject(res))
                .then(msgs => { if (Array.isArray(msgs)) setMessages(msgs); })
                .catch(err => console.error('Error refreshing session history on task exec:', err));
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
          } else if (data.type === 'session_title_update') {
            setChatSessions((prev) =>
              prev.map((s) => (s.id === data.chat_id ? { ...s, title: data.title } : s))
            );
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
          } else if (data.type === 'settings_update') {
            setAppSettings({ language: data.language });
          } else if (data.type === 'timer_completed') {
            setTimers((prev) => {
              const exists = prev.some(t => t.id === data.timer.id);
              if (exists) {
                return prev.map(t => t.id === data.timer.id ? { ...t, status: 'completed', time_left: 0 } : t);
              }
              return [...prev, { ...data.timer, time_left: 0, status: 'completed' }];
            });
            fetchChatSessions();
            fetchTimersData();
            if (data.session_id && data.session_id === currentChatIdRef.current) {
              fetchWithAuth(`http://localhost:8000/api/history/${data.session_id}`)
                .then(res => res.ok ? res.json() : Promise.reject(res))
                .then(msgs => { if (Array.isArray(msgs)) setMessages(msgs); })
                .catch(err => console.error('Error refreshing session history on timer completed:', err));
            }
            if (timerSoundEnabled) {
              playAlarmSound();
              speakText(`Sir, the timer "${data.timer.label}" is complete.`);
            }
          } else if (data.type === 'alarm_fired') {
            setTimers((prev) => {
              const exists = prev.some(t => t.id === data.alarm.id);
              if (exists) {
                return prev.map(t => t.id === data.alarm.id ? { ...t, status: 'completed', time_left: 0 } : t);
              }
              return [...prev, { ...data.alarm, time_left: 0, status: 'completed' }];
            });
            fetchChatSessions();
            fetchTimersData();
            if (data.session_id && data.session_id === currentChatIdRef.current) {
              fetchWithAuth(`http://localhost:8000/api/history/${data.session_id}`)
                .then(res => res.ok ? res.json() : Promise.reject(res))
                .then(msgs => { if (Array.isArray(msgs)) setMessages(msgs); })
                .catch(err => console.error('Error refreshing session history on alarm fired:', err));
            }
            if (timerSoundEnabled) {
              playAlarmSound();
              speakText(`Sir, the alarm "${data.alarm.label}" has gone off.`);
            }

          } else if (data.type === 'reminder_fired') {
            if (data.reminder && data.reminder.id) {
              setTimers((prev) => {
                const exists = prev.some(t => t.id === data.reminder.id);
                if (exists) {
                  return prev.map(t => t.id === data.reminder.id ? { ...t, ...data.reminder } : t);
                }
                return [...prev, data.reminder];
              });
            }
            fetchChatSessions();
            fetchTimersData();
            if (data.session_id && data.session_id === currentChatIdRef.current) {
              fetchWithAuth(`http://localhost:8000/api/history/${data.session_id}`)
                .then(res => res.ok ? res.json() : Promise.reject(res))
                .then(msgs => { if (Array.isArray(msgs)) setMessages(msgs); })
                .catch(err => console.error('Error refreshing session history on reminder fired:', err));
            }
          } else if (data.type === 'trace_update') {

            if (data.trace.agent !== 'Router') {
              setMessages((prev) => [...prev, {
                role: 'system',
                content: `⚙️ [${data.trace.agent}] ${data.trace.action}: ${data.trace.message.split('\n')[0]}`
              }]);
              setOfficeLiveTrace({
                agent: data.trace.agent,
                action: data.trace.action,
                message: data.trace.message,
                status: data.trace.status,
                ts: Date.now(),
              });
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
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/documents')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => { if (Array.isArray(data)) setDocuments(data); })
      .catch(err => console.log('Error fetching documents:', err));
  };

  const fetchMetrics = () => {
    if (!isAuthenticated) return;
    setIsMetricsLoading(true);
    fetchWithAuth('http://localhost:8000/api/metrics')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => {
        setMetrics(data);
        setIsMetricsLoading(false);
      })
      .catch(err => {
        console.log('Error fetching metrics:', err);
        setIsMetricsLoading(false);
      });
  };

  useEffect(() => {
    if (isAuthenticated && activeTab === 'metrics') {
      fetchMetrics();
    }
  }, [activeTab, isAuthenticated]);

  const fetchUploads = () => {
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/uploads')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => { if (Array.isArray(data)) setUploads(data); })
      .catch(err => console.log('Error fetching uploads:', err));
  };


  const getSessionLabel = (id: string) => {
    if (id === 'dashboard') return 'Main Terminal';
    const found = chatSessions.find(s => s.id === id);
    if (found && found.title) return found.title;
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

  const handleCreateNewSessionConfirm = async (name: string, agentId: string = 'jarvis') => {
    let sessionId = '';
    const trimmed = name.trim();
    if (trimmed) {
      const sanitized = trimmed.toLowerCase().replace(/[^a-z0-9а-яё_-]/g, '_');
      sessionId = `chat_${sanitized}_${Date.now().toString().slice(-4)}`;
    } else {
      sessionId = `chat_${Date.now()}`;
    }
    
    try {
      await fetchWithAuth(`http://localhost:8000/api/history/${sessionId}/agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId })
      });
    } catch (e) {
      console.error('Error setting session agent on creation:', e);
    }

    if (trimmed) {
      try {
        await fetchWithAuth(`http://localhost:8000/api/history/${sessionId}/rename`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: trimmed })
        });
      } catch (e) {
        console.error('Error renaming session on creation:', e);
      }
    }
    
    fetchChatSessions();
    setTimeout(() => selectChat(sessionId), 100);
  };

  const handleCreateNewSession = () => {
    setNewSessionNameInput('');
    setNewSessionAgentInput('jarvis');
    setShowNewSessionModal(true);
  };

  const handleSetSessionAgent = async (sessionId: string, agentId: string) => {
    try {
      const res = await fetchWithAuth(`http://localhost:8000/api/history/${sessionId}/agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId })
      });
      if (res.ok) {
        setChatSessions(prev =>
          prev.map(s => s.id === sessionId ? { ...s, agent_id: agentId } : s)
        );
      }
    } catch (e) {
      console.error('Error updating session agent:', e);
    }
  };

  const fetchSubagents = () => {
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/subagents')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => { if (Array.isArray(data)) setSubagents(data); })
      .catch(err => console.log('Error fetching subagents:', err));
  };

  const selectChat = (chatId: string, currentSubagentsList?: any[]) => {
    const listToSearch = Array.isArray(currentSubagentsList) ? currentSubagentsList : (Array.isArray(subagents) ? subagents : []);
    setCurrentChatId(chatId);
    setMessages([]); // clear temporarily
    fetchWithAuth(`http://localhost:8000/api/history/${chatId}`)
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setMessages(data);
        } else {
          if (chatId === 'dashboard') {
            setMessages([{ role: 'assistant', content: 'Greetings, Sir. Connection to the Synapse network is complete. Awaiting your instructions.' }]);
          } else {
            const agent = listToSearch.find((a: any) => a.id === chatId);
            if (chatId.startsWith('chat_')) {
              setMessages([{ role: 'assistant', content: 'Conversation initialized, Sir. How can I assist you today?' }]);
            } else if (chatId.startsWith('task_')) {
              const label = getSessionLabel(chatId);
              const displayTitle = (label && label !== chatId) ? label : 'Scheduled Automation Task';
              setMessages([{ role: 'assistant', content: `Scheduled task session "${displayTitle}" initialized, Sir. Ready for work.` }]);
            } else {
              setMessages([{ role: 'assistant', content: `Sub-agent session "${agent?.name || getSessionLabel(chatId)}" initialized, Sir. Ready for work.` }]);
            }
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
      const res = await fetchWithAuth('http://localhost:8000/api/subagents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
        
        fetchWithAuth('http://localhost:8000/api/subagents')
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
      const res = await fetchWithAuth(`http://localhost:8000/api/subagents/${id}`, {
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
      const res = await fetchWithAuth('http://localhost:8000/api/subagents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
        fetchWithAuth('http://localhost:8000/api/subagents')
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

  const handleCancelTimer = (id: string) => {
    fetchWithAuth(`http://localhost:8000/api/timers/${id}`, {
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
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/market/alerts')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => { if (Array.isArray(data)) setPriceAlerts(data); })
      .catch(err => console.log('Error fetching market alerts:', err));
  };

  const handleClearActivityLogs = () => {
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/activity/logs', {
      method: 'DELETE'
    })
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => {
        if (data && data.status === 'success') {
          setActivityLogs([]);
        }
      })
      .catch(err => console.log('Error clearing activity logs:', err));
  };

  const fetchModels = () => {
    if (!isAuthenticated) return;
    fetchWithAuth('http://localhost:8000/api/models')
      .then(res => res.ok ? res.json() : Promise.reject(res))
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

    fetchWithAuth('http://localhost:8000/api/config')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => {
        if (data && data.system_prompt !== undefined) {
          setConfig(data);
          setEditedPrompt(data.system_prompt);
          setEditedModel(data.model);
        }
      })
      .catch(() => console.log('REST config fetch skipped/failed (using WS instead)'));

    fetchWithAuth('http://localhost:8000/api/logs')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => {
        if (Array.isArray(data)) {
          setLogs(data);
        }
      })
      .catch(() => console.log('REST logs fetch skipped/failed'));
      
    fetchMetrics();
      
    fetchDocuments();
    fetchUploads();
    fetchSubagents();
    fetchChatSessions();
    fetchModels();

    fetchWithAuth('http://localhost:8000/api/settings')
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then(data => { if (data?.language) setAppSettings({ language: data.language }); })
      .catch(() => {});
    
    if (isAuthenticated) {
      const savedChatId = localStorage.getItem('jarvis_current_chat_id') || 'dashboard';
      selectChat(savedChatId);
    }
  }, [isAuthenticated]);

  // Fetch timers and subagents whenever the 'schedule', 'network', 'tasks', or 'subagents' tab is active
  useEffect(() => {
    if (!isAuthenticated) return;
    if (activeTab === 'schedule' || activeTab === 'network' || activeTab === 'tasks' || activeTab === 'subagents') {
      fetchSubagents();
    }
    if (activeTab !== 'schedule') return;

    const fetchTimersData = () => {
      fetchWithAuth('http://localhost:8000/api/timers')
        .then(res => res.ok ? res.json() : Promise.reject(res))
        .then(data => { if (Array.isArray(data)) setTimers(data); })
        .catch(err => console.log('Error fetching timers:', err));
    };

    fetchTimersData();
    const timersInterval = setInterval(fetchTimersData, 3000);
    return () => clearInterval(timersInterval);
  }, [activeTab, isAuthenticated]);

  // Fetch system stats, uploads, and market data when the "tools" tab is active
  useEffect(() => {
    if (!isAuthenticated || activeTab !== 'tools') return;

    const fetchStats = () => {
      fetchWithAuth('http://localhost:8000/api/system/stats')
        .then(res => res.ok ? res.json() : Promise.reject(res))
        .then(data => setSystemStats(data))
        .catch(err => console.log('Error fetching system stats:', err));
    };

    const fetchTimersData = () => {
      fetchWithAuth('http://localhost:8000/api/timers')
        .then(res => res.ok ? res.json() : Promise.reject(res))
        .then(data => { if (Array.isArray(data)) setTimers(data); })
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
          if (timer.status === 'running' && timer.time_left <= 0 && timer.type === 'recurring' && timer.interval_hours) {
            return { ...timer, time_left: Math.round(timer.interval_hours * 3600) };
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
      const res = await fetchWithAuth('http://localhost:8000/api/documents', {
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
      const res = await fetchWithAuth(`http://localhost:8000/api/documents/${docId}`, {
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
      const res = await fetchWithAuth(`http://localhost:8000/api/documents/search?q=${encodeURIComponent(memorySearchQuery)}`);
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

  // Handle attaching a file to the current chat message.
  // – PDF: sent to backend /api/parse-pdf for server-side text extraction (limit 500 KB text).
  // – Other text formats: read client-side via FileReader (limit 150 KB).
  const handleChatFileAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ''; // reset so the same file can be reselected after removal

    const isPdf = file.name.toLowerCase().endsWith('.pdf');

    if (isPdf) {
      // ── PDF path: server-side extraction ─────────────────────────────────────
      const MAX_PDF_MB = 25; // raw file size guard before sending to server
      if (file.size > MAX_PDF_MB * 1024 * 1024) {
        alert(`PDF "${file.name}" exceeds ${MAX_PDF_MB} MB. Please use a smaller file.`);
        return;
      }
      setIsUploading(true);
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetchWithAuth('http://localhost:8000/api/parse-pdf', {
          method: 'POST',
          body: form,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
          alert(`PDF parse failed: ${err.detail}`);
          return;
        }
        const data = await res.json();
        setAttachedFile({
          name: file.name,
          content: data.text,
          type: 'pdf',
          pages: data.pages,
          truncated: data.truncated,
        });
      } catch (err) {
        console.error('PDF parse error:', err);
        alert('Could not connect to backend to parse PDF.');
      } finally {
        setIsUploading(false);
      }
    } else {
      // ── Text path: client-side FileReader ────────────────────────────────────
      const MAX_TEXT_BYTES = 150 * 1024; // 150 KB
      if (file.size > MAX_TEXT_BYTES) {
        alert(`File "${file.name}" is too large for inline chat context (max 150 KB). Use the Memory tab to index it into the knowledge base instead.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = (evt) => {
        const content = evt.target?.result as string;
        setAttachedFile({ name: file.name, content, type: 'text' });
      };
      reader.onerror = () => {
        alert(`Failed to read file "${file.name}".`);
      };
      reader.readAsText(file, 'utf-8');
    }
  };

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

    const payload: Record<string, unknown> = {
      type: 'chat_message',
      content: inputValue,
      chat_id: currentChatId
    };
    if (attachedFile) {
      payload.attached_file = attachedFile;
    }

    wsRef.current.send(JSON.stringify(payload));

    setIsGenerating(true);
    setInputValue('');
    setAttachedFile(null);
  };

  const handleClearChat = async () => {
    if (!window.confirm('Sir, are you sure you want to completely clear the history of this session?')) return;
    
    setMessages([]);
    try {
      const res = await fetchWithAuth(`http://localhost:8000/api/history/${currentChatId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchChatSessions();
        if (currentChatId === 'dashboard') {
          setMessages([{ role: 'assistant', content: 'Greetings, Sir. Connection to the Synapse network is complete. Awaiting your instructions.' }]);
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
      const response = await fetchWithAuth('http://localhost:8000/api/config', {
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
      <div className="cyber-auth-container">
        <div className="cyber-grid-overlay" />
        <div className="cyber-auth-card">
          {/* Top Cyber HUD Header */}
          <div className="cyber-hud-header">
            <span>[ SYSTEM // SYNAPSE ]</span>
            <div className="cyber-status-badge">
              <span className="pulse-dot" style={{ width: 6, height: 6, background: '#ff007f', boxShadow: '0 0 8px #ff007f' }} />
              <span>SEC_LEVEL: ALPHA</span>
            </div>
          </div>
          
          <div style={{ marginBottom: '24px' }}>
            <h1 className="cyber-title">SYNAPSE</h1>
            <div className="cyber-subtitle">Secure Access Link // Protocol v2.5</div>
          </div>

          <div className="cyber-description">
            Sir, identity confirmation is required to access the management console.
          </div>

          {authStatus === 'idle' && (
            <button
              onClick={handleRequestOtp}
              className="cyber-btn"
            >
              <ShieldCheck size={18} />
              Request code in Telegram
            </button>
          )}

          {authStatus === 'sending' && (
            <div style={{ color: '#00f0ff', fontSize: '0.9rem', fontFamily: 'monospace', padding: '16px 0' }}>
              ⚡ INITIALIZING NEURAL LINK & SENDING CODE...
            </div>
          )}

          {(authStatus === 'sent' || authStatus === 'verifying' || authStatus === 'error') && (
            <form onSubmit={handleVerifyOtp} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ color: '#34d399', fontSize: '0.85rem', fontFamily: 'monospace', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '8px 12px', borderRadius: '6px' }}>
                ✓ Authorization code sent to your trusted Telegram chat.
              </div>
              
              <input
                type="text"
                maxLength={6}
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="0 0 0 0 0 0"
                className="cyber-input-otp"
                disabled={authStatus === 'verifying'}
                autoFocus
              />

              {authError && (
                <div style={{ color: '#f87171', fontSize: '0.85rem', fontFamily: 'monospace', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', padding: '8px 12px', borderRadius: '6px' }}>
                  ⚠️ {authError}
                </div>
              )}

              {authStatus === 'verifying' && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', padding: '8px 0' }}>
                  <span className="pulse-dot" style={{ width: 8, height: 8, background: '#00f0ff', boxShadow: '0 0 10px #00f0ff' }} />
                  <span style={{ color: '#00f0ff', fontSize: '0.9rem', fontFamily: 'monospace', letterSpacing: '2px' }}>DECRYPTING OTP CODE...</span>
                </div>
              )}

              <button
                type="button"
                onClick={handleRequestOtp}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#64748b',
                  fontSize: '0.8rem',
                  fontFamily: 'monospace',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  marginTop: '6px'
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
    <div className={`app-container scanlines${activeTab === 'office' ? ' is-office-mode' : ''}`}>
      {/* Mobile Menu Toggle Button */}
      <button 
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="mobile-menu-btn"
        style={{
          position: 'fixed',
          top: '16px',
          left: '16px',
          zIndex: 1100,
          background: 'rgba(12, 17, 34, 0.8)',
          border: '1px solid rgba(0, 240, 255, 0.3)',
          color: 'var(--accent-cyan)',
          padding: '8px',
          borderRadius: '8px',
          cursor: 'pointer',
          display: 'none',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 10px rgba(0, 240, 255, 0.1)',
          backdropFilter: 'blur(4px)'
        }}
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Sidebar Overlay for Mobile */}
      {sidebarOpen && (
        <div 
          onClick={() => setSidebarOpen(false)}
          className="sidebar-overlay"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            backgroundColor: 'rgba(6, 9, 19, 0.6)',
            backdropFilter: 'blur(4px)',
            zIndex: 999,
            display: 'none'
          }}
        />
      )}

      {/* 1. Left Sidebar — hover to expand */}
      <aside
        className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''} ${sidebarExpanded ? 'sidebar-expanded' : ''}`}
        onMouseEnter={() => {
          if (sidebarLeaveTimerRef.current) clearTimeout(sidebarLeaveTimerRef.current);
          setSidebarExpanded(true);
        }}
        onMouseLeave={() => {
          sidebarLeaveTimerRef.current = setTimeout(() => {
            setSidebarExpanded(false);
            setSettingsOpen(false);
          }, 120);
        }}
      >
        {/* Logo Area */}
        <div className="sidebar-logo">
          <div className="pulse-dot" style={{ width: 12, height: 12, flexShrink: 0 }} />
          <span className="sidebar-label sidebar-logo-text">SYNAPSE</span>
        </div>
        <p className="sidebar-label sidebar-version">SYSTEM CONSOLE v1.1.0</p>

        {/* Navigation */}
        <nav className="sidebar-nav">
          <button
            className={`sidebar-nav-btn${activeTab === 'chat' ? ' active' : ''}`}
            onClick={() => { setActiveTab('chat'); setSidebarOpen(false); setSidebarExpanded(false); }}
            title="Communication Link"
          >
            <MessageSquare size={18} className="sidebar-icon" />
            <span className="sidebar-label">Communication Link</span>
          </button>

          <button
            className={`sidebar-nav-btn${activeTab === 'schedule' ? ' active' : ''}`}
            onClick={() => { setActiveTab('schedule'); setSidebarOpen(false); setSidebarExpanded(false); }}
            title="Schedules & Automation"
          >
            <Clock size={18} className="sidebar-icon" />
            <span className="sidebar-label">Schedules & Automation</span>
          </button>

          {isOfficeEnabled && (
            <button
              className={`sidebar-nav-btn${activeTab === 'office' ? ' active' : ''}`}
              onClick={() => { setActiveTab('office'); setSidebarOpen(false); setSidebarExpanded(false); }}
              title="Pixel Office"
            >
              <Building2 size={18} className="sidebar-icon" />
              <span className="sidebar-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                Pixel Office
                <span className="sidebar-badge-beta">BETA</span>
              </span>
            </button>
          )}

          <button
            className={`sidebar-nav-btn${activeTab === 'tasks' ? ' active' : ''}`}
            onClick={() => { setActiveTab('tasks'); setSidebarOpen(false); setSidebarExpanded(false); }}
            title="Task Engine"
          >
            <Kanban size={18} className="sidebar-icon" />
            <span className="sidebar-label">Task Engine</span>
          </button>

          <button
            className={`sidebar-nav-btn${activeTab === 'network' ? ' active' : ''}`}
            onClick={() => { setActiveTab('network'); setSidebarOpen(false); setSidebarExpanded(false); }}
            title="Architecture"
          >
            <Network size={18} className="sidebar-icon" />
            <span className="sidebar-label">Architecture</span>
          </button>

          {/* Settings group */}
          <button
            className={`sidebar-nav-btn${(['config','subagents','mcp','obsidian','logs','activity','memory','tools','rss','metrics'].includes(activeTab)) ? ' active' : ''}`}
            onClick={() => setSettingsOpen(prev => !prev)}
            title="Settings"
          >
            <Settings size={18} className="sidebar-icon" />
            <span className="sidebar-label" style={{ flex: 1 }}>Settings</span>
            <span className={`sidebar-label sidebar-chevron${settingsOpen ? ' open' : ''}`}>›</span>
          </button>

          {settingsOpen && (
            <div className="sidebar-submenu">
              <button className={`sidebar-nav-btn sub${activeTab === 'config' ? ' active' : ''}`}
                onClick={() => { setActiveTab('config'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Settings size={15} className="sidebar-icon" />
                <span className="sidebar-label">Core Parameters</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'rss' ? ' active' : ''}`}
                onClick={() => { setActiveTab('rss'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Rss size={15} className="sidebar-icon" />
                <span className="sidebar-label">RSS Feeds & Nodes</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'subagents' ? ' active' : ''}`}
                onClick={() => { setActiveTab('subagents'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Layers size={15} className="sidebar-icon" />
                <span className="sidebar-label">Sub-agents</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'mcp' ? ' active' : ''}`}
                onClick={() => { setActiveTab('mcp'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Server size={15} className="sidebar-icon" />
                <span className="sidebar-label">MCP Servers</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'obsidian' ? ' active' : ''}`}
                onClick={() => { setActiveTab('obsidian'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <BookOpen size={15} className="sidebar-icon" />
                <span className="sidebar-label">Obsidian</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'memory' ? ' active' : ''}`}
                onClick={() => { setActiveTab('memory'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Database size={15} className="sidebar-icon" />
                <span className="sidebar-label">Memory Vault (RAG)</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'tools' ? ' active' : ''}`}
                onClick={() => { setActiveTab('tools'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Wrench size={15} className="sidebar-icon" />
                <span className="sidebar-label">Core Tools</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'logs' ? ' active' : ''}`}
                onClick={() => { setActiveTab('logs'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Terminal size={15} className="sidebar-icon" />
                <span className="sidebar-label">Decision Logs</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'metrics' ? ' active' : ''}`}
                onClick={() => { setActiveTab('metrics'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <BarChart3 size={15} className="sidebar-icon" />
                <span className="sidebar-label">Metrics Dashboard</span>
              </button>
              <button className={`sidebar-nav-btn sub${activeTab === 'activity' ? ' active' : ''}`}
                onClick={() => { setActiveTab('activity'); setSidebarOpen(false); setSidebarExpanded(false); }}>
                <Activity size={15} className="sidebar-icon" />
                <span className="sidebar-label">Activity Logs</span>
              </button>
            </div>
          )}
        </nav>

        {/* Status Box — minimalist */}
        <div className="sidebar-status-box sidebar-status">
          {/* Connection */}
          <div className="sidebar-status-row" title={isConnected ? 'Network: connected' : 'Network: disconnected'}>
            <span className={`pulse-dot${isConnected ? '' : ' danger'}`} style={{ flexShrink: 0, width: 8, height: 8 }} />
            <span className="sidebar-label sidebar-status-text" style={{ color: isConnected ? 'var(--success)' : 'var(--danger)', letterSpacing: '0.5px' }}>
              {isConnected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>

          {/* Model */}
          <div className="sidebar-status-row" title={`Model: ${config.model}`}>
            <Cpu size={14} style={{ color: 'var(--text-dim)', flexShrink: 0 }} />
            <span className="sidebar-label sidebar-status-text" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>
              {config.model.split('/').pop()}
            </span>
          </div>

          {/* Logout */}
          <button onClick={handleLogout} className="sidebar-logout-btn" title="Logout">
            <LogOut size={14} style={{ flexShrink: 0 }} />
            <span className="sidebar-label">Logout</span>
          </button>
        </div>
      </aside>

      {/* 2. Main Workspace */}
      <main style={styles.mainContent} className={activeTab === 'office' ? 'office-main' : undefined}>
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
            timerSoundEnabled={timerSoundEnabled}
            setTimerSoundEnabled={setTimerSoundEnabled}

            isGenerating={isGenerating}
            playingMsgIndex={playingMsgIndex}
            setPlayingMsgIndex={setPlayingMsgIndex}
            config={config}
            isConnected={isConnected}
            isUploading={isUploading}
            attachedFile={attachedFile}
            setAttachedFile={setAttachedFile}
            speakText={speakText}
            handleClearChat={handleClearChat}
            handleSendMessage={handleSendMessage}
            handleChatFileAttach={handleChatFileAttach}
            selectChat={selectChat}
            handleCreateNewSession={handleCreateNewSession}
            fetchChatSessions={fetchChatSessions}
            getSessionLabel={getSessionLabel}
            mainChatEndRef={mainChatEndRef}
            subagents={subagents}
            handleSetSessionAgent={handleSetSessionAgent}
            fetchWithAuth={fetchWithAuth}
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
            language={appSettings.language}
            onLanguageChange={(lang) => {
              setAppSettings({ language: lang });
              fetchWithAuth('http://localhost:8000/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ language: lang }),
              }).catch(() => {});
            }}
            isOfficeEnabled={isOfficeEnabled}
            onOfficeEnabledChange={handleToggleOfficeEnabled}
          />
        )}

        {activeTab === 'logs' && (
          <LogsTab
            logs={logs}
            selectedLog={selectedLog}
            setSelectedLog={setSelectedLog}
          />
        )}

        {activeTab === 'metrics' && (
          <MetricsTab
            metrics={metrics}
            isLoading={isMetricsLoading}
            onRefresh={fetchMetrics}
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

        {activeTab === 'schedule' && (
          <ScheduleTab
            timers={timers}
            subagents={subagents}
            handleCancelTimer={handleCancelTimer}
            fetchWithAuth={fetchWithAuth}
            onOpenChat={(sessionId) => {
              selectChat(sessionId);
              setActiveTab('chat');
            }}
            onTaskUpdated={() => {
              fetchChatSessions();
            }}
            timerSoundEnabled={timerSoundEnabled}
            setTimerSoundEnabled={setTimerSoundEnabled}
          />

        )}

        {activeTab === 'tools' && (
          <ToolsTab
            systemStats={systemStats}
            uploads={uploads}
          />
        )}

        {activeTab === 'rss' && (
          <RSSTab />
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
          <NetworkTab subagents={subagents} setSubagents={setSubagents} fetchSubagents={fetchSubagents} models={models} />
        )}

        {activeTab === 'mcp' && (
          <MCPTab />
        )}

        {activeTab === 'tasks' && (
          <TaskBoardTab />
        )}

        {activeTab === 'office' && isOfficeEnabled && (
          <OfficeTab
            t={(key: string) => key}
            isConnected={isConnected}
            language={appSettings.language as 'en' | 'ru'}
            liveTrace={officeLiveTrace}
            fetchWithAuth={fetchWithAuth}
            selectChat={(agentId) => {
              selectChat(agentId);
              setActiveTab('chat');
            }}
          />
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
                  handleCreateNewSessionConfirm(newSessionNameInput, newSessionAgentInput);
                  setShowNewSessionModal(false);
                }
              }}
              autoFocus
            />

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                ORCHESTRATOR / AGENT
              </label>
              <AgentSelect
                value={newSessionAgentInput}
                onChange={(agentId) => setNewSessionAgentInput(agentId)}
                agents={[
                  { id: 'jarvis', name: 'Jarvis (Main)', agent_type: 'orchestrator' },
                  ...subagents
                ]}
                variant="full"
              />
            </div>

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
                  handleCreateNewSessionConfirm(newSessionNameInput, newSessionAgentInput);
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
