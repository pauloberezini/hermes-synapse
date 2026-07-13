import { BarChart3, Clock, CheckCircle2, Coins, Database, Cpu } from 'lucide-react';
import { styles } from '../styles';

interface MetricsSummary {
  total_calls: number;
  avg_latency_ms: number;
  success_rate: number;
  total_tokens: number;
  total_cost_usd: number;
}

interface AgentMetric {
  agent_id: string;
  total_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  total_tokens: number;
  total_cost_usd: number;
}

interface ModelMetric {
  model: string;
  total_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  total_tokens: number;
  total_cost_usd: number;
}

interface MetricsTabProps {
  metrics: {
    summary: MetricsSummary;
    by_agent: AgentMetric[];
    by_model: ModelMetric[];
  } | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export function MetricsTab({
  metrics,
  isLoading,
  onRefresh
}: MetricsTabProps) {
  if (isLoading && !metrics) {
    return (
      <div style={styles.tabWrapper}>
        <div style={styles.tabHeader}>
          <div>
            <h2 className="glow-text-cyan" style={styles.tabTitle}>LEADERBOARD & METRICS</h2>
            <p style={styles.tabSubtitle}>Loading system performance data...</p>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '300px', color: 'var(--accent-cyan)' }}>
          <div className="pulse" style={{ fontSize: '18px', fontWeight: 'bold' }}>Retrieving Telemetry, Sir...</div>
        </div>
      </div>
    );
  }

  const data = metrics || {
    summary: { total_calls: 0, avg_latency_ms: 0, success_rate: 100, total_tokens: 0, total_cost_usd: 0 },
    by_agent: [],
    by_model: []
  };

  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>SYSTEM METRICS & LEADERBOARD</h2>
          <p style={styles.tabSubtitle}>Performance analysis, model costs, and agent success attribution</p>
        </div>
        <button 
          onClick={onRefresh}
          className="button-glow-cyan"
          style={{
            background: 'rgba(0, 240, 255, 0.1)',
            border: '1px solid var(--accent-cyan)',
            color: '#fff',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            transition: 'all 0.3s ease'
          }}
        >
          Refresh Stats
        </button>
      </div>

      {/* Summary Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '20px',
        marginBottom: '30px'
      }}>
        {/* Card 1: Total Calls */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ color: '#8a99ad', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '1px' }}>Total Runs</span>
            <BarChart3 size={20} color="var(--accent-cyan)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 'bold', color: '#fff', textShadow: '0 0 10px rgba(0, 240, 255, 0.3)' }}>
            {data.summary.total_calls}
          </span>
          <span style={{ fontSize: '11px', color: '#5f6e80', marginTop: '5px' }}>Total triggered agent completions</span>
        </div>

        {/* Card 2: Success Rate */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ color: '#8a99ad', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '1px' }}>Success Rate</span>
            <CheckCircle2 size={20} color={data.summary.success_rate >= 90 ? '#10b981' : '#f59e0b'} />
          </div>
          <span style={{ 
            fontSize: '28px', 
            fontWeight: 'bold', 
            color: data.summary.success_rate >= 90 ? '#10b981' : '#f59e0b',
            textShadow: `0 0 10px ${data.summary.success_rate >= 90 ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`
          }}>
            {data.summary.success_rate.toFixed(1)}%
          </span>
          <span style={{ fontSize: '11px', color: '#5f6e80', marginTop: '5px' }}>Errors: {((100 - data.summary.success_rate) * data.summary.total_calls / 100).toFixed(0)} runs</span>
        </div>

        {/* Card 3: Avg Latency */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ color: '#8a99ad', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '1px' }}>Avg Latency</span>
            <Clock size={20} color="var(--accent-purple)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 'bold', color: '#fff', textShadow: '0 0 10px rgba(139, 92, 246, 0.3)' }}>
            {data.summary.avg_latency_ms.toLocaleString()} ms
          </span>
          <span style={{ fontSize: '11px', color: '#5f6e80', marginTop: '5px' }}>Average response latency</span>
        </div>

        {/* Card 4: Total Cost */}
        <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ color: '#8a99ad', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '1px' }}>Accrued Cost</span>
            <Coins size={20} color="#f59e0b" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 'bold', color: '#f59e0b', textShadow: '0 0 10px rgba(245, 158, 11, 0.3)' }}>
            ${data.summary.total_cost_usd.toFixed(4)}
          </span>
          <span style={{ fontSize: '11px', color: '#5f6e80', marginTop: '5px' }}>Total estimated API consumption</span>
        </div>
      </div>

      {/* Main Tables Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '30px'
      }} className="metrics-grid-layout">
        {/* Agent Leaderboard */}
        <div className="glass-panel" style={{ padding: '20px', overflowX: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', borderBottom: '1px solid rgba(0, 240, 255, 0.1)', paddingBottom: '10px' }}>
            <Cpu size={18} color="var(--accent-cyan)" />
            <h3 style={{ margin: 0, fontSize: '16px', color: '#fff', fontWeight: 'bold', letterSpacing: '0.5px' }}>AGENT EFFICIENCY LEADERBOARD</h3>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', color: '#cbd5e1', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', textAlign: 'left' }}>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Agent ID</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Runs</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Success Rate</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Avg Latency</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              {data.by_agent.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '30px', color: '#5f6e80' }}>No agent logs indexed yet.</td>
                </tr>
              ) : (
                data.by_agent.map((agent) => (
                  <tr key={agent.agent_id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)', transition: 'background-color 0.2s' }}>
                    <td style={{ padding: '12px 5px', fontWeight: '600', color: '#fff' }}>{agent.agent_id}</td>
                    <td style={{ padding: '12px 5px' }}>{agent.total_calls}</td>
                    <td style={{ padding: '12px 5px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{
                          color: agent.success_rate >= 90 ? '#10b981' : agent.success_rate >= 75 ? '#f59e0b' : '#ef4444',
                          fontWeight: 'bold',
                          minWidth: '45px'
                        }}>
                          {agent.success_rate.toFixed(0)}%
                        </span>
                        <div style={{ width: '60px', height: '6px', backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{
                            width: `${agent.success_rate}%`,
                            height: '100%',
                            backgroundColor: agent.success_rate >= 90 ? '#10b981' : agent.success_rate >= 75 ? '#f59e0b' : '#ef4444',
                            borderRadius: '3px'
                          }} />
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '12px 5px' }}>{agent.avg_latency_ms.toFixed(0)} ms</td>
                    <td style={{ padding: '12px 5px', color: '#f59e0b', fontWeight: '500' }}>${agent.total_cost_usd.toFixed(5)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Model Resource Consumption */}
        <div className="glass-panel" style={{ padding: '20px', overflowX: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', borderBottom: '1px solid rgba(0, 240, 255, 0.1)', paddingBottom: '10px' }}>
            <Database size={18} color="var(--accent-purple)" />
            <h3 style={{ margin: 0, fontSize: '16px', color: '#fff', fontWeight: 'bold', letterSpacing: '0.5px' }}>MODEL PERFORMANCE & TOKENS</h3>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', color: '#cbd5e1', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', textAlign: 'left' }}>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Model Name</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Runs</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Success Rate</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Tokens</th>
                <th style={{ padding: '10px 5px', color: '#8a99ad', fontWeight: '500' }}>Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              {data.by_model.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '30px', color: '#5f6e80' }}>No model logs indexed yet.</td>
                </tr>
              ) : (
                data.by_model.map((model) => {
                  const displayName = model.model.includes('/') ? model.model.split('/')[1] : model.model;
                  return (
                    <tr key={model.model} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)', transition: 'background-color 0.2s' }}>
                      <td style={{ padding: '12px 5px', fontWeight: '600', color: '#fff' }} title={model.model}>
                        {displayName}
                      </td>
                      <td style={{ padding: '12px 5px' }}>{model.total_calls}</td>
                      <td style={{ padding: '12px 5px' }}>
                        <span style={{
                          color: model.success_rate >= 90 ? '#10b981' : model.success_rate >= 75 ? '#f59e0b' : '#ef4444',
                          fontWeight: 'bold'
                        }}>
                          {model.success_rate.toFixed(0)}%
                        </span>
                      </td>
                      <td style={{ padding: '12px 5px' }}>{model.total_tokens.toLocaleString()}</td>
                      <td style={{ padding: '12px 5px', color: '#f59e0b', fontWeight: '500' }}>${model.total_cost_usd.toFixed(5)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
