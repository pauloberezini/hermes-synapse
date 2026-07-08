import { CheckCircle2, XCircle, Clock, Database, Layers } from 'lucide-react';
import type { DecisionLog } from '../types';
import { styles } from '../styles';

interface LogsTabProps {
  logs: DecisionLog[];
  selectedLog: DecisionLog | null;
  setSelectedLog: (log: DecisionLog | null) => void;
}

export function LogsTab({
  logs,
  selectedLog,
  setSelectedLog
}: LogsTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>TELEMETRY AND DECISION LOGS</h2>
          <p style={styles.tabSubtitle}>Analysis of latency, token consumption, and decisions made</p>
        </div>
      </div>

      <div style={styles.logsLayout} className="logs-layout">
        {/* Logs List */}
        <div style={styles.logsListWrapper} className="glass-panel">
          <div style={styles.logsListHeader}>
            <span>Request History (Last 20)</span>
          </div>
          
          <div style={styles.logsList}>
            {logs.length === 0 ? (
              <div style={styles.emptyLogs}>No logs at the moment, Sir. Start a conversation with Hermes.</div>
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
            )}
          </div>
        </div>

        {/* Log Detail Viewer */}
        <div style={styles.logDetailWrapper} className="glass-panel">
          {selectedLog ? (
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
                  <span style={styles.detailStatLabel}>Session / Source</span>
                  <span style={styles.detailStatValue}>{selectedLog.session_id}</span>
                </div>
                <div style={styles.detailStatBox}>
                  <span style={styles.detailStatLabel}>Latency</span>
                  <span style={{ ...styles.detailStatValue, color: '#00f0ff' }}>{selectedLog.latency_ms} ms</span>
                </div>
                <div style={styles.detailStatBox}>
                  <span style={styles.detailStatLabel}>Tokens (Approx.)</span>
                  <span style={styles.detailStatValue}>{selectedLog.prompt_tokens_estimate} tokens</span>
                </div>
              </div>

              <div style={styles.detailBlock}>
                <h4 style={styles.detailBlockTitle}>Creator Prompt (Prompt)</h4>
                <div style={styles.codeBlock}>{selectedLog.user_message}</div>
              </div>

              {selectedLog.traces && selectedLog.traces.length > 0 && (
                <div style={styles.detailBlock}>
                  <h4 style={styles.detailBlockTitle}>Orchestrator Graph Trace</h4>
                  <div style={styles.traceTimeline}>
                    {selectedLog.traces.map((trace, idx) => (
                      <div key={idx} style={styles.traceNode}>
                        <div style={styles.traceNodeHeader}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{
                              ...styles.traceStatusDot,
                              backgroundColor: trace.status === 'error' ? 'var(--danger)' : (trace.status === 'warning' ? 'var(--warning)' : 'var(--accent-cyan)'),
                              boxShadow: trace.status === 'error' ? '0 0 8px var(--danger)' : '0 0 8px rgba(0, 240, 255, 0.4)'
                            }} />
                            <span style={styles.traceAgentName}>{trace.agent.toUpperCase()}</span>
                          </div>
                          <span style={styles.traceTime}>{trace.timestamp}</span>
                        </div>
                        <div style={styles.traceActionLabel}>{trace.action}</div>
                        <div style={styles.traceMessage}>{trace.message}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div style={styles.detailBlock}>
                <h4 style={styles.detailBlockTitle}>Vexa Generation Result</h4>
                <div style={{ ...styles.codeBlock, borderLeft: '3px solid var(--accent-cyan)' }}>
                  {selectedLog.assistant_response}
                </div>
              </div>

              {selectedLog.error && (
                <div style={styles.detailBlock}>
                  <h4 style={{ ...styles.detailBlockTitle, color: '#ef4444' }}>Error Log</h4>
                  <div style={{ ...styles.codeBlock, color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.05)' }}>
                    {selectedLog.error}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={styles.emptyDetail}>
              <Layers size={48} style={{ color: 'var(--text-dim)', marginBottom: 16 }} />
              <span>Select a log from the list on the left to view detailed telemetry data, Sir.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
