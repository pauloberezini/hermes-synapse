import React from 'react';
import { Activity, Database, Trash2 } from 'lucide-react';
import { styles } from '../styles';

interface MemoryTabProps {
  noteTitle: string;
  setNoteTitle: (val: string) => void;
  noteContent: string;
  setNoteContent: (val: string) => void;
  isIndexing: boolean;
  documents: { id: string; title: string }[];
  memorySearchQuery: string;
  setMemorySearchQuery: (val: string) => void;
  isSearchingMemory: boolean;
  memorySearchResults: { title: string; content: string; score: number }[] | null;
  
  handleIndexNote: (e: React.FormEvent) => void;
  handleSearchMemory: (e: React.FormEvent) => void;
  handleClearMemorySearch: () => void;
  handleDeleteDocument: (docId: string) => void;
}

export function MemoryTab({
  noteTitle,
  setNoteTitle,
  noteContent,
  setNoteContent,
  isIndexing,
  documents,
  memorySearchQuery,
  setMemorySearchQuery,
  isSearchingMemory,
  memorySearchResults,
  handleIndexNote,
  handleSearchMemory,
  handleClearMemorySearch,
  handleDeleteDocument
}: MemoryTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>KNOWLEDGE BASE AND DOCUMENTS (RAG)</h2>
          <p style={styles.tabSubtitle}>Adding notes and documents to Vexa's long-term memory</p>
        </div>
      </div>

      <div style={styles.logsLayout}>
        {/* Note Indexing Form */}
        <form onSubmit={handleIndexNote} style={styles.configForm} className="glass-panel">
          <h3 style={{ fontSize: '1.1rem', color: 'var(--accent-cyan)', marginBottom: '8px' }}>Record a new memory</h3>
          
          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Note / Document Title</label>
            <input 
              type="text" 
              value={noteTitle} 
              onChange={e => setNoteTitle(e.target.value)} 
              placeholder="e.g. Passwords, Protocol 14, Instructions..." 
              style={styles.chatInput} 
              className="form-input"
            />
          </div>

          <div style={styles.formGroup}>
            <label style={styles.formLabel}>Text Content</label>
            <textarea 
              value={noteContent} 
              onChange={e => setNoteContent(e.target.value)} 
              placeholder="Enter memory text, facts, or instructions for Vexa to remember..."
              style={styles.formTextarea} 
              className="form-input" 
              rows={8}
            />
          </div>

          <button type="submit" className="btn-primary" disabled={isIndexing} style={{ alignSelf: 'flex-start' }}>
            <Activity size={16} />
            <span>{isIndexing ? 'Indexing...' : 'Write to Memory'}</span>
          </button>
        </form>

        {/* Indexed Documents List */}
        <div style={styles.logsListWrapper} className="glass-panel">
          <div style={styles.logsListHeader}>
            <span>Saved Documents ({documents.length})</span>
          </div>
          
          {/* Search Bar */}
          <form onSubmit={handleSearchMemory} style={{ display: 'flex', gap: '8px', padding: '12px', borderBottom: '1px solid rgba(0, 240, 255, 0.08)' }}>
            <input 
              type="text" 
              value={memorySearchQuery} 
              onChange={e => setMemorySearchQuery(e.target.value)} 
              placeholder="Semantic search (by meaning)..." 
              style={{ ...styles.chatInput, height: '36px', fontSize: '0.85rem' }} 
              className="form-input"
            />
            <button type="submit" className="btn-primary" disabled={isSearchingMemory} style={{ padding: '0 12px', height: '36px', flexShrink: 0 }}>
              <span>{isSearchingMemory ? 'Searching...' : 'Search'}</span>
            </button>
            {memorySearchResults !== null && (
              <button type="button" onClick={handleClearMemorySearch} className="btn-primary" style={{ padding: '0 12px', height: '36px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', flexShrink: 0 }}>
                <span>Reset</span>
              </button>
            )}
          </form>
          
          <div style={styles.logsList}>
            {memorySearchResults !== null ? (
              memorySearchResults.length === 0 ? (
                <div style={styles.emptyLogs}>Nothing found for your query, Sir.</div>
              ) : (
                memorySearchResults.map((match, idx) => (
                  <div 
                    key={idx} 
                    style={{
                      ...styles.logCard,
                      borderColor: 'rgba(0, 240, 255, 0.15)',
                      cursor: 'default',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      padding: '16px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Database size={14} style={{ color: 'var(--accent-cyan)' }} />
                        <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#ffffff' }}>{match.title}</span>
                      </div>
                      <span style={{
                        fontSize: '0.75rem',
                        color: 'var(--accent-cyan)',
                        backgroundColor: 'rgba(0, 240, 255, 0.05)',
                        border: '1px solid rgba(0, 240, 255, 0.15)',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontFamily: 'var(--font-mono)'
                      }}>
                        {Math.round(match.score * 100)}% match
                      </span>
                    </div>
                    <div style={{
                      fontSize: '0.85rem',
                      color: 'var(--text-dim)',
                      backgroundColor: 'rgba(0, 0, 0, 0.2)',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      border: '1px solid rgba(255, 255, 255, 0.03)',
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.4
                    }}>
                      {match.content}
                    </div>
                  </div>
                ))
              )
            ) : (
              documents.length === 0 ? (
                <div style={styles.emptyLogs}>Vexa's memory is empty, Sir. Add a note on the left.</div>
              ) : (
                documents.map((doc, idx) => (
                  <div 
                    key={idx} 
                    style={{
                      ...styles.logCard,
                      borderColor: 'rgba(0, 240, 255, 0.08)',
                      cursor: 'default',
                      display: 'flex',
                      flexDirection: 'row',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '16px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <Database size={16} style={{ color: 'var(--accent-cyan)' }} />
                      <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>{doc.title}</span>
                    </div>
                    <button 
                      type="button"
                      onClick={() => handleDeleteDocument(doc.id)} 
                      className="btn-primary" 
                      style={{ 
                        padding: '6px', 
                        border: '1px solid rgba(239, 68, 68, 0.3)', 
                        background: 'transparent',
                        color: '#ef4444' 
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
