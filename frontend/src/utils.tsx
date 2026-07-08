import React from 'react';
import type { RenderedListItem } from './types';

// Inline text formatter for bold, italic, links, and inline code
export const parseInline = (text: string): React.ReactNode[] => {
  const tokens: React.ReactNode[] = [];
  let lastIndex = 0;
  
  // Regex to match:
  // 1. Bold: **text** or __text__
  // 2. Italic: *text* or _text_
  // 3. Link: [label](url)
  // 4. Inline code: `code`
  const regex = /(\*\*|__)(.*?)\1|(\*|_)(.*?)\3|(\[)(.*?)(\]\((.*?)\))|(`)(.*?)`/g;
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(text.substring(lastIndex, match.index));
    }
    
    if (match[1]) {
      // Bold
      tokens.push(
        <strong key={match.index} style={{ color: '#ffffff', fontWeight: 600 }}>
          {parseInline(match[2])}
        </strong>
      );
    } else if (match[3]) {
      // Italic
      tokens.push(
        <em key={match.index} style={{ fontStyle: 'italic' }}>
          {parseInline(match[4])}
        </em>
      );
    } else if (match[5]) {
      // Link
      const label = match[6];
      const url = match[8];
      tokens.push(
        <a 
          key={match.index} 
          href={url} 
          target="_blank" 
          rel="noopener noreferrer" 
          style={{ 
            color: 'var(--accent-cyan)', 
            textDecoration: 'none', 
            borderBottom: '1px dashed rgba(0, 240, 255, 0.4)',
            paddingBottom: '1px',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.color = '#fff';
            e.currentTarget.style.borderBottomColor = 'var(--accent-cyan)';
            e.currentTarget.style.textShadow = 'var(--glow-cyan)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.color = 'var(--accent-cyan)';
            e.currentTarget.style.borderBottomColor = 'rgba(0, 240, 255, 0.4)';
            e.currentTarget.style.textShadow = 'none';
          }}
        >
          {parseInline(label)}
        </a>
      );
    } else if (match[9]) {
      // Code
      tokens.push(
        <code 
          key={match.index} 
          style={{ 
            fontFamily: 'var(--font-mono)', 
            backgroundColor: 'rgba(255, 255, 255, 0.08)', 
            padding: '2px 6px', 
            borderRadius: '4px',
            fontSize: '0.85rem',
            color: 'var(--accent-orange)'
          }}
        >
          {match[10]}
        </code>
      );
    }
    
    lastIndex = regex.lastIndex;
  }
  
  if (lastIndex < text.length) {
    tokens.push(text.substring(lastIndex));
  }
  
  return tokens.length > 0 ? tokens : [text];
};

