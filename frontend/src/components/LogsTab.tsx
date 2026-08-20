import { CheckCircle2, XCircle, Clock, Database, Layers, Activity, FileText, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { DecisionLog, ActivityLog } from '../types';
import { styles } from '../styles';

interface LogsTabProps {
  logs: DecisionLog[];
  activityLogs: ActivityLog[];
  selectedLog: DecisionLog | null;
  setSelectedLog: (log: DecisionLog | null) => void;
  clearLogs: () => void;
}

export function LogsTab({
  logs,
  activityLogs,
  selectedLog,
  setSelectedLog,
  clearLogs
}: LogsTabProps) {
  const [activeSubTab, setActiveSubTab] = useState<'decision' | 'activity'>('decision');

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>TELEMETRY AND ACTIVITY</h2>
          <p style={styles.tabSubtitle}>System logs, decision traces, and internal activity feed</p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div className="glass-panel" style={{ display: 'flex', padding: '4px', borderRadius: '8px', gap: '4px' }}>
            <button 
              onClick={() => setActiveSubTab('decision')}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '5px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                fontSize: '0.78rem', fontWeight: 600, fontFamily: 'inherit',
                backgroundColor: activeSubTab === 'decision' ? 'rgba(0, 240, 255, 0.15)' : 'transparent',
                color: activeSubTab === 'decision' ? 'var(--accent-cyan)' : 'var(--text-dim)',
                transition: 'all 0.2s',
              }}
            >
              <FileText size={14} /> Decision Logs
            </button>
            <button 
              onClick={() => setActiveSubTab('activity')}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '5px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                fontSize: '0.78rem', fontWeight: 600, fontFamily: 'inherit',
                backgroundColor: activeSubTab === 'activity' ? 'rgba(0, 240, 255, 0.15)' : 'transparent',
                color: activeSubTab === 'activity' ? 'var(--accent-cyan)' : 'var(--text-dim)',
                transition: 'all 0.2s',
              }}
            >
              <Activity size={14} /> Activity Feed
            </button>
          </div>
          <button
            onClick={clearLogs}
            title="Clear Logs"
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--text-dim)', display: 'flex', alignItems: 'center', padding: '4px',
              borderRadius: '4px', transition: 'color 0.2s',
            }}
            onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-dim)')}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div style={styles.logsLayout} className="logs-layout">
        <div style={styles.logsListWrapper} className="glass-panel">
          <div style={styles.logsListHeader}>
            <span>{activeSubTab === 'decision' ? 'Request History' : 'Activity Feed'}</span>
          </div>
          
          <div style={styles.logsList}>
            {activeSubTab === 'decision' ? (
              logs.length === 0 ? (
                <div style={styles.emptyLogs}>No decision logs found, Sir.</div>
              ) : (
                logs.map((log, index) => (
                  <div 
                    key={index} 
                    style={{
                      ...styles.logCard,
                      backgroundColor: selectedLog === log ? 'rgba(0, 240, 255, 0.08)' : 'transparent',
                      borderColor: selectedLog === log ? 'var(--accent-cyan)' : 'rgba(0, 240, 255, 0.08)'
                    }}
                    onClick={() => setSelectedLog(log)}
                  >
                    <div style={styles.logCardHeader}>
                      <span style={styles.logTime}>{log.timestamp}</span>
                      <span style={log.success ? styles.statusSuccess : styles.statusError}>
                        {log.success ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                        {log.success ? 'Success' : 'Error'}
                      </span>
                    </div>
                    <div style={styles.logCardQuery}>{log.user_message}</div>
                    <div style={styles.logCardStats}>
                      <span style={styles.statItem}><Clock size={12} /> {log.latency_ms} ms</span>
                      <span style={styles.statItem}><Database size={12} /> ~{log.prompt_tokens_estimate} tkn</span>
                    </div>
                  </div>
                ))
              )
            ) : (
              activityLogs.length === 0 ? (
                <div style={styles.emptyLogs}>No activity recorded, Sir.</div>
              ) : (
                activityLogs.map((log, index) => (
                  <div key={index} style={styles.logCard}>
                    <div style={styles.logCardHeader}>
                      <span style={styles.logTime}>{log.timestamp}</span>
                      <span style={{
                        fontSize: '0.7rem', padding: '1px 6px',
                        border: '1px solid rgba(0, 240, 255, 0.3)',
                        borderRadius: '3px', color: 'var(--accent-cyan)',
                        fontFamily: 'monospace', fontWeight: 600,
                      }}>{log.source}</span>
                    </div>
                    <div style={styles.logCardQuery}>{log.message}</div>
                  </div>
                ))
              )
            )}
          </div>
        </div>

        <div style={styles.logDetailWrapper} className="glass-panel">
          {activeSubTab === 'decision' && selectedLog ? (
            <div style={styles.logDetail}>
              <div style={styles.detailHeader}>
                <h3 style={styles.detailTitle}>TELEMETRY DETAILS</h3>
                <span style={styles.detailTime}>{selectedLog.timestamp}</span>
              </div>
              <div style={styles.detailGrid}>
                <div style={styles.detailStatBox}>
                  <span style={styles.detailStatLabel}>Model</span>
                  <span style={styles.detailStatValue}>{selectedLog.model}</span>
                </div>
                <div style={styles.detailStatBox}>
                  <span style={styles.detailStatLabel}>Latency</span>
                  <span style={{ ...styles.detailStatValue, color: '#00f0ff' }}>{selectedLog.latency_ms} ms</span>
                </div>
              </div>
              <div style={styles.detailBlock}>
                <h4 style={styles.detailBlockTitle}>Creator Prompt</h4>
                <div style={styles.codeBlock}>{selectedLog.user_message}</div>
              </div>
              <div style={styles.detailBlock}>
                <h4 style={styles.detailBlockTitle}>SYNAPSE Generation Result</h4>
                <div style={{ ...styles.codeBlock, borderLeft: '3px solid var(--accent-cyan)' }}>
                  {selectedLog.assistant_response}
                </div>
              </div>
            </div>
          ) : (
            <div style={styles.emptyDetail}>
              <Layers size={48} style={{ color: 'var(--text-dim)', marginBottom: 16 }} />
              <span>Select an item to view details, Sir.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
