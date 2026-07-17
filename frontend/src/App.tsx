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
  ChevronDown,
  ChevronRight,
  Building2,
  UserCog,
  ChevronsLeft,
  ChevronsRight,
  ShieldCheck
} from 'lucide-react';

import type { AppSettings, ChatMessage, ChatSession, DecisionLog, ActivityLog, SystemConfig, AgentModel, SystemStats } from './types';
import { styles } from './styles';
import { translate, type Language } from './i18n';
import { 
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
import { AgentsAdminTab } from './components/AgentsAdminTab';
import { OfficeTab, type OfficeLiveTrace } from './components/OfficeTab';
import { ProcessesTab } from './components/ProcessesTab';
import { HermesMark } from './components/HermesMark';
import { MetricsTab } from './components/MetricsTab';

// Initialize global fetch interceptor
initFetchInterceptor();

// Static BCP-47 locale map — defined at module level so hooks don't need it as a dep
const langToLocale: Record<string, string> = {
  ru: 'ru-RU', en: 'en-US', he: 'he-IL', de: 'de-DE', es: 'es-ES', fr: 'fr-FR'
};

export default function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'office' | 'processes' | 'agents' | 'schedule' | 'config' | 'logs' | 'activity' | 'memory' | 'tools' | 'subagents' | 'obsidian' | 'network' | 'mcp' | 'metrics'>(() => {
    const saved = localStorage.getItem('jarvis_active_tab');
    if (saved === 'settings') return 'tools';
    return (saved as any) || 'chat';
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => localStorage.getItem('hermes_sidebar_collapsed') === '1');
  const [language, setLanguageState] = useState<Language>(() => (localStorage.getItem('hermes_language') as Language) || 'ru');
  const [appSettings, setAppSettings] = useState<AppSettings>({ language });
  const appSettingsRef = useRef<AppSettings>({ language });
  const t = useCallback((key: string) => translate(language, key), [language]);
  const toggleSidebar = useCallback(() => {
    setIsSidebarCollapsed(prev => {
      const next = !prev;
      localStorage.setItem('hermes_sidebar_collapsed', next ? '1' : '0');
      return next;
    });
  }, []);
  const setLanguage = useCallback((nextLanguage: Language) => {
    localStorage.setItem('hermes_language', nextLanguage);
    setLanguageState(nextLanguage);
    setAppSettings({ language: nextLanguage });
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: nextLanguage }),
    }).catch(() => undefined);
  }, []);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([
    { id: 'dashboard', title: 'Main Terminal', agent_id: 'jarvis' },
  ]);
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
  const [metrics, setMetrics] = useState<any>(null);
  const [isMetricsLoading, setIsMetricsLoading] = useState(false);
  const [config, setConfig] = useState<SystemConfig>({
    system_prompt: '',
    model: 'qwen3:8b',
    provider: 'ollama',
    api_base: 'http://127.0.0.1:11434',
    ollama_base_url: 'http://127.0.0.1:11434',
    openai_api_base: 'https://openrouter.ai/api/v1',
    ollama_num_ctx: 8192,
    ollama_keep_alive: '5m',
    ollama_think: false,
    fast_mode: false,
    max_history_len: 6,
    max_tokens: 2048,
    tool_max_tokens: 2048,
    temperature: 0.7,
    auto_rag: false,
    memory_enabled: true,
    memory_auto_save: true,
    memory_max_items: 4
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
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);

  const [uploads, setUploads] = useState<{ name: string; size_bytes: number }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  // File attached to the current chat message (text context, not dataset upload)
  const [attachedFile, setAttachedFile] = useState<{ name: string; content: string; type?: string; pages?: number; truncated?: boolean } | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isTTSEnabled, setIsTTSEnabled] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [playingMsgIndex, setPlayingMsgIndex] = useState<number | null>(null);
  const [micEnabled, setMicEnabled] = useState(false);
  const [micState, setMicState] = useState<'off' | 'listening' | 'capturing' | 'transcribing'>('off');
  
  const [inputValue, setInputValue] = useState('');
  const [selectedLog, setSelectedLog] = useState<DecisionLog | null>(null);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  // Prompt edit states
  const [editedPrompt, setEditedPrompt] = useState('');
  const [editedModel, setEditedModel] = useState('');
  const [editedRuntimeConfig, setEditedRuntimeConfig] = useState<Partial<SystemConfig>>({});
  
  const [officeLiveTrace, setOfficeLiveTrace] = useState<OfficeLiveTrace | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mainChatEndRef = useRef<HTMLDivElement | null>(null);
  const subagentChatEndRef = useRef<HTMLDivElement | null>(null);
  const lastSentTimeRef = useRef<number>(0);
  const ttsEnabledRef = useRef(true);       // ref so WS handler always sees current value
  const isGeneratingRef = useRef(false);    // ref so send guard sees current value
  const activeRunIdRef = useRef<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceChunksRef = useRef<Blob[]>([]);
  const micStateRef = useRef<'off' | 'listening' | 'capturing' | 'transcribing'>('off');
  // Last user message per session, used by the "Retry" action (P0 UX).
  const lastUserMessageRef = useRef<Record<string, string>>({});

  const [subagents, setSubagents] = useState<AgentModel[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string>(() => {
    return localStorage.getItem('jarvis_current_chat_id') || 'dashboard';
  });
  const currentChatIdRef = useRef(localStorage.getItem('jarvis_current_chat_id') || 'dashboard');
  
  const [newAgentId, setNewAgentId] = useState('');
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentPrompt, setNewAgentPrompt] = useState('');
  const [newAgentModel, setNewAgentModel] = useState('qwen3:8b');
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
  const [editAgentModel, setEditAgentModel] = useState('qwen3:8b');
  const [editAgentSkills, setEditAgentSkills] = useState('');
  const [editAgentTemperature, setEditAgentTemperature] = useState(0.7);
  const [isUpdatingAgent, setIsUpdatingAgent] = useState(false);
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);

  const navStyle = useCallback((tab: typeof activeTab) => ({
    ...styles.navBtn,
    ...(isSidebarCollapsed ? styles.navBtnCollapsed : {}),
    ...(activeTab === tab ? styles.navBtnActive : {})
  }), [activeTab, isSidebarCollapsed]);

  useEffect(() => {
    currentChatIdRef.current = currentChatId;
    localStorage.setItem('jarvis_current_chat_id', currentChatId);
  }, [currentChatId]);

  useEffect(() => {
    localStorage.setItem('jarvis_active_tab', activeTab);
  }, [activeTab]);

  // Keep ttsEnabledRef in sync with its state
  useEffect(() => { ttsEnabledRef.current = isTTSEnabled; }, [isTTSEnabled]);
  useEffect(() => { appSettingsRef.current = appSettings; }, [appSettings]);

  // Open Settings dropdown automatically if a settings sub-tab is active
  useEffect(() => {
    if (['config', 'subagents', 'mcp', 'obsidian', 'logs', 'activity', 'memory', 'tools'].includes(activeTab)) {
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
  useEffect(() => {
    micStateRef.current = micState;
  }, [micState]);

  useEffect(() => {
    isGeneratingRef.current = isGenerating;
  }, [isGenerating]);

  // Draft persistence: restore the unsent draft when switching sessions (P0 UX).
  useEffect(() => {
    try {
      const draft = localStorage.getItem(`hermes.draft.${currentChatId}`) || '';
      setInputValue(draft);
    } catch { /* localStorage unavailable — non-fatal */ }
  }, [currentChatId]);

  useEffect(() => {
    try {
      if (inputValue) {
        localStorage.setItem(`hermes.draft.${currentChatId}`, inputValue);
      } else {
        localStorage.removeItem(`hermes.draft.${currentChatId}`);
      }
    } catch { /* localStorage unavailable — non-fatal */ }
  }, [inputValue, currentChatId]);

  const sendChatText = useCallback((text: string) => {
    const command = text.trim();
    if (!command || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return false;

    // Block concurrent sends while a response is generating (P0 UX).
    if (isGeneratingRef.current) {
      console.warn('Response in progress; ignoring new submission.');
      return false;
    }

    const now = Date.now();
    if (now - lastSentTimeRef.current < 300) {
      console.warn("Prevented duplicate message submission");
      return false;
    }
    lastSentTimeRef.current = now;
    lastUserMessageRef.current[currentChatIdRef.current] = command;

    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    setPlayingMsgIndex(null);
    const runId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    activeRunIdRef.current = runId;
    wsRef.current.send(JSON.stringify({
      type: 'chat_message',
      content: command,
      chat_id: currentChatIdRef.current,
      run_id: runId
    }));
    setIsGenerating(true);
    return true;
  }, []);

  const resetVoiceRecorder = useCallback(() => {
    voiceStreamRef.current?.getTracks().forEach(track => track.stop());
    voiceStreamRef.current = null;
    mediaRecorderRef.current = null;
    voiceChunksRef.current = [];
  }, []);

  const submitVoiceBlob = useCallback(async (blob: Blob) => {
    if (!blob.size) {
      setMicEnabled(false);
      setMicState('off');
      return;
    }

    setMicEnabled(true);
    setMicState('transcribing');
    const formData = new FormData();
    formData.append('file', blob, `jarvis-voice-${Date.now()}.webm`);

    try {
      const res = await fetch('/api/voice/transcribe', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Voice transcription failed.');
      }

      const text = String(data.text || '').trim();
      if (!text) {
        throw new Error('No speech detected in recording.');
      }

      const sent = sendChatText(text);
      setInputValue(sent ? '' : text);
      if (sent) playBeep(1040, 0.12);
    } catch (err) {
      console.error('Voice transcription error:', err);
      alert(err instanceof Error ? err.message : 'Voice transcription failed.');
    } finally {
      setMicEnabled(false);
      setMicState('off');
    }
  }, [sendChatText]);

  const stopVoiceRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
  }, []);

  const startVoiceRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      alert('Voice recording is not supported by this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });

      const mimeCandidates = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
      ];
      const mimeType = mimeCandidates.find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      voiceStreamRef.current = stream;
      voiceChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          voiceChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const recordedType = recorder.mimeType || mimeType || 'audio/webm';
        const blob = new Blob(voiceChunksRef.current, { type: recordedType });
        resetVoiceRecorder();
        submitVoiceBlob(blob);
      };

      recorder.onerror = (event) => {
        console.error('Voice recorder error:', event);
        resetVoiceRecorder();
        setMicEnabled(false);
        setMicState('off');
        alert('Voice recorder failed.');
      };

      recorder.start();
      setMicEnabled(true);
      setMicState('capturing');
      window.speechSynthesis?.cancel();
      setIsSpeaking(false);
      setPlayingMsgIndex(null);
      stopAlarmSound();
      playBeep(880, 0.12);
    } catch (err) {
      console.error('Microphone permission error:', err);
      resetVoiceRecorder();
      setMicEnabled(false);
      setMicState('off');
      alert('Microphone access was denied or is unavailable.');
    }
  }, [resetVoiceRecorder, submitVoiceBlob]);

  const handleVoiceToggle = useCallback(() => {
    if (micStateRef.current === 'capturing') {
      playBeep(560, 0.10);
      stopVoiceRecording();
      return;
    }
    if (micStateRef.current === 'transcribing') return;
    startVoiceRecording();
  }, [startVoiceRecording, stopVoiceRecording]);

  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== 'inactive') {
        try { recorder.stop(); } catch (_) {}
      }
      resetVoiceRecorder();
    };
  }, [resetVoiceRecorder]);

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
    return fetch(url, { ...options, headers }).then(res => {
      if (res.status === 401) {
        localStorage.removeItem('jarvis_auth_token');
        setIsAuthenticated(false);
      }
      return res;
    });
  }, []);

  const handleRequestOtp = async () => {
    setAuthStatus('sending');
    setAuthError('');
    try {
      const res = await fetch('/api/auth/request-code', {
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
      const res = await fetch('/api/auth/verify-code', {
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
      const wsUrl = `${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`;
      
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
            setEditedRuntimeConfig(data.config);
            if (data.logs) {
              setLogs(data.logs);
            }
            if (data.history && data.history.length > 0) {
              setMessages(data.history);
            }
            if (data.activity_logs) {
              setActivityLogs(data.activity_logs);
            }
          } else if (data.type === 'chat_stream_start') {
            const msgChatId = data.chat_id || 'dashboard';
            if (msgChatId === currentChatIdRef.current) {
              setMessages(prev => prev.some(message => message.run_id === data.run_id)
                ? prev
                : [...prev, {
                    role: 'assistant',
                    content: '',
                    thinking: '',
                    chat_id: msgChatId,
                    run_id: data.run_id,
                    streaming: true,
                    meta: { model: data.model, provider: data.provider, status: 'streaming' },
                  }]);
            }
          } else if (data.type === 'chat_stream_chunk') {
            const msgChatId = data.chat_id || 'dashboard';
            if (msgChatId === currentChatIdRef.current) {
              setMessages(prev => prev.map(message => message.run_id === data.run_id
                ? {
                    ...message,
                    content: `${message.content || ''}${data.content || ''}`,
                    thinking: `${message.thinking || ''}${data.thinking || ''}`,
                    streaming: true,
                  }
                : message));
            }
          } else if (data.type === 'chat_stream_end') {
            const msgChatId = data.chat_id || 'dashboard';
            if (msgChatId === currentChatIdRef.current) {
              setMessages(prev => prev.map(message => message.run_id === data.run_id
                ? { ...message, streaming: false, id: data.message_id || message.id, meta: data.meta || message.meta }
                : message));
            }
          } else if (data.type === 'chat_message') {
            const msgChatId = data.chat_id || 'dashboard';
            if (msgChatId === currentChatIdRef.current) {
              const incoming: ChatMessage = {
                id: data.id,
                role: data.role,
                content: data.content,
                chat_id: msgChatId,
                cost_usd: data.cost_usd,
                meta: data.meta,
                run_id: data.run_id,
                streaming: false,
              };
              setMessages(prev => data.role === 'assistant' && data.run_id && prev.some(message => message.run_id === data.run_id)
                ? prev.map(message => message.run_id === data.run_id ? { ...message, ...incoming } : message)
                : [...prev, incoming]);
            }
            if (data.role === 'assistant') {
              activeRunIdRef.current = null;
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
                new Notification('VEXA', {
                  body: preview || 'New Vexa response',
                  icon: '/favicon.svg',
                  tag: 'jarvis-reply',
                  silent: false,
                });
              }
            }
          } else if (data.type === 'chat_cancelled') {
            const cancelledRunId = String(data.run_id || activeRunIdRef.current || '');
            const cancelledChatId = data.chat_id || currentChatIdRef.current;
            if (cancelledChatId === currentChatIdRef.current) {
              setMessages(prev => prev.map(message =>
                message.run_id === cancelledRunId
                  ? {
                      ...message,
                      streaming: false,
                      meta: { ...(message.meta || {}), status: 'cancelled' },
                    }
                  : message
              ));
            }
            activeRunIdRef.current = null;
            setIsGenerating(false);
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
            setConfig(data);
            setEditedPrompt(data.system_prompt);
            setEditedModel(data.model);
            setEditedRuntimeConfig(data);
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
    fetch('/api/documents')
      .then(res => res.json())
      .then(data => setDocuments(data))
      .catch(err => console.log('Error fetching documents:', err));
  };

  const fetchMetrics = useCallback(() => {
    setIsMetricsLoading(true);
    fetchWithAuth('http://localhost:8000/api/metrics')
      .then(res => res.json())
      .then(data => {
        setMetrics(data);
        setIsMetricsLoading(false);
      })
      .catch(err => {
        console.log('Error fetching metrics:', err);
        setIsMetricsLoading(false);
      });
  }, [fetchWithAuth]);

  useEffect(() => {
    if (activeTab === 'metrics') {
      fetchMetrics();
    }
  }, [activeTab, fetchMetrics]);

  const fetchUploads = () => {
    fetch('/api/uploads')
      .then(res => res.json())
      .then(data => setUploads(data))
      .catch(err => console.log('Error fetching uploads:', err));
  };

  const fetchChatSessions = () => {
    fetch('/api/history/sessions')
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
    fetch('/api/subagents')
      .then(res => res.json())
      .then(data => setSubagents(data))
      .catch(err => console.log('Error fetching subagents:', err));
  };

  const selectChat = (chatId: string, currentSubagentsList?: any[]) => {
    const listToSearch = currentSubagentsList || subagents;
    setCurrentChatId(chatId);
    setMessages([]); // clear temporarily
    fetch(`/api/history/${chatId}`)
      .then(res => res.json())
      .then(data => {
        if (data && data.length > 0) {
          setMessages(data);
        } else {
          if (chatId === 'dashboard') {
            setMessages([{ role: 'assistant', content: 'Greetings, Sir. Connection to the Hermes network is complete. Awaiting your instructions.' }]);
          } else {
            const agent = listToSearch.find((a: any) => a.id === chatId);
            if (chatId.startsWith('chat_')) {
              setMessages([{ role: 'assistant', content: 'Conversation initialized, Sir. How can I assist you today?' }]);
            } else {
              setMessages([{ role: 'assistant', content: `Sub-agent session "${agent?.name || chatId}" initialized, Sir. Ready for work.` }]);
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
      const res = await fetch('/api/subagents', {
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
        
        fetch('/api/subagents')
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
      const res = await fetch(`/api/subagents/${id}`, {
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
      const res = await fetch('/api/subagents', {
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
        fetch('/api/subagents')
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
    fetch(`/api/timers/${id}`, {
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

  const handleClearActivityLogs = () => {
    fetch('/api/activity/logs', {
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
    fetch('/api/models', {
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

    fetch('/api/config')
      .then(res => res.json())
      .then(data => {
        if (data && data.system_prompt !== undefined) {
          setConfig(data);
          setEditedPrompt(data.system_prompt);
          setEditedModel(data.model);
          setEditedRuntimeConfig(data);
        }
      })
      .catch(() => console.log('REST config fetch skipped/failed (using WS instead)'));

    fetch('/api/logs')
      .then(res => res.json())
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
      .then(res => res.json())
      .then(data => {
        if (data?.language) {
          const nextLanguage = data.language as Language;
          setAppSettings({ language: nextLanguage });
          setLanguageState(nextLanguage);
          localStorage.setItem('hermes_language', nextLanguage);
        }
      })
      .catch(() => {});
    
    if (isAuthenticated) {
      const savedChatId = localStorage.getItem('jarvis_current_chat_id') || 'dashboard';
      selectChat(savedChatId);
    }
    // These fetch helpers and selectChat are intentionally initialized once per auth session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  // Fetch system stats and timers when the "tools" tab is active
  useEffect(() => {
    if (!isAuthenticated || activeTab !== 'tools') return;

    const fetchStats = () => {
      fetch('/api/system/stats')
        .then(async res => {
          const contentType = res.headers.get('content-type') || '';
          if (!res.ok || !contentType.includes('application/json')) {
            throw new Error(`Telemetry API unavailable (${res.status})`);
          }
          return res.json();
        })
        .then(data => setSystemStats(data))
        .catch(err => {
          console.log('Error fetching system stats:', err);
          setSystemStats({
            available: false,
            cpu_load_percent: null,
            ram_used_percent: null,
            ram_total_gb: null,
            disk_used_percent: null,
            disk_total_gb: null,
            disk_used_gb: null,
            status: 'unavailable',
            source: 'backend telemetry API',
            unavailable: ['cpu', 'ram', 'disk'],
            error: err instanceof Error ? err.message : 'Telemetry API unavailable'
          });
        });
    };

    const fetchTimersData = () => {
      fetch('/api/timers')
        .then(async res => {
          const contentType = res.headers.get('content-type') || '';
          if (!res.ok || !contentType.includes('application/json')) {
            throw new Error(`Timers API unavailable (${res.status})`);
          }
          const data = await res.json();
          if (!Array.isArray(data)) {
            throw new Error('Timers API returned an invalid payload');
          }
          return data;
        })
        .then(data => setTimers(data))
        .catch(err => console.log('Error fetching timers:', err));
    };

    fetchStats();
    fetchTimersData();
    fetchUploads();

    const statsInterval = setInterval(() => {
      fetchStats();
      fetchUploads();
    }, 5000);
    const timersInterval = setInterval(fetchTimersData, 2000);

    return () => {
      clearInterval(statsInterval);
      clearInterval(timersInterval);
    };
  }, [activeTab, isAuthenticated]);

  // Local smooth countdown for timers in state
  useEffect(() => {
    const localTicker = setInterval(() => {
      setTimers(prevTimers =>
        (Array.isArray(prevTimers) ? prevTimers : []).map(timer => {
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
      const res = await fetch('/api/documents', {
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
      const res = await fetch(`/api/documents/${docId}`, {
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
      const res = await fetch(`/api/documents/search?q=${encodeURIComponent(memorySearchQuery)}`);
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
    if (sendChatText(inputValue)) {
      setInputValue('');
    }
  };

  const handleStopGeneration = useCallback(() => {
    const runId = activeRunIdRef.current;
    if (runId) {
      const token = localStorage.getItem('jarvis_auth_token');
      void fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      activeRunIdRef.current = null;
    }
    setIsGenerating(false);
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    setPlayingMsgIndex(null);
  }, []);

  // Re-send the last user message for the current session (P0 UX "Retry").
  const handleRetryLast = useCallback(() => {
    const last = lastUserMessageRef.current[currentChatIdRef.current];
    if (last) {
      sendChatText(last);
    }
  }, [sendChatText]);

  const handleClearChat = async () => {
    if (!window.confirm('Sir, are you sure you want to completely clear the history of this session?')) return;
    
    setMessages([]);
    try {
      const res = await fetch(`/api/history/${currentChatId}`, {
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
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_prompt: editedPrompt,
          model: editedModel,
          provider: editedRuntimeConfig.provider,
          api_base: editedRuntimeConfig.api_base,
          ollama_base_url: editedRuntimeConfig.ollama_base_url,
          openai_api_base: editedRuntimeConfig.openai_api_base,
          ollama_num_ctx: editedRuntimeConfig.ollama_num_ctx,
          ollama_keep_alive: editedRuntimeConfig.ollama_keep_alive,
          ollama_think: editedRuntimeConfig.ollama_think,
          fast_mode: editedRuntimeConfig.fast_mode,
          max_history_len: editedRuntimeConfig.max_history_len,
          max_tokens: editedRuntimeConfig.max_tokens,
          tool_max_tokens: editedRuntimeConfig.tool_max_tokens,
          temperature: editedRuntimeConfig.temperature,
          auto_rag: editedRuntimeConfig.auto_rag,
          memory_enabled: editedRuntimeConfig.memory_enabled,
          memory_auto_save: editedRuntimeConfig.memory_auto_save,
          memory_max_items: editedRuntimeConfig.memory_max_items
        })
      });
      if (response.ok) {
        const data = await response.json();
        setConfig(data.config);
        setEditedRuntimeConfig(data.config);
        setEditedModel(data.config.model);
        fetchModels();
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
          
          <div className="hermes-auth-brand" style={{ marginBottom: '30px' }}>
            <HermesMark className="hermes-auth-mark" />
            <h1 className="glow-text-cyan" style={{ fontSize: '2.5rem', fontWeight: 800, letterSpacing: 0, margin: 0 }}>HERMES</h1>
            <p style={{ color: '#06b6d4', fontSize: '0.9rem', letterSpacing: 0, margin: '4px 0 0', textTransform: 'uppercase' }}>Secure Access Link</p>
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

      {/* 1. Left Sidebar */}
      <aside
        style={{ ...styles.sidebar, ...(isSidebarCollapsed ? styles.sidebarCollapsed : {}) }}
        className={`glass-panel sidebar ${sidebarOpen ? 'sidebar-open' : ''} ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
      >
        <button
          type="button"
          onClick={toggleSidebar}
          style={styles.sidebarToggle}
          title={isSidebarCollapsed ? 'Развернуть меню' : 'Свернуть меню до иконок'}
          aria-label={isSidebarCollapsed ? 'Развернуть меню' : 'Свернуть меню до иконок'}
        >
          {isSidebarCollapsed ? <ChevronsRight size={17} /> : <ChevronsLeft size={17} />}
        </button>
        <div style={styles.logoArea}>
          <HermesMark />
          <h1 className="glow-text-cyan sidebar-title" style={styles.logoTitle}>HERMES</h1>
        </div>
        <p className="sidebar-subtitle" style={styles.logoSubtitle}>{t('appSubtitle')}</p>
        
        <nav style={{ ...styles.navMenu, ...(isSidebarCollapsed ? styles.navMenuCollapsed : {}) }}>
          <button
            style={navStyle('chat')}
            onClick={() => { setActiveTab('chat'); setSidebarOpen(false); }}
            title={t('navChat')}
          >
            <MessageSquare size={18} />
            <span>{t('navChat')}</span>
          </button>

          <button
            style={navStyle('office')}
            onClick={() => { setActiveTab('office'); setSidebarOpen(false); }}
            title={t('navOffice')}
          >
            <Building2 size={18} />
            <span>{t('navOffice')}</span>
          </button>

          <button
            style={navStyle('processes')}
            onClick={() => { setActiveTab('processes'); setSidebarOpen(false); }}
            title={t('navProcesses')}
          >
            <ShieldCheck size={18} />
            <span>{t('navProcesses')}</span>
          </button>

          <button
            style={navStyle('agents')}
            onClick={() => { setActiveTab('agents'); setSidebarOpen(false); }}
            title={t('navAgents')}
          >
            <UserCog size={18} />
            <span>{t('navAgents')}</span>
          </button>
          
          <button
            style={navStyle('schedule')}
            onClick={() => { setActiveTab('schedule'); setSidebarOpen(false); }}
            title="Schedules & Automation"
          >
            <Clock size={18} />
            <span>Schedules & Automation</span>
          </button>

          <button
            style={navStyle('network')}
            onClick={() => { setActiveTab('network'); setSidebarOpen(false); }}
            title={t('navArchitecture')}
          >
            <Network size={18} />
            <span>{t('navArchitecture')}</span>
          </button>
          
          <button
            style={{
              ...styles.navBtn,
              ...(isSidebarCollapsed ? styles.navBtnCollapsed : {}),
              justifyContent: 'space-between',
              paddingRight: '12px',
              ...((['config', 'subagents', 'mcp', 'obsidian', 'logs', 'activity', 'memory', 'tools'].includes(activeTab)) ? styles.navBtnActive : {})
            }}
            onClick={() => setSettingsOpen(!settingsOpen)}
            title={t('navSettings')}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Settings size={18} />
              <span>{t('navSettings')}</span>
            </div>
            {settingsOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>

          {settingsOpen && (
            <div style={{ paddingLeft: isSidebarCollapsed ? 0 : '20px', display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px', marginBottom: '4px' }}>
              {!isSidebarCollapsed && <span className="nav-section-label">SYSTEM</span>}
              <button
                style={navStyle('config')}
                onClick={() => { setActiveTab('config'); setSidebarOpen(false); }}
                title={t('navConfig')}
              >
                <Settings size={18} />
                <span>{t('navConfig')}</span>
              </button>

              <button
                style={navStyle('tools')}
                onClick={() => { setActiveTab('tools'); setSidebarOpen(false); }}
                title={t('navTools')}
              >
                <Wrench size={18} />
                <span>{t('navTools')}</span>
              </button>

              {!isSidebarCollapsed && <span className="nav-section-label">AGENTS</span>}
              <button
                style={navStyle('subagents')}
                onClick={() => {
                  setActiveTab('subagents');
                  selectChat(currentChatId === 'dashboard' ? 'dashboard' : currentChatId);
                  setSidebarOpen(false);
                }}
                title={t('navSubagents')}
              >
                <Layers size={18} />
                <span>{t('navSubagents')}</span>
              </button>

              <button
                style={navStyle('mcp')}
                onClick={() => { setActiveTab('mcp'); setSidebarOpen(false); }}
                title={t('navMcp')}
              >
                <Server size={18} />
                <span>{t('navMcp')}</span>
              </button>

              <button
                style={navStyle('obsidian')}
                onClick={() => { setActiveTab('obsidian'); setSidebarOpen(false); }}
                title={t('navObsidian')}
              >
                <BookOpen size={18} />
                <span>{t('navObsidian')}</span>
              </button>
              
              <button
                style={navStyle('memory')}
                onClick={() => { setActiveTab('memory'); setSidebarOpen(false); }}
                title={t('navMemory')}
              >
                <Database size={18} />
                <span>{t('navMemory')}</span>
              </button>

              {!isSidebarCollapsed && <span className="nav-section-label">LOGS</span>}
              <button
                style={navStyle('logs')}
                onClick={() => { setActiveTab('logs'); setSidebarOpen(false); }}
                title={t('navLogs')}
              >
                <Terminal size={18} />
                <span>{t('navLogs')}</span>
              </button>
              
              <button
                style={navStyle('activity')}
                onClick={() => { setActiveTab('activity'); setSidebarOpen(false); }}
                title={t('navActivity')}
              >
                <Activity size={18} />
                <span>{t('navActivity')}</span>
              </button>
            </div>
          )}
        </nav>

        {/* Sidebar Status Info */}
        <div style={styles.statusBox} className="glass-panel sidebar-status">
          <div style={styles.statusRow}>
            <span style={styles.statusLabel}>{t('network')}:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className={`pulse-dot ${isConnected ? '' : 'danger'}`} />
              <span style={{ fontSize: '0.85rem', color: isConnected ? 'var(--success)' : 'var(--danger)' }}>
                {isConnected ? t('connected') : t('disconnected')}
              </span>
            </div>
          </div>
          
          <div style={styles.statusRow}>
            <span style={styles.statusLabel}>{t('llmCore')}:</span>
            <div style={styles.modelTag}>
              <Cpu size={12} style={{ color: 'var(--accent-cyan)' }} />
              <span style={styles.modelName}>{config.model.split('/').pop()}</span>
            </div>
          </div>
          
          <div style={styles.statusRow}>
            <span style={styles.statusLabel}>{t('callLogs')}:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--accent-cyan)' }}>
              {logs.length} logs
            </span>
          </div>
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
            onVoiceToggle={handleVoiceToggle}
            isTTSEnabled={isTTSEnabled}
            setIsTTSEnabled={setIsTTSEnabled}
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
            t={t}
            onStopGeneration={handleStopGeneration}
            onRetryLast={handleRetryLast}
            hasLastUserMessage={messages.some(message => message.role === 'user')}
            onChangeModel={() => setActiveTab('config')}
            subagents={subagents}
            handleSetSessionAgent={handleSetSessionAgent}
          />
        )}

        {activeTab === 'office' && (
          <OfficeTab
            t={t}
            isConnected={isConnected}
            language={language}
            liveTrace={officeLiveTrace}
            selectChat={(agentId) => {
              selectChat(agentId);
              setActiveTab('chat');
            }}
          />
        )}

        {activeTab === 'processes' && <ProcessesTab language={language} />}

        {activeTab === 'agents' && (
          <AgentsAdminTab
            agents={subagents}
            models={models}
            fetchAgents={fetchSubagents}
            t={t}
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
            runtimeConfig={editedRuntimeConfig}
            setRuntimeConfig={setEditedRuntimeConfig}
            language={language}
            onLanguageChange={(nextLanguage) => setLanguage(nextLanguage as Language)}
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
          />
        )}

        {activeTab === 'tools' && (
          <ToolsTab
            systemStats={systemStats}
            uploads={uploads}
            language={language}
            setLanguage={setLanguage}
            t={t}
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
          <NetworkTab subagents={subagents} setSubagents={setSubagents} fetchSubagents={fetchSubagents} models={models} />
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
            backgroundColor: 'rgba(24, 23, 38, 0.96)',
            border: '1px solid rgba(155, 136, 255, 0.34)',
            borderRadius: '8px',
            boxShadow: '0 22px 60px rgba(0, 0, 0, 0.4), 0 0 28px rgba(155, 136, 255, 0.2)',
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
              <select
                value={newSessionAgentInput}
                onChange={(e) => setNewSessionAgentInput(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: '1px solid rgba(255,255,255,0.1)',
                  backgroundColor: 'rgba(15, 23, 42, 0.95)',
                  color: '#fff',
                  fontSize: '0.9rem',
                  outline: 'none',
                  cursor: 'pointer'
                }}
              >
                <option value="jarvis">👑 Jarvis (Main)</option>
                {subagents.map(a => {
                  const isOrch = a.agent_type === 'orchestrator' || a.agent_type === 'sub-orchestrator';
                  const icon = isOrch ? '🧠' : '🤖';
                  return (
                    <option key={a.id} value={a.id}>
                      {icon} {a.name}
                    </option>
                  );
                })}
              </select>
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
                  border: '1px solid rgba(155, 136, 255, 0.45)',
                  backgroundColor: 'rgba(155, 136, 255, 0.14)',
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
