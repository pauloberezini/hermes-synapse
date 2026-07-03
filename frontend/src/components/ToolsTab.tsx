import { 
  Activity, 
  Database, 
  Clock, 
  Trash2, 
  TrendingUp, 
  Plus, 
  Bell, 
  Shield, 
  Settings 
} from 'lucide-react';
import { styles } from '../styles';
import { formatTimeLeft } from '../utils';

interface ToolsTabProps {
  systemStats: { 
    cpu_load_percent: number; 
    ram_used_percent: number; 
    ram_total_gb: number; 
    disk_used_percent: number; 
    disk_total_gb: number; 
    disk_used_gb: number; 
    status: string;
  } | null;
  uploads: { name: string; size_bytes: number }[];
  timers: { 
    id: string; 
    label: string; 
    duration?: number; 
    time_left: number; 
    status: string; 
    created_at: string; 
    type?: string; 
    target_time?: string; 
  }[];
  marketPrices: Record<string, any>;
  priceAlerts: { 
    id: string; 
    symbol: string; 
    display_name: string; 
    target_price: number; 
    condition: string; 
    created_at: string; 
  }[];
  alertSymbol: string;
  setAlertSymbol: (symbol: string) => void;
  alertCondition: string;
  setAlertCondition: (condition: string) => void;
  alertPrice: string;
  setAlertPrice: (price: string) => void;
  
  handleCancelTimer: (id: string) => void;
  handleCreateAlert: () => void;
  handleCancelAlert: (id: string) => void;
}

