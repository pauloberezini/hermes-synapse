import { Trash2 } from 'lucide-react';
import type { ActivityLog } from '../types';
import { styles } from '../styles';

interface ActivityTabProps {
  isGenerating: boolean;
  activityLogs: ActivityLog[];
  handleClearActivityLogs: () => void;
}

export function ActivityTab({
  isGenerating,
  activityLogs,
  handleClearActivityLogs
}: ActivityTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>CORE ACTIVITY AND COGNITION LOGS</h2>
          <p style={styles.tabSubtitle}>Real-time monitoring of background processes and chain-of-thought</p>
        </div>
        <div style={{ ...styles.detailStatBox, minWidth: '140px' }}>
          <span style={styles.detailStatLabel}>Current Status</span>
          <span style={{ 
            ...styles.detailStatValue, 
            color: isGenerating ? 'var(--accent-cyan)' : 'var(--accent-green)' 
          }}>
            {isGenerating ? '🧠 COGNITION' : '🟢 STANDBY'}
          </span>
        </div>
      </div>

      <div style={{ ...styles.logsLayout, gridTemplateColumns: '1fr' }}>
        <div style={{ ...styles.logsListWrapper, maxHeight: 'calc(100vh - 240px)' }} className="glass-panel">
          <div style={{ ...styles.logsListHeader, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Core Activity Feed (Last 200 events)</span>
            <button 
              onClick={handleClearActivityLogs} 
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-dim)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '0.8rem'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = '#ef4444')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-dim)')}
            >
              <Trash2 size={14} />
              <span>Clear Log</span>
            </button>
          </div>
          
          <div style={{ ...styles.logsList, maxHeight: 'calc(100vh - 290px)' }}>
            {activityLogs.length === 0 ? (
              <div style={styles.emptyLogs}>Activity feed is empty. Core is idle or waiting for background scanning, Sir.</div>
            ) : (
              activityLogs.map((log, index) => (
                <div 
                  key={index} 
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    padding: '12px',
                    borderBottom: '1px solid rgba(0, 240, 255, 0.08)',
                    backgroundColor: log.type === 'active' ? 'rgba(0, 240, 255, 0.03)' : 'transparent',
                    fontFamily: 'monospace',
                    fontSize: '0.9rem'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ 
                        color: 'var(--text-dim)',
                        fontSize: '0.8rem'
                      }}>
                        [{log.timestamp}]
                      </span>
                      <span style={{ 
                        color: log.type === 'active' ? 'var(--accent-cyan)' : 'var(--text-dim)',
                        fontWeight: 'bold',
                        fontSize: '0.8rem',
                        border: `1px solid ${log.type === 'active' ? 'rgba(0, 240, 255, 0.3)' : 'rgba(255, 255, 255, 0.1)'}`,
                        borderRadius: '3px',
                        padding: '1px 6px',
                        backgroundColor: log.type === 'active' ? 'rgba(0, 240, 255, 0.05)' : 'rgba(255, 255, 255, 0.02)'
                      }}>
                        {log.source.toUpperCase()}
                      </span>
                    </div>
                    
                    {log.token_cost > 0 && (
                      <span style={{ 
                        color: 'var(--accent-cyan)',
                        fontSize: '0.8rem'
                      }}>
                        Cost: ${log.token_cost.toFixed(6)}
                      </span>
                    )}
                  </div>
                  <div style={{ 
                    color: log.type === 'active' ? 'var(--text-light)' : 'var(--text-dim)',
                    lineHeight: '1.4',
                    whiteSpace: 'pre-wrap',
                    marginLeft: '4px'
                  }}>
                    {log.message}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
