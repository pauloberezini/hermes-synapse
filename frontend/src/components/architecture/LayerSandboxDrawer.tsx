import React, { useState } from 'react';
import { 
  X, 
  Send, 
  Terminal, 
  Loader2
} from 'lucide-react';

interface LayerSandboxDrawerProps {
  activeOrchestrator: any | null;
  onClose: () => void;
}

export function LayerSandboxDrawer({
  activeOrchestrator,
  onClose
}: LayerSandboxDrawerProps) {
  const [prompt, setPrompt] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<Array<{ type: 'info' | 'success' | 'error'; text: string; time: string }>>([]);
  const [output, setOutput] = useState<string | null>(null);

  const addLog = (type: 'info' | 'success' | 'error', text: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { type, text, time }]);
  };

  const handleRunTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isRunning) return;

    setIsRunning(true);
    setOutput(null);
    setLogs([]);

    const orchName = activeOrchestrator?.name || activeOrchestrator?.id || 'SYNAPSE';
    addLog('info', `Initializing Orchestrator Pulse for layer: ${orchName}...`);

    try {
      addLog('info', `Routing query to active orchestrator target: ${activeOrchestrator?.id || 'jarvis'}`);
      
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: prompt,
          session_id: `sandbox_${activeOrchestrator?.id || 'jarvis'}`,
          agent_id: activeOrchestrator?.id || 'jarvis'
        })
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const data = await res.json();
      addLog('success', 'Execution pulse completed successfully.');
      setOutput(data.response || JSON.stringify(data, null, 2));
    } catch (err: any) {
      addLog('error', `Execution failed: ${err.message || err}`);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div style={{
      position: 'absolute',
      bottom: 0,
      left: 0,
      right: 0,
      height: 280,
      background: 'var(--bg-secondary, #0f172a)',
      borderTop: '1px solid var(--border-color, rgba(255,255,255,0.12))',
      zIndex: 25,
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '0 -8px 24px rgba(0,0,0,0.4)',
      backdropFilter: 'blur(12px)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(0,0,0,0.2)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Terminal size={16} style={{ color: '#34d399' }} />
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#f3f4f6' }}>
            Layer Sandbox Testing Panel — [{activeOrchestrator?.name || activeOrchestrator?.id || 'Master Orchestrator'}]
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#6b7280',
            cursor: 'pointer',
            padding: '2px',
            borderRadius: '4px'
          }}
        >
          <X size={16} />
        </button>
      </div>

      {/* Body Content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: Input & Logs */}
        <div style={{
          flex: 1,
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          borderRight: '1px solid rgba(255,255,255,0.08)'
        }}>
          <form onSubmit={handleRunTest} style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              placeholder={`Send test prompt to ${activeOrchestrator?.name || 'Orchestrator'}...`}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={isRunning}
              style={{
                flex: 1,
                background: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: '6px',
                padding: '8px 12px',
                color: '#fff',
                fontSize: '12px',
                outline: 'none'
              }}
            />
            <button
              type="submit"
              disabled={isRunning || !prompt.trim()}
              style={{
                background: '#10b981',
                color: '#000',
                border: 'none',
                borderRadius: '6px',
                padding: '8px 14px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: isRunning ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                opacity: isRunning ? 0.7 : 1
              }}
            >
              {isRunning ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              Pulse Test
            </button>
          </form>

          {/* Execution Trace Logs */}
          <div style={{
            flex: 1,
            background: 'rgba(0,0,0,0.4)',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.06)',
            padding: '8px 12px',
            overflowY: 'auto',
            fontFamily: 'monospace',
            fontSize: '11px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px'
          }}>
            {logs.length === 0 ? (
              <span style={{ color: '#6b7280', fontStyle: 'italic' }}>
                Awaiting test pulse execution. Enter a prompt above to simulate sub-agent delegation.
              </span>
            ) : (
              logs.map((log, i) => (
                <div key={i} style={{ display: 'flex', gap: '8px', color: log.type === 'error' ? '#f87171' : log.type === 'success' ? '#34d399' : '#9ca3af' }}>
                  <span style={{ color: '#6b7280' }}>[{log.time}]</span>
                  <span>{log.text}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Output Result View */}
        <div style={{
          width: '45%',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
          background: 'rgba(0,0,0,0.2)'
        }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase' }}>
            Orchestrator Output Payload
          </div>
          <div style={{
            flex: 1,
            background: 'rgba(0,0,0,0.4)',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.06)',
            padding: '10px 12px',
            overflowY: 'auto',
            fontSize: '12px',
            lineHeight: '1.5',
            color: '#f3f4f6',
            whiteSpace: 'pre-wrap'
          }}>
            {output ? output : <span style={{ color: '#6b7280' }}>Output response will render here...</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
