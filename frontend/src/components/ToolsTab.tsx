import { 
  Activity, 
  Database, 
  Shield, 
  Settings 
} from 'lucide-react';
import { styles } from '../styles';

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
}

export function ToolsTab({
  systemStats,
  uploads
}: ToolsTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>TOOLS AND MONITORING</h2>
          <p style={styles.tabSubtitle}>Monitoring of system metrics and background processes</p>
        </div>
      </div>

      <div style={styles.toolsLayout} className="tools-layout">
        {/* Left Column: Telemetry & Datasets */}
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

                {/* Memory RAM Loader */}
                <div style={styles.metricItem}>
                  <div style={styles.metricLabelRow}>
                    <span>RAM Utilization</span>
                    <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
                      {systemStats.ram_used_percent}%
                    </span>
                  </div>
                  <div style={styles.progressBarBg}>
                    <div 
                      style={{
                        ...styles.progressBarFill,
                        width: `${systemStats.ram_used_percent}%`,
                        backgroundColor: systemStats.ram_used_percent > 85 ? 'var(--danger)' : (systemStats.ram_used_percent > 60 ? 'var(--warning)' : 'var(--accent-cyan)'),
                        boxShadow: systemStats.ram_used_percent > 85 ? '0 0 10px var(--danger)' : '0 0 10px rgba(0, 240, 255, 0.4)'
                      }}
                    />
                  </div>
                  <div style={styles.metricHelpText}>
                    Used {(systemStats.ram_total_gb * systemStats.ram_used_percent / 100).toFixed(1)} GB of {systemStats.ram_total_gb} GB
                  </div>
                </div>

                {/* Disk Loader */}
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

        {/* Right Column: Active Sub-agents & Core Tools */}
        <div style={styles.toolsContentRight}>
          
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
