import { 
  Activity, 
  Box,
  Clock3,
  Cpu,
  Database, 
  Download,
  HardDrive,
  MemoryStick,
  Network,
  Server,
  Shield, 
  Settings,
  Thermometer,
  Upload,
  Zap,
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

const formatBytes = (bytes?: number | null, decimals = 1) => {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : decimals)} ${units[index]}`;
};

const formatUptime = (seconds?: number) => {
  if (!seconds) return '—';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days} д ${hours} ч ${minutes} мин`;
};

const formatPercent = (value?: number | null) => value === null || value === undefined ? '—' : `${value.toFixed(value % 1 ? 1 : 0)}%`;

function Meter({ value, dangerAt = 85 }: { value?: number | null; dangerAt?: number }) {
  const normalized = Math.max(0, Math.min(100, value || 0));
  const tone = value === null || value === undefined
    ? 'is-unavailable'
    : value >= dangerAt
      ? 'is-danger'
      : value >= 65
        ? 'is-warning'
        : 'is-normal';
  return <span className={`server-meter ${tone}`}><i style={{ width: `${normalized}%` }} /></span>;
}

export function ToolsTab({
  systemStats,
  uploads,
  language,
  setLanguage,
  t
}: ToolsTabProps) {
  const host = systemStats?.host;
  const cpu = host?.cpu;
  const memory = host?.memory;
  const disks = host?.disks || [];
  const rootDisk = disks.find(disk => disk.mountpoint === '/') || disks[0];
  const gpus = host?.gpus || [];
  const containers = host?.containers || [];
  const network = host?.network;
  const isHostTelemetry = systemStats?.scope === 'physical_host';
  const isHealthy = systemStats?.status === 'nominal';
  const updatedAt = systemStats?.collected_at
    ? new Date(systemStats.collected_at).toLocaleTimeString(language === 'ru' ? 'ru-RU' : 'en-US')
    : null;
  const labels = language === 'ru' ? {
    title: 'СЕРВЕР И МОНИТОРИНГ',
    subtitle: 'Физический хост, GPU, хранилища, сеть и Docker-сервисы в реальном времени',
    server: 'Физический сервер', healthy: 'ВСЕ СИСТЕМЫ В НОРМЕ', partial: 'НЕПОЛНЫЕ ДАННЫЕ', stale: 'ДАННЫЕ УСТАРЕЛИ', loading: 'ЗАГРУЗКА',
    updated: 'Обновлено', uptime: 'Аптайм', processes: 'процессов', cpu: 'Процессор', ram: 'Оперативная память', rootDisk: 'Системный диск',
    used: 'занято', available: 'свободно', cores: 'логических ядер', load: 'Load average', storage: 'Хранилища', graphics: 'Графические процессоры',
    network: 'Сеть', services: 'Docker-сервисы', receive: 'Приём', transmit: 'Передача', total: 'Всего', driver: 'Драйвер',
    temperature: 'Температура', power: 'Питание', fan: 'Вентилятор', vram: 'VRAM', service: 'Сервис', state: 'Состояние', resources: 'Ресурсы', io: 'I/O',
    runtimeFallback: 'Сейчас доступны только метрики backend-контейнера. Данные физического хоста не следует интерпретировать как состояние всего сервера.',
    noGpu: 'GPU не обнаружены', noContainers: 'Данные Docker пока отсутствуют', noData: 'Ожидание первого снимка телеметрии…',
  } : {
    title: 'SERVER AND MONITORING',
    subtitle: 'Live physical host, GPU, storage, network and Docker service telemetry',
    server: 'Physical server', healthy: 'ALL SYSTEMS NOMINAL', partial: 'PARTIAL DATA', stale: 'STALE DATA', loading: 'LOADING',
    updated: 'Updated', uptime: 'Uptime', processes: 'processes', cpu: 'Processor', ram: 'Memory', rootDisk: 'System disk',
    used: 'used', available: 'available', cores: 'logical cores', load: 'Load average', storage: 'Storage', graphics: 'Graphics processors',
    network: 'Network', services: 'Docker services', receive: 'Receive', transmit: 'Transmit', total: 'Total', driver: 'Driver',
    temperature: 'Temperature', power: 'Power', fan: 'Fan', vram: 'VRAM', service: 'Service', state: 'State', resources: 'Resources', io: 'I/O',
    runtimeFallback: 'Only backend-container metrics are available. They must not be interpreted as the state of the physical server.',
    noGpu: 'No GPUs detected', noContainers: 'Docker data is not available yet', noData: 'Waiting for the first telemetry snapshot…',
  };

  return (
    <div style={styles.tabWrapper} className="tools-monitoring-tab">
      <div style={styles.tabHeader}>
        <div>
          <h2 style={styles.tabTitle}>{labels.title}</h2>
          <p style={styles.tabSubtitle}>{labels.subtitle}</p>
        </div>
      </div>

      <section className="server-monitor glass-panel">
        <header className="server-monitor-header">
          <div className="server-identity">
            <span className="server-icon"><Server size={22} /></span>
            <div>
              <div className="server-title-line">
                <h3>{host?.hostname || labels.server}</h3>
                {network?.primary_ip && <code>{network.primary_ip}</code>}
              </div>
              <p>{host ? `${host.os || 'Unknown OS'} · ${host.kernel || 'Unknown kernel'} · ${host.architecture || '—'}` : labels.noData}</p>
            </div>
          </div>
          <div className="server-freshness">
            <span className={`server-health-badge ${isHealthy ? 'is-healthy' : systemStats?.status === 'stale' ? 'is-stale' : 'is-partial'}`}>
              <i />
              {!systemStats ? labels.loading : isHealthy ? labels.healthy : systemStats.status === 'stale' ? labels.stale : labels.partial}
            </span>
            {updatedAt && <small>{labels.updated} {updatedAt} · {Math.round(systemStats?.age_seconds || 0)} c назад</small>}
          </div>
        </header>

        {systemStats && !isHostTelemetry && (
          <div className="server-warning"><Activity size={16} /><span>{labels.runtimeFallback} {systemStats.host_error || systemStats.error || ''}</span></div>
        )}

        {systemStats ? (
          <>
            <div className="server-overview-grid">
              <article className="server-primary-metric">
                <div className="server-metric-heading"><Cpu size={17} /><span>{labels.cpu}</span><strong>{formatPercent(cpu?.usage_percent ?? systemStats.cpu_load_percent)}</strong></div>
                <Meter value={cpu?.usage_percent ?? systemStats.cpu_load_percent} dangerAt={85} />
                <p title={cpu?.model}>{cpu?.model || 'CPU'} · {cpu?.logical_cores || '—'} {labels.cores}</p>
                <small>{labels.load}: {[cpu?.load_1m, cpu?.load_5m, cpu?.load_15m].map(value => value ?? '—').join(' / ')}</small>
              </article>

              <article className="server-primary-metric">
                <div className="server-metric-heading"><MemoryStick size={17} /><span>{labels.ram}</span><strong>{formatPercent(memory?.usage_percent ?? systemStats.ram_used_percent)}</strong></div>
                <Meter value={memory?.usage_percent ?? systemStats.ram_used_percent} />
                <p>{formatBytes(memory?.used_bytes)} {labels.used} · {formatBytes(memory?.available_bytes)} {labels.available}</p>
                <small>{labels.total}: {formatBytes(memory?.total_bytes || (systemStats.ram_total_gb ? systemStats.ram_total_gb * 1024 ** 3 : undefined))}</small>
              </article>

              <article className="server-primary-metric">
                <div className="server-metric-heading"><HardDrive size={17} /><span>{labels.rootDisk}</span><strong>{formatPercent(rootDisk?.usage_percent ?? systemStats.disk_used_percent)}</strong></div>
                <Meter value={rootDisk?.usage_percent ?? systemStats.disk_used_percent} dangerAt={90} />
                <p>{formatBytes(rootDisk?.used_bytes || (systemStats.disk_used_gb ? systemStats.disk_used_gb * 1024 ** 3 : undefined))} {labels.used} · {formatBytes(rootDisk?.available_bytes)} {labels.available}</p>
                <small>{rootDisk?.device || '/'} · {rootDisk?.filesystem || 'filesystem'}</small>
              </article>

              <article className="server-primary-metric server-uptime-metric">
                <div className="server-metric-heading"><Clock3 size={17} /><span>{labels.uptime}</span></div>
                <strong>{formatUptime(host?.uptime_seconds)}</strong>
                <p>{host?.process_count ?? '—'} {labels.processes}</p>
                <small>{host?.boot_time ? new Date(host.boot_time).toLocaleString(language === 'ru' ? 'ru-RU' : 'en-US') : '—'}</small>
              </article>
            </div>

            <div className="server-detail-grid">
              <section className="server-detail-section">
                <h4><HardDrive size={16} />{labels.storage}<span>{disks.length}</span></h4>
                <div className="storage-list">
                  {disks.length ? disks.map(disk => (
                    <div className="storage-row" key={`${disk.device}-${disk.mountpoint}`}>
                      <div><strong>{disk.mountpoint}</strong><small>{disk.device} · {disk.filesystem}</small></div>
                      <div className="storage-capacity"><strong>{formatBytes(disk.used_bytes)} / {formatBytes(disk.total_bytes)}</strong><Meter value={disk.usage_percent} dangerAt={90} /></div>
                      <span>{formatPercent(disk.usage_percent)}</span>
                    </div>
                  )) : <p className="server-empty">{labels.noData}</p>}
                </div>
              </section>

              <section className="server-detail-section">
                <h4><Network size={16} />{labels.network}<span>{network?.interfaces?.length || 0}</span></h4>
                <div className="network-summary">
                  <div><Download size={18} /><span>{labels.receive}</span><strong>{formatBytes(network?.rx_bytes_per_second)}/с</strong><small>{labels.total}: {formatBytes(network?.rx_bytes)}</small></div>
                  <div><Upload size={18} /><span>{labels.transmit}</span><strong>{formatBytes(network?.tx_bytes_per_second)}/с</strong><small>{labels.total}: {formatBytes(network?.tx_bytes)}</small></div>
                </div>
                <div className="interface-list">{network?.interfaces?.map(item => <code key={item.name}>{item.name}: ↓{formatBytes(item.rx_bytes_per_second)}/с ↑{formatBytes(item.tx_bytes_per_second)}/с</code>)}</div>
              </section>
            </div>

            <section className="server-wide-section">
              <h4><Zap size={16} />{labels.graphics}<span>{gpus.length}</span></h4>
              {gpus.length ? <div className="gpu-grid">{gpus.map(gpu => (
                <article className="gpu-row" key={gpu.uuid || gpu.index}>
                  <div className="gpu-name"><span>GPU {gpu.index}</span><strong>{gpu.name}</strong><small>{labels.driver} {gpu.driver_version}</small></div>
                  <div className="gpu-stat"><span>GPU</span><strong>{formatPercent(gpu.utilization_percent)}</strong><Meter value={gpu.utilization_percent} dangerAt={95} /></div>
                  <div className="gpu-stat"><span>{labels.vram}</span><strong>{formatBytes(gpu.memory_used_bytes)} / {formatBytes(gpu.memory_total_bytes)}</strong><Meter value={gpu.memory_usage_percent} dangerAt={92} /></div>
                  <div className="gpu-compact-stat"><Thermometer size={15} /><span>{labels.temperature}</span><strong>{gpu.temperature_celsius ?? '—'}°C</strong></div>
                  <div className="gpu-compact-stat"><Zap size={15} /><span>{labels.power}</span><strong>{gpu.power_draw_watts?.toFixed(0) ?? '—'} / {gpu.power_limit_watts?.toFixed(0) ?? '—'} W</strong></div>
                  <div className="gpu-compact-stat"><Activity size={15} /><span>{labels.fan}</span><strong>{formatPercent(gpu.fan_percent)}</strong></div>
                </article>
              ))}</div> : <p className="server-empty">{labels.noGpu}</p>}
            </section>

            <section className="server-wide-section docker-section">
              <h4><Box size={16} />{labels.services}<span>{containers.length}</span></h4>
              {containers.length ? <div className="docker-table">
                <div className="docker-table-head"><span>{labels.service}</span><span>{labels.state}</span><span>{labels.resources}</span><span>{labels.io}</span></div>
                {containers.map(container => {
                  const serviceHealthy = container.state === 'running' && container.health !== 'unhealthy';
                  return <div className="docker-row" key={container.name}>
                    <div><i className={serviceHealthy ? 'is-up' : 'is-down'} /><strong>{container.name}</strong><small title={container.image}>{container.image}</small></div>
                    <div><span className={`container-health ${serviceHealthy ? 'is-up' : 'is-down'}`}>{container.health === 'none' ? container.state : container.health}</span><small>{container.status}</small></div>
                    <div><strong>CPU {formatPercent(container.cpu_percent)} · RAM {formatPercent(container.memory_percent)}</strong><small>{container.memory_usage || '—'} · PID {container.pids ?? '—'}</small></div>
                    <div><strong>NET {container.network_io || '—'}</strong><small>BLOCK {container.block_io || '—'}</small></div>
                  </div>;
                })}
              </div> : <p className="server-empty">{labels.noContainers}</p>}
            </section>
          </>
        ) : <div className="server-loading"><span className="pulse-dot" />{labels.noData}</div>}
      </section>

      <div style={styles.toolsLayout} className="tools-layout">
        {/* Left Column: Datasets */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', height: '100%', overflowY: 'auto', paddingRight: '4px' }}>

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