// Render full markdown content to React Nodes (supports lists, tables, headers, blocks)
export const renderMarkdown = (text: string) => {
  if (!text) return null;
  
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  
  let currentList: { items: RenderedListItem[]; ordered: boolean } | null = null;
  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeBlockLines: string[] = [];
  
  const flushList = (key: number) => {
    if (currentList) {
      elements.push(
        <div key={`list-${key}`} style={{ margin: '8px 0' }}>
          {currentList.items.map((item, idx) => (
            <div 
              key={idx} 
              style={{ 
                display: 'flex', 
                alignItems: 'flex-start', 
                paddingLeft: `${item.indent * 12}px`, 
                marginBottom: '4px',
                lineHeight: 1.5
              }}
            >
              {currentList!.ordered ? (
                <span style={{ 
                  color: 'var(--accent-cyan)', 
                  marginRight: '8px', 
                  fontFamily: 'var(--font-mono)', 
                  fontSize: '0.9rem',
                  minWidth: '18px',
                  textAlign: 'right'
                }}>
                  {idx + 1}.
                </span>
              ) : (
                <span style={{ 
                  color: 'var(--accent-cyan)', 
                  marginRight: '8px', 
                  userSelect: 'none',
                  fontSize: '1rem',
                  lineHeight: '1.2rem'
                }}>
                  •
                </span>
              )}
              <div style={{ flex: 1 }}>{item.content}</div>
            </div>
          ))}
        </div>
      );
      currentList = null;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    
    if (trimmed.startsWith('```')) {
      flushList(i);
      if (inCodeBlock) {
        // End of code block
        elements.push(
          <pre 
            key={`code-${i}`} 
            style={{
              backgroundColor: 'rgba(0, 0, 0, 0.4)',
              border: '1px solid rgba(0, 240, 255, 0.15)',
              borderRadius: '8px',
              padding: '12px',
              margin: '12px 0',
              overflowX: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.85rem',
              color: '#d4d4d4',
              position: 'relative'
            }}
          >
            {codeBlockLang && (
              <span style={{ 
                position: 'absolute', 
                top: '4px', 
                right: '8px', 
                fontSize: '0.7rem', 
                color: 'var(--text-dim)', 
                textTransform: 'uppercase' 
              }}>
                {codeBlockLang}
              </span>
            )}
            <code>{codeBlockLines.join('\n')}</code>
          </pre>
        );
        inCodeBlock = false;
        codeBlockLines = [];
      } else {
        // Start of code block
        inCodeBlock = true;
        codeBlockLang = trimmed.substring(3).trim();
      }
      continue;
    }
    
    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    // Parse Markdown tables
    if (trimmed.startsWith('|') && i + 1 < lines.length) {
      const nextLineTrimmed = lines[i + 1].trim();
      if (nextLineTrimmed.startsWith('|') && (nextLineTrimmed.includes('---') || nextLineTrimmed.includes('-|-'))) {
        flushList(i);
        
        const headerRow = trimmed;
        const dataRows: string[] = [];
        
        let j = i + 2;
        while (j < lines.length) {
          const rowTrimmed = lines[j].trim();
          if (rowTrimmed.startsWith('|')) {
            dataRows.push(rowTrimmed);
            j++;
          } else {
            break;
          }
        }
        
        const parseRowCells = (rowStr: string) => {
          const cells = rowStr.split('|').map(c => c.trim());
          if (cells[0] === '') cells.shift();
          if (cells[cells.length - 1] === '') cells.pop();
          return cells;
        };
        
        const headers = parseRowCells(headerRow);
        const rows = dataRows.map(r => parseRowCells(r));
        
        elements.push(
          <div key={`table-wrapper-${i}`} style={{ overflowX: 'auto', margin: '12px 0', border: '1px solid rgba(0, 240, 255, 0.15)', borderRadius: '8px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', fontFamily: 'var(--font-mono)' }}>
              <thead>
                <tr style={{ backgroundColor: 'rgba(0, 240, 255, 0.08)', borderBottom: '1px solid rgba(0, 240, 255, 0.2)' }}>
                  {headers.map((h, idx) => (
                    <th key={idx} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                      {parseInline(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rIdx) => (
                  <tr 
                    key={rIdx} 
                    style={{ 
                      backgroundColor: rIdx % 2 === 0 ? 'rgba(255, 255, 255, 0.01)' : 'rgba(0, 240, 255, 0.02)',
                      borderBottom: rIdx === rows.length - 1 ? 'none' : '1px solid rgba(255, 255, 255, 0.03)' 
                    }}
                  >
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} style={{ padding: '8px 12px', color: '#e2e8f0' }}>
                        {parseInline(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        
        i = j - 1;
        continue;
      }
    }
    
    // Check for list items
    const bulletMatch = line.match(/^(\s*)([*+-])\s+(.*)$/);
    const numberMatch = line.match(/^(\s*)(\d+)\.\s+(.*)$/);
    
    if (bulletMatch) {
      const indent = Math.floor(bulletMatch[1].length / 2); // 2 spaces per indent level
      const content = bulletMatch[3].trim();
      if (!currentList || currentList.ordered) {
        flushList(i);
        currentList = { items: [], ordered: false };
      }
      currentList.items.push({
        indent,
        content: parseInline(content)
      });
    } else if (numberMatch) {
      const indent = Math.floor(numberMatch[1].length / 2);
      const content = numberMatch[3].trim();
      if (!currentList || !currentList.ordered) {
        flushList(i);
        currentList = { items: [], ordered: true };
      }
      currentList.items.push({
        indent,
        content: parseInline(content)
      });
    } else {
      flushList(i);
      
      if (trimmed === '') {
        elements.push(<div key={`br-${i}`} style={{ height: '8px' }} />);
      } else if (trimmed.startsWith('#')) {
        const headerMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
        if (headerMatch) {
          const level = headerMatch[1].length;
          const content = headerMatch[2];
          const fontSize = level === 1 ? '1.4rem' : level === 2 ? '1.25rem' : '1.1rem';
          const margin = level === 1 ? '16px 0 8px' : '12px 0 6px';
          elements.push(
            <div 
              key={`h-${i}`} 
              style={{ 
                fontSize, 
                fontWeight: 600, 
                color: '#ffffff', 
                margin,
                borderBottom: level === 1 ? '1px solid rgba(0, 240, 255, 0.2)' : 'none',
                paddingBottom: level === 1 ? '4px' : '0'
              }}
            >
              {parseInline(content)}
            </div>
          );
        } else {
          elements.push(
            <p key={`p-${i}`} style={{ margin: '6px 0', lineHeight: 1.6 }}>
              {parseInline(line)}
            </p>
          );
        }
      } else {
        elements.push(
          <p key={`p-${i}`} style={{ margin: '6px 0', lineHeight: 1.6 }}>
            {parseInline(line)}
          </p>
        );
      }
    }
  }
  
  flushList(lines.length);
  return elements;
};

// Formats seconds into HH:MM:SS or MM:SS format
export const formatTimeLeft = (seconds: number) => {
  if (seconds <= 0) return '00:00';
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

// Wake-word config
export const WAKE_WORDS = ['vexa', 'векса', 'вексу', 'вексе', 'jarvis', 'джарвис', 'жарвис', 'джарвиз', 'харвис'];

// Sound Player utilities
export const playBeep = (freq = 880, dur = 0.25) => {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + dur);
    ctx.close();
  } catch (_) {}
};

let alarmAudioContext: AudioContext | null = null;
let alarmIntervalId: any = null;

export const playAlarmSound = () => {
  if (alarmAudioContext || alarmIntervalId) return;
  try {
    const AC = window.AudioContext || (window as any).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    alarmAudioContext = ctx;

    const playPulse = () => {
      if (ctx.state === 'closed') return;
      
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(880, ctx.currentTime);
      osc1.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.4);
      gain1.gain.setValueAtTime(0.3, ctx.currentTime);
      gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc1.start(ctx.currentTime);
      osc1.stop(ctx.currentTime + 0.4);

      setTimeout(() => {
        if (ctx.state === 'closed') return;
        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(1046.50, ctx.currentTime);
        osc2.frequency.exponentialRampToValueAtTime(523.25, ctx.currentTime + 0.35);
        gain2.gain.setValueAtTime(0.25, ctx.currentTime);
        gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
        osc2.start(ctx.currentTime);
        osc2.stop(ctx.currentTime + 0.35);
      }, 150);
    };

    playPulse();
    alarmIntervalId = setInterval(playPulse, 1200);
  } catch (err) {
    console.error('Failed to play alarm sound:', err);
  }
};

export const stopAlarmSound = () => {
  if (alarmIntervalId) {
    clearInterval(alarmIntervalId);
    alarmIntervalId = null;
  }
  if (alarmAudioContext) {
    try {
      alarmAudioContext.close();
    } catch (_) {}
    alarmAudioContext = null;
  }
};

// Global Fetch Interceptor to automatically add Auth headers and capture 401s
export const initFetchInterceptor = () => {
  const originalFetch = window.fetch;
  (window as any).fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const token = localStorage.getItem('jarvis_auth_token');
    const urlStr = typeof input === 'string' ? input : (input instanceof URL ? input.toString() : (input as Request).url);
    
    if (token && !urlStr.includes('/api/auth/')) {
      init = init || {};
      const headers = init.headers ? { ...init.headers } : {};
      (headers as any)['Authorization'] = `Bearer ${token}`;
      init.headers = headers;
    }
    
    const res = await originalFetch(input, init);
    if (res.status === 401 && !urlStr.includes('/api/auth/')) {
      localStorage.removeItem('jarvis_auth_token');
      window.dispatchEvent(new Event('jarvis-unauthorized'));
    }
    return res;
  };
};
