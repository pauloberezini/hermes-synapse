import { 
  Activity, 
  Database, 
  Shield, 
  Settings 
} from 'lucide-react';
import { styles } from '../styles';
import type { Language } from '../i18n';
import type { SystemStats } from '../types';

interface ToolsTabProps {
  systemStats: SystemStats | null;
  uploads: { name: string; size_bytes: number }[];
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
}

export function ToolsTab({
  systemStats,
  uploads,
  language,
  setLanguage,
  t
}: ToolsTabProps) {
  const telemetryAvailable = systemStats?.available !== false && systemStats?.status !== 'unavailable';
  const telemetryStatusLabel = !systemStats
    ? 'LOADING'
    : systemStats.status === 'unavailable'
      ? 'UNAVAILABLE'
      : systemStats.status === 'partial'
        ? 'PARTIAL'
        : systemStats.scope === 'backend_runtime'
          ? 'RUNTIME'
          : systemStats.status.toUpperCase();
  const telemetryStatusColor = !systemStats
    ? 'var(--text-muted)'
    : telemetryAvailable && systemStats.status !== 'partial'
      ? 'var(--success)'
      : 'var(--warning)';

  const renderMetric = (
    label: string,
    value: number | null | undefined,
    help?: string,
    dangerAt = 85,
  ) => (
    <div style={styles.metricItem}>
      <div style={styles.metricLabelRow}>
        <span>{label}</span>
        <span style={{ color: value === null || value === undefined ? 'var(--warning)' : 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
          {value === null || value === undefined ? 'unavailable' : `${value}%`}
        </span>
      </div>
      <div style={styles.progressBarBg}>
        <div
          style={{
            ...styles.progressBarFill,
            width: `${Math.max(0, Math.min(100, value || 0))}%`,
            backgroundColor: value === null || value === undefined ? 'var(--warning)' : (value > dangerAt ? 'var(--danger)' : (value > 50 ? 'var(--warning)' : 'var(--accent-cyan)')),
            boxShadow: value === null || value === undefined ? 'none' : '0 0 10px rgba(0, 240, 255, 0.4)',
          }}
        />
      </div>
      {help && <div style={styles.metricHelpText}>{help}</div>}
    </div>
  );

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>TOOLS AND MONITORING</h2>
          <p style={styles.tabSubtitle}>Runtime telemetry from the backend process plus background tools</p>
        </div>
      </div>

      <div style={styles.toolsLayout} className="tools-layout">
        {/* Left Column: Telemetry & Datasets */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', height: '100%', overflowY: 'auto', paddingRight: '4px' }}>
          
          {/* System Metrics Telemetry */}
          <div style={{ ...styles.toolsMetricsWrapper, height: 'auto', flexShrink: 0 }} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <Activity size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Backend Runtime Telemetry</span>
            </h3>
            
            {systemStats ? (
              <div style={styles.metricsList}>
                {renderMetric('CPU Load', systemStats.cpu_load_percent, undefined, 80)}
                {renderMetric('RAM Usage', systemStats.ram_used_percent, systemStats.ram_total_gb ? `Total capacity: ${systemStats.ram_total_gb} GB` : 'RAM capacity unavailable')}
                {renderMetric('Disk Storage', systemStats.disk_used_percent, systemStats.disk_total_gb ? `Used ${systemStats.disk_used_gb} GB of ${systemStats.disk_total_gb} GB` : 'Disk capacity unavailable')}

                {(systemStats.status !== 'nominal' || systemStats.error) && (
                  <div style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(245,158,11,0.24)',
                    background: 'rgba(245,158,11,0.07)',
                    color: 'var(--warning)',
                    fontSize: '0.82rem',
                    lineHeight: 1.4,
                  }}>
                    {systemStats.error || `Unavailable: ${(systemStats.unavailable || []).join(', ')}`}
                  </div>
                )}

                {(systemStats.scope === 'backend_runtime' || systemStats.warning) && (
                  <div style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(115, 217, 255, 0.2)',
                    background: 'rgba(115, 217, 255, 0.06)',
                    color: 'var(--text-muted)',
                    fontSize: '0.78rem',
                    lineHeight: 1.45,
                  }}>
                    {systemStats.warning || 'Metrics describe the backend runtime, not necessarily the whole physical host.'}
                  </div>
                )}

                {systemStats.source && (
                  <div style={styles.metricHelpText}>
                    Source: {systemStats.source}
                  </div>
                )}

                <div style={styles.telemetryStatusRow}>
                  <span style={{ color: 'var(--text-muted)' }}>Telemetry Status:</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className={`pulse-dot ${telemetryAvailable ? '' : 'danger'}`} />
                    <span style={{ color: telemetryStatusColor, fontWeight: 600, fontSize: '0.85rem' }}>
                      {telemetryStatusLabel}
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
          <div style={styles.toolsRegistryWrapper} className="glass-panel">
            <h3 style={styles.toolsPanelTitle}>
              <Settings size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>{t('language')}</span>
            </h3>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {([
                ['ru', 'Русский'],
                ['en', 'English'],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setLanguage(value)}
                  className="btn-primary"
                  style={{
                    borderColor: language === value ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.14)',
                    background: language === value ? 'rgba(0,240,255,0.12)' : 'rgba(255,255,255,0.03)',
                    color: language === value ? 'var(--accent-cyan)' : 'var(--text-muted)',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <p style={{ ...styles.formHelp, marginTop: 12 }}>{t('languageHelp')}</p>
            <div style={{
              marginTop: 14,
              padding: 12,
              borderRadius: 8,
              border: '1px solid rgba(16,185,129,0.22)',
              background: 'rgba(16,185,129,0.06)',
              color: 'var(--success)',
              fontSize: '0.86rem',
              fontWeight: 600,
            }}>
              {t('saveStatus')}
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
                  Requests current meteorological conditions in the specified city. Accompanied by Vexa's signature weather report.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
