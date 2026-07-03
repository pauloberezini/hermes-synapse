import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  Wifi, 
  WifiOff, 
  RefreshCw, 
  FileText, 
  Search, 
  Plus, 
  BookOpen, 
  Trash2 
} from 'lucide-react';
import { renderMarkdown } from '../utils';

interface ObsidianTabProps {
  authToken: string | null;
}

export function ObsidianTab({ authToken }: ObsidianTabProps) {
  const [status, setStatus] = useState<null | { reachable: boolean; message: string }>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [indexedCount, setIndexedCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState('');
  const [activePanel, setActivePanel] = useState<'notes' | 'search' | 'create'>('notes');

  const [selectedNotePath, setSelectedNotePath] = useState<string | null>(null);
  const [selectedNoteContent, setSelectedNoteContent] = useState<string | null>(null);
  const [isLoadingNote, setIsLoadingNote] = useState(false);

  const headers = useMemo(() => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authToken) h['Authorization'] = `Bearer ${authToken}`;
    return h;
  }, [authToken]);

  const handleSelectNote = async (notePath: string) => {
    setSelectedNotePath(notePath);
    setIsLoadingNote(true);
    setSelectedNoteContent(null);
    try {
      const r = await fetch(`/api/obsidian/note?path=${encodeURIComponent(notePath)}`, { headers });
      if (r.ok) {
        const data = await r.json();
        setSelectedNoteContent(data.content);
      } else {
        setSelectedNoteContent(`Load error: HTTP ${r.status}`);
      }
    } catch (e: any) {
      setSelectedNoteContent(`Error loading note: ${e.message}`);
    } finally {
      setIsLoadingNote(false);
    }
  };

  const handleDeleteNote = async (notePath: string) => {
    if (!window.confirm(`Sir, are you sure you want to delete the note "${notePath}"?`)) return;
    try {
      const r = await fetch(`/api/obsidian/note?path=${encodeURIComponent(notePath)}`, {
        method: 'DELETE',
        headers
      });
      if (r.ok) {
        setSelectedNotePath(null);
        setSelectedNoteContent(null);
        fetchNotes();
      } else {
        alert(`Error deleting note: HTTP ${r.status}`);
      }
    } catch (e: any) {
      alert(`Error deleting note: ${e.message}`);
    }
  };

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/obsidian/status', { headers });
      const data = await r.json();
      setStatus(data);
    } catch { setStatus({ reachable: false, message: 'Backend connection error' }); }
  }, [headers]);

  const fetchNotes = useCallback(async () => {
    try {
      const r = await fetch('/api/obsidian/notes', { headers });
      const data = await r.json();
      setNotes(data.notes || []);
      setIndexedCount(data.indexed_count || 0);
    } catch { }
  }, [headers]);

  const handleSync = async () => {
    setSyncing(true); setSyncResult('');
    try {
      const r = await fetch('/api/obsidian/sync', { method: 'POST', headers });
      const data = await r.json();
      setSyncResult(data.message || JSON.stringify(data));
      fetchNotes();
    } catch (e: any) { setSyncResult('Sync error: ' + e.message); }
    setSyncing(false);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const r = await fetch(`/api/obsidian/search?q=${encodeURIComponent(searchQuery)}`, { headers });
      const data = await r.json();
      setSearchResults(data);
    } catch { }
  };

  const handleCreate = async () => {
    if (!newTitle.trim() || !newContent.trim()) return;
    setCreating(true); setCreateResult('');
    try {
      const r = await fetch('/api/obsidian/notes', {
        method: 'POST', headers,
        body: JSON.stringify({ title: newTitle, content: newContent, folder: 'Jarvis' })
      });
      const data = await r.json();
      setCreateResult(data.message || data.error || JSON.stringify(data));
      if (data.status === 'created') { setNewTitle(''); setNewContent(''); fetchNotes(); }
    } catch (e: any) { setCreateResult('Error: ' + e.message); }
    setCreating(false);
  };

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchStatus(); fetchNotes(); }, [fetchStatus, fetchNotes]);

  const panelBtnStyle = (active: boolean): React.CSSProperties => ({
    padding: '8px 16px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontSize: '0.82rem',
    fontWeight: 600, transition: 'all 0.2s',
    background: active ? 'rgba(0,240,255,0.15)' : 'rgba(255,255,255,0.05)',
    color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
    boxShadow: active ? '0 0 10px rgba(0,240,255,0.1)' : 'none',
  });

  return (
    <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: '20px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 className="glow-text-cyan" style={{ margin: 0, fontSize: '1.3rem', letterSpacing: '0.15em' }}>
            📓 OBSIDIAN KNOWLEDGE BASE
          </h2>
          <p style={{ margin: '4px 0 0', color: 'var(--text-dim)', fontSize: '0.82rem' }}>
            Personal Notes Vault · RAG Search · Auto-creation
          </p>
        </div>

        {/* Status badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 16px',
          borderRadius: '20px',
          background: status?.reachable ? 'rgba(0,255,160,0.08)' : 'rgba(255,60,60,0.08)',
          border: `1px solid ${status?.reachable ? 'rgba(0,255,160,0.25)' : 'rgba(255,60,60,0.25)'}`,
        }}>
          {status?.reachable ? <Wifi size={14} style={{ color: '#00ffa0' }} /> : <WifiOff size={14} style={{ color: '#ff4040' }} />}
          <span style={{ fontSize: '0.78rem', color: status?.reachable ? '#00ffa0' : '#ff6060' }}>
            {status ? status.message : 'Checking...'}
          </span>
          <button onClick={fetchStatus} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: 0 }}>
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        {[
          { label: 'Notes in Vault', value: notes.length, color: 'var(--accent-cyan)' },
          { label: 'Indexed', value: indexedCount, color: '#00ffa0' },
          { label: 'Tools', value: 4, color: '#a78bfa' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            flex: 1, minWidth: '140px', padding: '14px 18px', borderRadius: '12px',
            background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
          }}>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color }}>{value}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '2px' }}>{label}</div>
          </div>
        ))}
        <button
          onClick={handleSync}
          disabled={syncing}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '14px 22px', borderRadius: '12px', border: '1px solid rgba(0,240,255,0.25)',
            background: 'rgba(0,240,255,0.05)', color: 'var(--accent-cyan)',
            cursor: syncing ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 600,
            opacity: syncing ? 0.6 : 1, transition: 'all 0.2s',
          }}
        >
          <RefreshCw size={16} style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />
          {syncing ? 'Syncing...' : 'Sync'}
        </button>
      </div>
      {syncResult && (
        <div style={{ padding: '10px 16px', borderRadius: '8px', background: 'rgba(0,255,160,0.06)',
          border: '1px solid rgba(0,255,160,0.2)', color: '#00ffa0', fontSize: '0.82rem' }}>
          ✅ {syncResult}
        </div>
      )}

      {/* Panel tabs */}
      <div style={{ display: 'flex', gap: '8px' }}>
        {(['notes', 'search', 'create'] as const).map(p => (
          <button key={p} style={panelBtnStyle(activePanel === p)} onClick={() => setActivePanel(p)}>
            {p === 'notes' && <><FileText size={13} style={{ display: 'inline', marginRight: 5 }} />Notes</>}
            {p === 'search' && <><Search size={13} style={{ display: 'inline', marginRight: 5 }} />Search</>}
            {p === 'create' && <><Plus size={13} style={{ display: 'inline', marginRight: 5 }} />Create</>}
          </button>
        ))}
      </div>

      {/* Notes panel */}
      {activePanel === 'notes' && (
        <div style={{ display: 'flex', gap: '20px', minHeight: '400px', width: '100%' }}>
          {/* Left panel: List of notes */}
          <div style={{
            width: '280px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            maxHeight: '550px',
            overflowY: 'auto',
            paddingRight: '8px',
            flexShrink: 0
          }}>
            {notes.length === 0 && (
              <div style={{ color: 'var(--text-dim)', fontSize: '0.85rem', padding: '20px', textAlign: 'center' }}>
                {status?.reachable
                  ? 'Vault is empty. Click "Sync" to load notes.'
                  : 'Obsidian is unavailable. Run the app and enable the Local REST API plugin.'}
              </div>
            )}
            {notes.map(n => {
              const isActive = selectedNotePath === n;
              return (
                <div 
                  key={n} 
                  onClick={() => handleSelectNote(n)}
                  style={{
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '10px', 
                    padding: '10px 14px', 
                    borderRadius: '8px',
                    background: isActive ? 'rgba(0,240,255,0.08)' : 'rgba(255,255,255,0.02)', 
                    border: `1px solid ${isActive ? 'rgba(0,240,255,0.3)' : 'rgba(255,255,255,0.06)'}`,
                    fontSize: '0.82rem', 
                    color: isActive ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    transition: 'all 0.15s'
                  }}
                  className="list-item-hover"
                >
                  <FileText size={14} style={{ color: isActive ? 'var(--accent-cyan)' : 'var(--text-dim)', flexShrink: 0 }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }} title={n}>{n}</span>
                </div>
              );
            })}
          </div>

          {/* Right panel: Note Content viewer */}
          <div style={{
            flex: 1,
            background: 'rgba(255,255,255,0.01)',
            border: '1px solid rgba(255,255,255,0.05)',
            borderRadius: '12px',
            padding: '20px',
            maxHeight: '550px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column'
          }} className="glass-panel">
            {selectedNotePath ? (
              <>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  borderBottom: '1px solid rgba(255,255,255,0.08)',
                  paddingBottom: '12px',
                  marginBottom: '16px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FileText size={16} style={{ color: 'var(--accent-cyan)' }} />
                    <span style={{ fontWeight: 600, fontSize: '0.95rem', color: '#fff' }}>
                      {selectedNotePath}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => handleSelectNote(selectedNotePath)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: '4px', display: 'flex', alignItems: 'center' }}
                      title="Refresh content"
                    >
                      <RefreshCw size={13} />
                    </button>
                    <button
                      onClick={() => handleDeleteNote(selectedNotePath)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px', display: 'flex', alignItems: 'center' }}
                      title="Delete note"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
                {isLoadingNote ? (
                  <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
                    Loading content...
                  </div>
                ) : (
                  <div style={{
                    fontSize: '0.88rem',
                    lineHeight: 1.6,
                    color: 'var(--text-secondary)'
                  }} className="markdown-body">
                    {selectedNoteContent ? renderMarkdown(selectedNoteContent) : <span style={{ color: 'var(--text-dim)' }}>Note is empty.</span>}
                  </div>
                )}
              </>
            ) : (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: 'var(--text-dim)',
                fontSize: '0.85rem',
                gap: '8px',
                padding: '40px 0'
              }}>
                <BookOpen size={24} style={{ color: 'rgba(255,255,255,0.1)' }} />
                <span>Select a note from the list on the left to view its content</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Search panel */}
      {activePanel === 'search' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Semantic search across notes..."
              className="form-input"
              style={{ flex: 1 }}
            />
            <button onClick={handleSearch} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Search size={15} /> Search
            </button>
          </div>
          {searchResults.length === 0 && searchQuery && (
            <div style={{ color: 'var(--text-dim)', fontSize: '0.85rem', padding: '12px' }}>Nothing found.</div>
          )}
          {searchResults.map((r, i) => (
            <div key={i} style={{
              padding: '14px 18px', borderRadius: '10px',
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(0,240,255,0.1)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--accent-cyan)' }}>
                  📄 {r.title || r.note_path || 'Note'}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                  score: {(r.score * 100).toFixed(0)}%
                </span>
              </div>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {(r.content || '').slice(0, 400)}
              </p>
              {r.note_path && (
                <div style={{ marginTop: '6px', fontSize: '0.72rem', color: 'var(--text-dim)' }}>📁 {r.note_path}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create panel */}
      {activePanel === 'create' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '700px' }}>
          <input
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            placeholder="Note title..."
            className="form-input"
          />
          <textarea
            value={newContent}
            onChange={e => setNewContent(e.target.value)}
            placeholder="Note content in Markdown format..."
            className="form-input"
            rows={10}
            style={{ resize: 'vertical', fontFamily: 'monospace', fontSize: '0.85rem' }}
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newTitle.trim() || !newContent.trim()}
            className="btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '8px', alignSelf: 'flex-start' }}
          >
            <BookOpen size={16} />
            {creating ? 'Creating...' : 'Create note in Obsidian'}
          </button>
          {createResult && (
            <div style={{
              padding: '10px 16px', borderRadius: '8px', fontSize: '0.82rem',
              background: createResult.toLowerCase().includes('created') ? 'rgba(0,255,160,0.06)' : 'rgba(255,60,60,0.06)',
              border: createResult.toLowerCase().includes('created') ? '1px solid rgba(0,255,160,0.2)' : '1px solid rgba(255,60,60,0.2)',
              color: createResult.toLowerCase().includes('created') ? '#00ffa0' : '#ff6060',
            }}>
              {createResult}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
