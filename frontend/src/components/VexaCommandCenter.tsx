import {
  Activity,
  BrainCircuit,
  Mic,
  MicOff,
  Radio,
  Send,
  ShieldCheck,
  Square,
  Users,
  Volume2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { AgentModel, ChatMessage } from '../types';

type VoicePhase = 'offline' | 'ready' | 'listening' | 'transcribing' | 'thinking' | 'speaking';

interface TtsStatus {
  enabled: boolean;
  available: boolean;
  active_provider?: string | null;
  voice?: string | null;
  browser_fallback: boolean;
}

interface VexaCommandCenterProps {
  agents: AgentModel[];
  messages: ChatMessage[];
  isConnected: boolean;
  isGenerating: boolean;
  isSpeaking: boolean;
  micState: 'off' | 'listening' | 'capturing' | 'transcribing';
  onVoiceToggle: () => void;
  onCommand: (text: string) => boolean;
  onStop: () => void;
  language: 'ru' | 'en';
}

const COPY = {
  ru: {
    title: 'VEXA',
    subtitle: 'Автономный голосовой центр управления',
    ready: 'Готова к команде',
    listening: 'Слушаю',
    transcribing: 'Распознаю речь',
    thinking: 'Координирую агентов',
    speaking: 'Отвечаю',
    offline: 'Нет связи с ядром',
    prompt: 'Скажите или напишите задачу для Vexa',
    send: 'Передать команду',
    stop: 'Остановить выполнение',
    mic: 'Начать голосовую команду',
    micStop: 'Завершить запись',
    conversation: 'Режим диалога',
    conversationHint: 'Vexa продолжит слушать после ответа',
    latestRequest: 'Последняя команда',
    latestAnswer: 'Ответ Vexa',
    waitingRequest: 'Ожидаю вашу команду.',
    waitingAnswer: 'Готова управлять агентами и выполнить задачу.',
    network: 'Контур',
    agents: 'Агенты',
    active: 'Активны',
    voice: 'Голос',
    local: 'Локальный',
    browser: 'Системный женский',
    policy: 'Контроль рисков включён',
    privacy: 'Микрофон активен только при синем индикаторе',
  },
  en: {
    title: 'VEXA',
    subtitle: 'Autonomous voice command center',
    ready: 'Ready for a command',
    listening: 'Listening',
    transcribing: 'Transcribing speech',
    thinking: 'Coordinating agents',
    speaking: 'Responding',
    offline: 'Core connection unavailable',
    prompt: 'Speak or type a task for Vexa',
    send: 'Send command',
    stop: 'Stop execution',
    mic: 'Start a voice command',
    micStop: 'Finish recording',
    conversation: 'Conversation mode',
    conversationHint: 'Vexa will listen again after responding',
    latestRequest: 'Latest command',
    latestAnswer: 'Vexa response',
    waitingRequest: 'Awaiting your command.',
    waitingAnswer: 'Ready to coordinate agents and execute the task.',
    network: 'Core',
    agents: 'Agents',
    active: 'Active',
    voice: 'Voice',
    local: 'Local',
    browser: 'System female',
    policy: 'Risk controls enabled',
    privacy: 'The microphone is active only with the blue indicator',
  },
} as const;

function plainText(value: string) {
  return value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]*\)/g, '$1')
    .replace(/[#*_>|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function phaseFor(
  isConnected: boolean,
  micState: VexaCommandCenterProps['micState'],
  isGenerating: boolean,
  isSpeaking: boolean,
): VoicePhase {
  if (!isConnected) return 'offline';
  if (micState === 'capturing' || micState === 'listening') return 'listening';
  if (micState === 'transcribing') return 'transcribing';
  if (isSpeaking) return 'speaking';
  if (isGenerating) return 'thinking';
  return 'ready';
}

function phaseLabel(phase: VoicePhase, copy: typeof COPY.ru | typeof COPY.en) {
  return copy[phase];
}

function VexaCoreAnimation({ phase }: { phase: VoicePhase }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    let frame = 0;
    let frameId = 0;

    const render = (time: number) => {
      const bounds = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const width = Math.max(1, Math.round(bounds.width * dpr));
      const height = Math.max(1, Math.round(bounds.height * dpr));
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      ctx.clearRect(0, 0, width, height);
      const cx = width / 2;
      const cy = height * .5;
      const radius = Math.min(width, height) * .31;
      const speed = phase === 'listening' ? 2.4 : phase === 'thinking' ? 1.7 : phase === 'speaking' ? 2 : .7;
      const energy = phase === 'offline' ? .16 : phase === 'ready' ? .42 : .9;
      const tick = reduceMotion ? 0 : time / 1000;

      ctx.save();
      ctx.globalCompositeOperation = 'screen';
      for (let ring = 0; ring < 7; ring += 1) {
        const ringRadius = radius * (.48 + ring * .105);
        const rotation = tick * speed * (ring % 2 ? -1 : 1) * (.12 + ring * .018);
        ctx.lineWidth = Math.max(1, dpr * (ring % 3 === 0 ? 1.25 : .65));
        ctx.strokeStyle = `rgba(${ring % 2 ? '58, 187, 255' : '27, 128, 255'}, ${.12 + energy * .2})`;
        for (let segment = 0; segment < 9; segment += 1) {
          const start = rotation + segment * Math.PI * 2 / 9;
          const length = .16 + ((ring * 7 + segment * 3) % 5) * .055;
          ctx.beginPath();
          ctx.arc(cx, cy, ringRadius, start, start + length);
          ctx.stroke();
        }
      }

      const particleCount = reduceMotion ? 28 : 74;
      for (let index = 0; index < particleCount; index += 1) {
        const seed = index * 12.9898;
        const orbit = radius * (.34 + ((Math.sin(seed) + 1) / 2) * .8);
        const angle = seed + tick * speed * (.08 + index % 5 * .018);
        const wobble = Math.sin(tick * 1.4 + seed) * radius * .025;
        const x = cx + Math.cos(angle) * (orbit + wobble);
        const y = cy + Math.sin(angle) * (orbit * .72 + wobble);
        const size = dpr * (.5 + (index % 4) * .32);
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(99, 213, 255, ${.12 + energy * ((index % 5) / 8 + .18)})`;
        ctx.fill();
      }

      if (phase === 'listening' || phase === 'speaking' || phase === 'transcribing') {
        ctx.lineWidth = Math.max(1, dpr * 1.1);
        ctx.strokeStyle = `rgba(111, 224, 255, ${.25 + energy * .35})`;
        ctx.beginPath();
        for (let index = 0; index <= 96; index += 1) {
          const ratio = index / 96;
          const angle = ratio * Math.PI * 2;
          const signal = Math.sin(angle * 7 + tick * speed * 4) * .5 + Math.sin(angle * 13 - tick * 3) * .24;
          const waveRadius = radius * (.31 + signal * .035 * energy);
          const x = cx + Math.cos(angle) * waveRadius;
          const y = cy + Math.sin(angle) * waveRadius;
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.stroke();
      }

      const pulse = reduceMotion ? .65 : .6 + Math.sin(tick * (phase === 'ready' ? 1.8 : 4.2)) * .14;
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * .48);
      glow.addColorStop(0, `rgba(197, 244, 255, ${pulse * energy})`);
      glow.addColorStop(.13, `rgba(38, 174, 255, ${.35 * energy})`);
      glow.addColorStop(1, 'rgba(0, 76, 180, 0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * .5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      frame += 1;
      if (!reduceMotion || frame < 2) frameId = requestAnimationFrame(render);
    };

    frameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frameId);
  }, [phase]);

  return <canvas ref={canvasRef} className="vexa-core-canvas" aria-hidden="true" />;
}

export function VexaCommandCenter({
  agents,
  messages,
  isConnected,
  isGenerating,
  isSpeaking,
  micState,
  onVoiceToggle,
  onCommand,
  onStop,
  language,
}: VexaCommandCenterProps) {
  const copy = COPY[language];
  const [input, setInput] = useState('');
  const [conversationMode, setConversationMode] = useState(false);
  const [ttsStatus, setTtsStatus] = useState<TtsStatus | null>(null);
  const lastAutoListenRef = useRef('');
  const phase = phaseFor(isConnected, micState, isGenerating, isSpeaking);

  const conversation = useMemo(() => {
    const user = [...messages].reverse().find(message => message.role === 'user');
    const assistant = [...messages].reverse().find(message => message.role === 'assistant' && !message.streaming);
    return {
      request: user ? plainText(user.content) : copy.waitingRequest,
      answer: assistant ? plainText(assistant.content) : copy.waitingAnswer,
      answerKey: assistant ? `${assistant.id || ''}:${assistant.run_id || ''}:${assistant.content.length}` : '',
    };
  }, [copy.waitingAnswer, copy.waitingRequest, messages]);

  const activeAgents = useMemo(
    () => agents.filter(agent => ['working', 'running', 'active', 'processing'].includes(String(agent.status || '').toLowerCase())),
    [agents],
  );

  useEffect(() => {
    let cancelled = false;
    fetch('/api/voice/tts/status')
      .then(response => response.ok ? response.json() : Promise.reject(new Error('TTS status unavailable')))
      .then(data => {
        if (!cancelled) setTtsStatus(data);
      })
      .catch(() => {
        if (!cancelled) setTtsStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!conversationMode || !conversation.answerKey || conversation.answerKey === lastAutoListenRef.current) return;
    if (!isConnected || isGenerating || isSpeaking || micState !== 'off') return;
    lastAutoListenRef.current = conversation.answerKey;
    const timer = window.setTimeout(onVoiceToggle, 650);
    return () => window.clearTimeout(timer);
  }, [conversation.answerKey, conversationMode, isConnected, isGenerating, isSpeaking, micState, onVoiceToggle]);

  const submit = () => {
    const command = input.trim();
    if (!command || !isConnected || isGenerating) return;
    if (onCommand(command)) setInput('');
  };

  const toggleConversation = () => {
    const next = !conversationMode;
    setConversationMode(next);
    lastAutoListenRef.current = conversation.answerKey;
    if (next && micState === 'off' && !isGenerating && !isSpeaking) onVoiceToggle();
  };

  const voiceName = ttsStatus?.available
    ? `${copy.local} · ${ttsStatus.active_provider || 'TTS'}${ttsStatus.voice ? ` · ${ttsStatus.voice}` : ''}`
    : copy.browser;

  return (
    <section className={`vexa-command-center is-${phase}`} aria-label={copy.subtitle}>
      <div className="vexa-backdrop" aria-hidden="true" />
      <VexaCoreAnimation phase={phase} />

      <header className="vexa-header">
        <div className="vexa-identity">
          <span className="vexa-kicker"><BrainCircuit size={15} /> Autonomous intelligence</span>
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>
        <div className={`vexa-phase is-${phase}`} aria-live="polite">
          <i />
          <span>{phaseLabel(phase, copy)}</span>
        </div>
      </header>

      <div className="vexa-telemetry" aria-label={language === 'ru' ? 'Состояние системы' : 'System state'}>
        <div>
          {isConnected ? <Wifi size={16} /> : <WifiOff size={16} />}
          <span>{copy.network}</span>
          <strong>{isConnected ? 'ONLINE' : 'OFFLINE'}</strong>
        </div>
        <div>
          <Users size={16} />
          <span>{copy.agents}</span>
          <strong>{agents.length}</strong>
        </div>
        <div>
          <Activity size={16} />
          <span>{copy.active}</span>
          <strong>{activeAgents.length}</strong>
        </div>
        <div>
          <Volume2 size={16} />
          <span>{copy.voice}</span>
          <strong title={voiceName}>{voiceName}</strong>
        </div>
      </div>

      <div className="vexa-transcript">
        <div>
          <span>{copy.latestRequest}</span>
          <p>{conversation.request}</p>
        </div>
        <div>
          <span>{copy.latestAnswer}</span>
          <p>{conversation.answer}</p>
        </div>
      </div>

      <aside className="vexa-agent-radar" aria-label={language === 'ru' ? 'Активные агенты' : 'Active agents'}>
        <div className="vexa-agent-radar-title">
          <Radio size={15} />
          <span>{language === 'ru' ? 'Контур агентов' : 'Agent mesh'}</span>
          <b>{activeAgents.length}/{agents.length}</b>
        </div>
        <div className="vexa-agent-list">
          {(activeAgents.length ? activeAgents : agents).slice(0, 7).map(agent => (
            <div key={agent.id}>
              <i className={activeAgents.includes(agent) ? 'is-active' : ''} />
              <span>{agent.name}</span>
              <small>{agent.current_task || agent.role || (language === 'ru' ? 'Ожидает задачу' : 'Awaiting task')}</small>
            </div>
          ))}
          {!agents.length && <p>{language === 'ru' ? 'Агенты ещё не загружены' : 'Agents have not loaded yet'}</p>}
        </div>
      </aside>

      <div className="vexa-voice-controls">
        <button
          type="button"
          className={`vexa-conversation-toggle${conversationMode ? ' is-active' : ''}`}
          onClick={toggleConversation}
          aria-pressed={conversationMode}
        >
          <Radio size={16} />
          <span>
            <strong>{copy.conversation}</strong>
            <small>{copy.conversationHint}</small>
          </span>
        </button>

        <button
          type="button"
          className={`vexa-mic-button${micState !== 'off' ? ' is-active' : ''}`}
          onClick={onVoiceToggle}
          disabled={micState === 'transcribing'}
          aria-label={micState === 'capturing' ? copy.micStop : copy.mic}
          title={micState === 'capturing' ? copy.micStop : copy.mic}
        >
          {micState === 'capturing' ? <MicOff size={28} /> : <Mic size={28} />}
          <span aria-hidden="true" />
        </button>

        {isGenerating ? (
          <button type="button" className="vexa-stop-button" onClick={onStop} title={copy.stop} aria-label={copy.stop}>
            <Square size={18} fill="currentColor" />
          </button>
        ) : (
          <div className="vexa-privacy">
            <ShieldCheck size={16} />
            <span>{copy.policy}</span>
          </div>
        )}
      </div>

      <form
        className="vexa-command-input"
        onSubmit={event => {
          event.preventDefault();
          submit();
        }}
      >
        <label htmlFor="vexa-command">{copy.prompt}</label>
        <input
          id="vexa-command"
          value={input}
          onChange={event => setInput(event.target.value)}
          placeholder={copy.prompt}
          autoComplete="off"
          disabled={!isConnected}
        />
        <button type="submit" disabled={!input.trim() || !isConnected || isGenerating} title={copy.send} aria-label={copy.send}>
          <Send size={18} />
        </button>
      </form>

      <footer className="vexa-footer">
        <span><i className={micState !== 'off' ? 'is-recording' : ''} /> {copy.privacy}</span>
        <span>STT · faster-whisper</span>
      </footer>
    </section>
  );
}