export function ToolsTab({
  systemStats,
  uploads,
  timers,
  marketPrices,
  priceAlerts,
  alertSymbol,
  setAlertSymbol,
  alertCondition,
  setAlertCondition,
  alertPrice,
  setAlertPrice,
  handleCancelTimer,
  handleCreateAlert,
  handleCancelAlert
}: ToolsTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>TOOLS AND MONITORING</h2>
          <p style={styles.tabSubtitle}>Monitoring of system metrics and background processes</p>
        </div>
      </div>

      <div style={styles.toolsLayout}>
        {/* Left Column wrapper */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', height: '100%', overflowY: 'auto', paddingRight: '4px' }}>
          
          {/* System Metrics Telemetry */}
          <div style={{ ...styles.toolsMetricsWrapper, height: 'auto', flexShrink: 0 }} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <Activity size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>System Telemetry</span>
            </h3>
            
            {systemStats ? (
              <div style={styles.metricsList}>
                {/* CPU Loader */}
                <div style={styles.metricItem}>
                  <div style={styles.metricLabelRow}>
                    <span>CPU Load</span>
                    <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
                      {systemStats.cpu_load_percent}%
                    </span>
                  </div>
                  <div style={styles.progressBarBg}>
                    <div 
                      style={{
                        ...styles.progressBarFill,
                        width: `${systemStats.cpu_load_percent}%`,
                        backgroundColor: systemStats.cpu_load_percent > 80 ? 'var(--danger)' : (systemStats.cpu_load_percent > 50 ? 'var(--warning)' : 'var(--accent-cyan)'),
                        boxShadow: systemStats.cpu_load_percent > 80 ? '0 0 10px var(--danger)' : '0 0 10px rgba(0, 240, 255, 0.4)'
                      }}
                    />
                  </div>
                </div>

                {/* RAM usage */}
                <div style={styles.metricItem}>
                  <div style={styles.metricLabelRow}>
                    <span>RAM Usage</span>
                    <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
                      {systemStats.ram_used_percent}%
                    </span>
                  </div>
                  <div style={styles.progressBarBg}>
                    <div 
                      style={{
                        ...styles.progressBarFill,
                        width: `${systemStats.ram_used_percent}%`,
                        backgroundColor: systemStats.ram_used_percent > 85 ? 'var(--danger)' : 'var(--accent-cyan)',
                        boxShadow: '0 0 10px rgba(0, 240, 255, 0.4)'
                      }}
                    />
                  </div>
                  <div style={styles.metricHelpText}>
                    Total capacity: {systemStats.ram_total_gb} GB
                  </div>
                </div>

                {/* Disk Usage */}
                <div style={styles.metricItem}>
                  <div style={styles.metricLabelRow}>
                    <span>Disk Storage</span>
                    <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
                      {systemStats.disk_used_percent}%
                    </span>
                  </div>
                  <div style={styles.progressBarBg}>
                    <div 
                      style={{
                        ...styles.progressBarFill,
                        width: `${systemStats.disk_used_percent}%`,
                        backgroundColor: 'var(--accent-cyan)',
                        boxShadow: '0 0 10px rgba(0, 240, 255, 0.4)'
                      }}
                    />
                  </div>
                  <div style={styles.metricHelpText}>
                    Used {systemStats.disk_used_gb} GB of {systemStats.disk_total_gb} GB
                  </div>
                </div>

                <div style={styles.telemetryStatusRow}>
                  <span style={{ color: 'var(--text-muted)' }}>Core Status:</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className="pulse-dot" />
                    <span style={{ color: 'var(--success)', fontWeight: 600, fontSize: '0.85rem' }}>
                      {systemStats.status.toUpperCase()}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div style={styles.loadingStats}>
                <div className="pulse-dot" />
                <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Loading telemetry metrics...</span>
              </div>
            )}
          </div>

          {/* Datasets panel */}
          <div style={styles.datasetsWrapper} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <Database size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Active Datasets</span>
            </h3>
            
            {uploads.length === 0 ? (
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', padding: '16px 0' }}>
                No loaded datasets, Sir. Attach a CSV/Excel file in the chat.
              </div>
            ) : (
              <div style={styles.datasetList}>
                {uploads.map((upload, idx) => (
                  <div key={idx} style={styles.datasetItem}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                      <span style={styles.datasetName} title={upload.name}>{upload.name}</span>
                      <span style={styles.datasetSize}>
                        {(upload.size_bytes / 1024).toFixed(1)} KB
                      </span>
                    </div>
                    <Database size={14} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Center/Right Column: Active Timers & Available Tools */}
        <div style={styles.toolsContentRight}>
          
          {/* Active Timers List */}
          <div style={styles.toolsTimersWrapper} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <Clock size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Active Timers and Alerts</span>
            </h3>

            <div style={styles.timersList}>
              {timers.length === 0 ? (
                <div style={styles.emptyTimersMsg}>
                  No active timers found, Sir. You can ask Jarvis to set a timer or alarm in the chat or via Telegram.
                </div>
              ) : (
                timers.map((timer) => (
                  <div 
                    key={timer.id} 
                    style={{
                      ...styles.timerCard,
                      borderColor: timer.status === 'running' 
                        ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.2)' : 'rgba(0, 240, 255, 0.2)') 
                        : 'rgba(255, 255, 255, 0.05)',
                      backgroundColor: timer.status === 'running' 
                        ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.02)' : 'rgba(0, 240, 255, 0.02)') 
                        : 'rgba(255, 255, 255, 0.01)'
                    }}
                  >
                    <div style={styles.timerHeader}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <span style={styles.timerLabel}>{timer.label}</span>
                        {timer.status === 'running' && (
                          <button 
                            onClick={() => handleCancelTimer(timer.id)}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'rgba(239, 68, 68, 0.65)',
                              cursor: 'pointer',
                              padding: '4px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              borderRadius: '4px',
                              transition: 'all 0.2s',
                              marginLeft: '8px',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = '#ef4444';
                              e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'rgba(239, 68, 68, 0.65)';
                              e.currentTarget.style.backgroundColor = 'transparent';
                            }}
                            title="Cancel"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                      <span style={{
                        ...styles.timerStatusBadge,
                        color: timer.status === 'running' 
                            ? (timer.type === 'alarm' ? '#f97316' : 'var(--accent-cyan)') 
                            : 'var(--success)',
                        borderColor: timer.status === 'running' 
                            ? (timer.type === 'alarm' ? 'rgba(249, 115, 22, 0.3)' : 'rgba(0, 240, 255, 0.3)') 
                            : 'rgba(16, 185, 129, 0.3)'
                      }}>
                        {timer.status === 'running' 
                          ? (timer.type === 'alarm' ? 'WAITING' : 'COUNTDOWN') 
                          : 'COMPLETED'}
                      </span>
                    </div>

                    <div style={styles.timerBody}>
                      <div style={styles.countdownBox}>
                        <span style={styles.countdownVal}>
                          {timer.status === 'running' ? formatTimeLeft(timer.time_left) : '00:00'}
                        </span>
                        <span style={styles.countdownUnit}>
                          {timer.type === 'alarm' ? 'until ring' : 'remaining'}
                        </span>
                      </div>
                      <div style={styles.timerMeta}>
                        {timer.type === 'alarm' ? (
                          <div>Triggers at: {timer.target_time}</div>
                        ) : (
                          <div>Duration: {timer.duration} sec</div>
                        )}
                        <div>Started at: {timer.created_at}</div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Market & Price Alerts Monitor */}
          <div style={styles.toolsTimersWrapper} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <TrendingUp size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Market Quotes and Alerts</span>
            </h3>
            
            {/* Prices ticker */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: '8px', marginBottom: '16px' }}>
              {['TON', 'BTC', 'ETH', 'AAPL', 'TSLA'].map((sym) => (
                <div key={sym} style={{
                  padding: '8px',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.05)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center'
                }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>{sym}</span>
                  <span style={{ fontSize: '0.85rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', fontWeight: 600, marginTop: '2px' }}>
                    {marketPrices[sym] !== undefined ? (typeof marketPrices[sym] === 'number' ? `$${marketPrices[sym].toFixed(2)}` : marketPrices[sym]) : '...'}
                  </span>
                </div>
              ))}
            </div>

            {/* Create alert form */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <select 
                value={alertSymbol}
                onChange={(e) => setAlertSymbol(e.target.value)}
                className="form-input"
                style={{ padding: '6px 10px', fontSize: '0.8rem', flex: 1, minWidth: '80px', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
              >
                <option value="TON">TON</option>
                <option value="BTC">BTC</option>
                <option value="ETH">ETH</option>
                <option value="AAPL">AAPL</option>
                <option value="TSLA">TSLA</option>
              </select>

              <select 
                value={alertCondition}
                onChange={(e) => setAlertCondition(e.target.value)}
                className="form-input"
                style={{ padding: '6px 10px', fontSize: '0.8rem', flex: 1, minWidth: '80px', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
              >
                <option value="above">Above</option>
                <option value="below">Below</option>
              </select>

              <input 
                type="number" 
                placeholder="Price in USD" 
                value={alertPrice}
                onChange={(e) => setAlertPrice(e.target.value)}
                className="form-input"
                style={{ padding: '6px 10px', fontSize: '0.8rem', flex: 2, minWidth: '100px', height: '34px', background: 'rgba(6, 9, 19, 0.8)', border: '1px solid rgba(0, 240, 255, 0.15)', color: '#fff' }}
              />

              <button 
                onClick={handleCreateAlert}
                className="btn-primary"
                style={{ padding: '8px 12px', fontSize: '0.75rem', height: '34px' }}
              >
                <Plus size={12} /> Add
              </button>
            </div>

            {/* Alerts list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Active Alerts:</span>
              {priceAlerts.length === 0 ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', textAlign: 'center', padding: '12px 0' }}>
                  No active alerts.
                </div>
              ) : (
                priceAlerts.map((alert) => (
                  <div key={alert.id} style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(255,255,255,0.01)',
                    border: '1px solid rgba(255,255,255,0.03)'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Bell size={12} style={{ color: alert.condition === 'above' ? 'var(--accent-cyan)' : 'var(--accent-orange)' }} />
                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff' }}>{alert.display_name}</span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {alert.condition === 'above' ? '≥' : '≤'} ${alert.target_price.toFixed(2)}
                      </span>
                    </div>
                    <button 
                      onClick={() => handleCancelAlert(alert.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'rgba(239, 68, 68, 0.6)',
                        cursor: 'pointer',
                        padding: '2px',
                        display: 'flex',
                        alignItems: 'center'
                      }}
                      title="Delete"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Active Sub-agents (Orchestrator Graph) */}
          <div className="glass-panel" style={{ ...styles.toolsRegistryWrapper, marginBottom: '0px' }}>
            <h3 style={styles.toolsPanelTitle}>
              <Shield size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Active System Sub-agents (Orchestrator Graph)</span>
            </h3>
            
            <div style={styles.registeredToolsList}>
              {/* Research Agent */}
              <div style={styles.toolRegistryItem}>
                <div style={styles.toolRegistryHeader}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="pulse-dot" style={{ backgroundColor: '#10b981', boxShadow: '0 0 8px #10b981' }} />
                    <span style={styles.toolRegistryName}>ResearchAgent (Information Retrieval)</span>
                  </div>
                  <span style={{ ...styles.toolRegistryTag, backgroundColor: 'rgba(0, 240, 255, 0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(0, 240, 255, 0.2)' }}>ONLINE</span>
                </div>
                <p style={styles.toolRegistryDesc}>
                  Queries CoinGecko (coin prices) and RSS news feeds autonomously. Scans, filters, and sanitizes web pages by links. Used by the planner to fetch real-time external information.
                </p>
              </div>

              {/* Code Agent */}
              <div style={styles.toolRegistryItem}>
                <div style={styles.toolRegistryHeader}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="pulse-dot" style={{ backgroundColor: '#10b981', boxShadow: '0 0 8px #10b981' }} />
                    <span style={styles.toolRegistryName}>CodeAgent (Code Execution in Docker)</span>
                  </div>
                  <span style={{ ...styles.toolRegistryTag, backgroundColor: 'rgba(16, 185, 129, 0.1)', color: 'var(--success)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>SANDBOXED</span>
                </div>
                <p style={styles.toolRegistryDesc}>
                  Writes and tests Python scripts. Executes them in isolated Docker micro-containers with memory (128MB) and core (0.5 CPU) limits, no network access. Self-corrects code up to 3 times on exceptions or syntax errors.
                </p>
              </div>

              {/* Analyst Agent */}
              <div style={styles.toolRegistryItem}>
                <div style={styles.toolRegistryHeader}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="pulse-dot" style={{ backgroundColor: '#10b981', boxShadow: '0 0 8px #10b981' }} />
                    <span style={styles.toolRegistryName}>AnalystAgent (Data Analysis & Plotting)</span>
                  </div>
                  <span style={{ ...styles.toolRegistryTag, backgroundColor: 'rgba(0, 240, 255, 0.1)', color: 'var(--accent-cyan)', border: '1px solid rgba(0, 240, 255, 0.2)' }}>ONLINE</span>
                </div>
                <p style={styles.toolRegistryDesc}>
                  Works in tandem with CodeAgent. Reads data from uploaded CSV/Excel tables, performs mathematical analysis via pandas/numpy, and generates charts using matplotlib with a signature dark theme. Chart cards are returned in the chat.
                </p>
              </div>
            </div>
          </div>

          {/* Registered Tools */}
          <div style={styles.toolsRegistryWrapper} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <Settings size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Registered Utilities (Core Tools)</span>
            </h3>
            
            <div style={styles.registeredToolsList}>
              <div style={styles.toolRegistryItem}>
                <div style={styles.toolRegistryHeader}>
                  <span style={styles.toolRegistryName}>get_system_stats</span>
                  <span style={styles.toolRegistryTag}>system</span>
                </div>
                <p style={styles.toolRegistryDesc}>
                  Collects telemetry from host system. Reads CPU, RAM, and disk utilization without external dependencies.
                </p>
              </div>

              <div style={styles.toolRegistryItem}>
                <div style={styles.toolRegistryHeader}>
                  <span style={styles.toolRegistryName}>set_timer</span>
                  <span style={styles.toolRegistryTag}>scheduler</span>
                </div>
                <p style={styles.toolRegistryDesc}>
                  Sets a countdown timer. On completion, sends a push notification to the creator's Telegram and prints a system alert to the console.
                </p>
              </div>

              <div style={styles.toolRegistryItem}>
                <div style={styles.toolRegistryHeader}>
                  <span style={styles.toolRegistryName}>get_weather</span>
                  <span style={styles.toolRegistryTag}>utility</span>
                </div>
                <p style={styles.toolRegistryDesc}>
                  Requests current meteorological conditions in the specified city. Accompanied by Jarvis's signature weather report.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
