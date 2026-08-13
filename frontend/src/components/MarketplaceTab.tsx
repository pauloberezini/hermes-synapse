import React, { useState, useEffect, useCallback } from 'react';
import { Search, Package, Star, Download, Trash2, RefreshCw, Filter, ChevronDown, User, Code2, Globe, ShieldCheck, BarChart2, Database, Terminal, Brain, BookOpen, Rss, Clock, AlertCircle, CheckCircle2, Cpu, ChevronLeft, ChevronRight, ShoppingCart } from 'lucide-react';

// ─── Built-in skill catalogue (always visible, drawn from the system's own tools) ────────
const BUILTIN_SKILLS = [
  {
    id: 'web_search',
    name: 'web_search',
    display_name: 'Web Search',
    description: 'DuckDuckGo-powered search, real-time weather via OpenWeatherMap, and RSS news aggregation. No API key required for search.',
    author: 'hermes-core',
    version: '2.0.0',
    category: 'research',
    tags: ['search', 'web', 'weather', 'news'],
    tools: ['search_web', 'get_weather', 'get_rss_digest'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Globe,
    color: '#00f0ff',
  },
  {
    id: 'market_monitor',
    name: 'market_monitor',
    display_name: 'Market Monitor',
    description: 'Real-time stock quotes, crypto prices, and configurable price alerts. Supports Yahoo Finance, Alpaca, and CCXT-compatible brokers.',
    author: 'hermes-core',
    version: '2.0.0',
    category: 'finance',
    tags: ['trading', 'finance', 'alerts'],
    tools: ['get_market_prices', 'add_price_alert', 'cancel_price_alert'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: BarChart2,
    color: '#10b981',
  },
  {
    id: 'bcm',
    name: 'bcm',
    display_name: 'BCM Trading Engine',
    description: 'Institutional-grade FIX 4.4 execution via Pepperstone cTrader, autonomous trading cycles with compliance guardrails and risk engine.',
    author: 'hermes-core',
    version: '3.0.0',
    category: 'finance',
    tags: ['trading', 'forex', 'fix-protocol'],
    tools: ['bcm_run_autonomous_cycle', 'bcm_get_technical_indicators', 'bcm_get_market_experience'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Cpu,
    color: '#f43f5e',
  },
  {
    id: 'bybit',
    name: 'bybit',
    display_name: 'Bybit Options & Crypto',
    description: 'Bybit V5 REST API integration for USDC perpetuals, crypto options, portfolio Greeks, delta hedging, and margin safety checks.',
    author: 'hermes-core',
    version: '1.5.0',
    category: 'finance',
    tags: ['crypto', 'options', 'bybit'],
    tools: ['bybit_analyze_option_position', 'bybit_get_portfolio_greeks', 'bybit_get_positions'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Database,
    color: '#f59e0b',
  },
  {
    id: 'obsidian_rag',
    name: 'obsidian_rag',
    display_name: 'Obsidian Vault',
    description: 'Bidirectional sync with Obsidian via Local REST API. Index notes into vector memory, semantic search, and write-back capabilities.',
    author: 'hermes-core',
    version: '1.2.0',
    category: 'productivity',
    tags: ['notes', 'knowledge-base', 'rag'],
    tools: ['read_obsidian_note', 'search_obsidian_notes', 'create_obsidian_note'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: BookOpen,
    color: '#8b5cf6',
  },
  {
    id: 'timers_alarms',
    name: 'timers_alarms',
    display_name: 'Timers & Alarms',
    description: 'Full scheduler toolkit: one-shot timers, daily alarms, recurring reminders, cron jobs, and pause/resume controls via APScheduler.',
    author: 'hermes-core',
    version: '2.1.0',
    category: 'productivity',
    tags: ['scheduling', 'reminders', 'automation'],
    tools: ['set_timer', 'set_alarm', 'set_recurring_reminder', 'cancel_timer_or_alarm'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Clock,
    color: '#3b82f6',
  },
  {
    id: 'shell_execution',
    name: 'shell_execution',
    display_name: 'Terminal Shell',
    description: 'Execute whitelisted shell commands on the Hermes server, retrieve system stats (CPU, memory, disk), and run sandboxed scripts.',
    author: 'hermes-core',
    version: '1.0.0',
    category: 'developer',
    tags: ['terminal', 'system', 'devops'],
    tools: ['execute_command', 'get_system_stats'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Terminal,
    color: '#6b7280',
  },
  {
    id: 'python_sandbox',
    name: 'python_sandbox',
    display_name: 'Python Sandbox',
    description: 'Isolated Docker-based Python REPL for calculations, data analysis, chart generation, and self-correcting code execution via CodeAgent.',
    author: 'hermes-core',
    version: '1.4.0',
    category: 'developer',
    tags: ['python', 'code', 'analysis'],
    tools: ['execute_code', 'run_research_agent', 'run_analyst_agent'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Code2,
    color: '#14b8a6',
  },
  {
    id: 'todoist_sync',
    name: 'todoist_sync',
    display_name: 'Todoist Tasks',
    description: 'Sync tasks, projects, and labels with Todoist REST API v2. List, create, complete, and delete tasks directly from the agent.',
    author: 'hermes-core',
    version: '1.0.0',
    category: 'productivity',
    tags: ['tasks', 'todoist', 'gtd'],
    tools: ['get_todoist_tasks', 'create_todoist_task', 'complete_todoist_task'],
    price_type: 'free',
    price_usd: 0,
    is_installed: false,
    icon: CheckCircle2,
    color: '#ef4444',
  },
  {
    id: 'google_calendar',
    name: 'google_calendar',
    display_name: 'Google Calendar',
    description: 'OAuth2 Google Calendar integration. List upcoming events, check free/busy slots, and create or delete calendar events.',
    author: 'hermes-core',
    version: '1.0.0',
    category: 'productivity',
    tags: ['calendar', 'google', 'scheduling'],
    tools: ['get_calendar_events', 'create_calendar_event'],
    price_type: 'free',
    price_usd: 0,
    is_installed: false,
    icon: Star,
    color: '#f59e0b',
  },
  {
    id: 'read_rss_node_feed',
    name: 'read_rss_node_feed',
    display_name: 'RSS News Ray',
    description: 'Autonomous RSS feed aggregation nodes. Fetch, parse, and deliver curated news from any RSS/Atom source into agent context.',
    author: 'hermes-core',
    version: '1.1.0',
    category: 'research',
    tags: ['rss', 'news', 'feeds'],
    tools: ['read_rss_node_feed', 'get_rss_digest'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Rss,
    color: '#ea580c',
  },
  {
    id: 'github_integration',
    name: 'github_integration',
    display_name: 'GitHub Integration',
    description: 'Read GitHub issues, pull requests, and repository READMEs. Community skill authored using the hermes_sdk decorator API.',
    author: 'community',
    version: '1.0.0',
    category: 'developer',
    tags: ['github', 'devtools', 'community'],
    tools: ['list_issues', 'get_readme'],
    price_type: 'free',
    price_usd: 0,
    is_installed: false,
    icon: Code2,
    color: '#a78bfa',
  },
  {
    id: 'skill_distiller',
    name: 'skill_distiller',
    display_name: 'Skill Distiller',
    description: 'Automatically distills high-quality agent decision logs into reusable skills stored in the vector memory using LLM heuristics.',
    author: 'hermes-core',
    version: '1.0.0',
    category: 'ai',
    tags: ['ai', 'learning', 'distillation'],
    tools: ['distill_skill_from_log', 'search_distilled_skills'],
    price_type: 'free',
    price_usd: 0,
    is_installed: true,
    icon: Brain,
    color: '#c084fc',
  },
];

// ─── Category config ────────────────────────────────────────────────────────
const CATEGORIES = [
  { id: 'all', label: 'All Skills', icon: Package },
  { id: 'research', label: 'Research', icon: Globe },
  { id: 'finance', label: 'Finance', icon: BarChart2 },
  { id: 'productivity', label: 'Productivity', icon: CheckCircle2 },
  { id: 'developer', label: 'Developer', icon: Code2 },
  { id: 'ai', label: 'AI / ML', icon: Brain },
];

const SORT_OPTIONS = [
  { value: 'name', label: 'Name A→Z' },
  { value: 'installed', label: 'Installed First' },
  { value: 'category', label: 'Category' },
];

// ─── Individual Skill Card ───────────────────────────────────────────────────
function SkillCard({ skill, onInstall, onUninstall }: { skill: any; onInstall: (id: string) => void; onUninstall: (id: string) => void }) {
  const [actionLoading, setActionLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const IconComponent = skill.icon || Package;

  const handleInstall = async () => {
    setActionLoading(true);
    if (skill.price_type !== 'free') {
      try {
        const res = await fetch(`http://localhost:8000/api/marketplace/skills/${skill.id}/checkout?redirect_url=${encodeURIComponent(window.location.href)}`, {
          method: 'POST'
        });
        if (res.ok) {
          const data = await res.json();
          if (data.checkout_url) {
            window.location.href = data.checkout_url;
            return; // don't clear loading state if redirecting
          }
        }
      } catch (err) {
        console.error("Checkout error:", err);
      }
    } else {
      await onInstall(skill.id);
    }
    setActionLoading(false);
  };

  const handleUninstall = async () => {
    setActionLoading(true);
    await onUninstall(skill.id);
    setActionLoading(false);
  };

  return (
    <div
      className="marketplace-skill-card"
      style={{
        background: 'var(--bg-card, rgba(16,22,42,0.65))',
        border: skill.is_installed
          ? `1px solid rgba(16, 185, 129, 0.3)`
          : '1px solid rgba(0,240,255,0.08)',
        borderRadius: '14px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        backdropFilter: 'blur(12px)',
        transition: 'border-color 0.25s, box-shadow 0.25s, transform 0.2s',
        position: 'relative',
        overflow: 'hidden',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = skill.is_installed
          ? 'rgba(16,185,129,0.6)'
          : 'rgba(0,240,255,0.25)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px rgba(0,0,0,0.4), 0 0 20px ${skill.color}20`;
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = skill.is_installed
          ? 'rgba(16,185,129,0.3)'
          : 'rgba(0,240,255,0.08)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = 'none';
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)';
      }}
    >
      {/* Subtle color accent glow top */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: '2px',
        background: `linear-gradient(90deg, transparent, ${skill.color}, transparent)`,
        opacity: skill.is_installed ? 0.9 : 0.4,
      }} />

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <div style={{
          width: 44, height: 44, borderRadius: '10px', flexShrink: 0,
          background: `${skill.color}18`,
          border: `1px solid ${skill.color}30`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <IconComponent size={20} color={skill.color} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <h3 style={{
              margin: 0, fontSize: '0.95rem', fontWeight: 600,
              color: 'var(--text-primary, #f1f5f9)', lineHeight: 1.3,
            }}>
              {skill.display_name}
            </h3>
            {skill.is_installed && (
              <span style={{
                fontSize: '0.68rem', fontWeight: 600, padding: '2px 7px',
                borderRadius: '20px', letterSpacing: '0.05em',
                background: 'rgba(16,185,129,0.15)',
                color: '#10b981',
                border: '1px solid rgba(16,185,129,0.3)',
              }}>
                INSTALLED
              </span>
            )}
            {skill.author === 'community' && (
              <span style={{
                fontSize: '0.68rem', fontWeight: 600, padding: '2px 7px',
                borderRadius: '20px', letterSpacing: '0.05em',
                background: 'rgba(139,92,246,0.15)',
                color: '#a78bfa',
                border: '1px solid rgba(139,92,246,0.3)',
              }}>
                COMMUNITY
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
            <User size={11} color="var(--text-dim, #64748b)" />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim, #64748b)' }}>{skill.author}</span>
            <span style={{ color: 'var(--text-dim, #64748b)', fontSize: '0.75rem' }}>·</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim, #64748b)' }}>v{skill.version}</span>
          </div>
        </div>

        <span style={{
          fontSize: '0.8rem', fontWeight: 700,
          color: skill.price_type === 'free' ? '#10b981' : '#f59e0b',
          whiteSpace: 'nowrap',
        }}>
          {skill.price_type === 'free' ? 'Free' : `$${skill.price_usd}`}
        </span>
      </div>

      {/* Description */}
      <p style={{
        margin: 0, fontSize: '0.84rem',
        color: 'var(--text-muted, #94a3b8)',
        lineHeight: 1.55,
        display: '-webkit-box',
        WebkitLineClamp: expanded ? 'unset' : 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}>
        {skill.description}
      </p>
      {skill.description && skill.description.length > 120 && (
        <button
          onClick={() => setExpanded(x => !x)}
          style={{
            alignSelf: 'flex-start', background: 'none', border: 'none', cursor: 'pointer',
            fontSize: '0.75rem', color: 'var(--accent-cyan, #00f0ff)', padding: 0,
            marginTop: '-10px',
          }}
        >
          {expanded ? 'Show less ↑' : 'Read more ↓'}
        </button>
      )}

      {/* Tools chips */}
      {skill.tools && skill.tools.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {skill.tools.slice(0, 4).map((t: string) => (
            <span key={t} style={{
              fontSize: '0.7rem', padding: '3px 8px',
              borderRadius: '6px', fontFamily: 'var(--font-mono, monospace)',
              background: 'rgba(0,240,255,0.07)', color: 'var(--accent-cyan, #00f0ff)',
              border: '1px solid rgba(0,240,255,0.12)',
            }}>
              {t}
            </span>
          ))}
          {skill.tools.length > 4 && (
            <span style={{
              fontSize: '0.7rem', padding: '3px 8px', borderRadius: '6px',
              background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim, #64748b)',
              border: '1px solid rgba(255,255,255,0.08)',
            }}>
              +{skill.tools.length - 4} more
            </span>
          )}
        </div>
      )}

      {/* Footer: action button */}
      <div style={{ marginTop: 'auto', paddingTop: '4px' }}>
        {skill.is_installed ? (
          <button
            onClick={handleUninstall}
            disabled={actionLoading}
            style={{
              width: '100%', padding: '9px', borderRadius: '8px',
              border: '1px solid rgba(239,68,68,0.3)',
              background: 'rgba(239,68,68,0.08)',
              color: actionLoading ? '#64748b' : '#ef4444',
              cursor: actionLoading ? 'not-allowed' : 'pointer',
              fontSize: '0.84rem', fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
              transition: 'background 0.2s, border-color 0.2s',
            }}
            onMouseEnter={e => {
              if (!actionLoading) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.18)';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.08)';
            }}
          >
            {actionLoading ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={14} />}
            {actionLoading ? 'Processing…' : 'Uninstall'}
          </button>
        ) : (
          <button
            onClick={handleInstall}
            disabled={actionLoading}
            style={{
              width: '100%', padding: '9px', borderRadius: '8px',
              border: `1px solid ${skill.color}40`,
              background: `${skill.color}12`,
              color: actionLoading ? '#64748b' : skill.color,
              cursor: actionLoading ? 'not-allowed' : 'pointer',
              fontSize: '0.84rem', fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
              transition: 'background 0.2s, border-color 0.2s',
            }}
            onMouseEnter={e => {
              if (!actionLoading) (e.currentTarget as HTMLButtonElement).style.background = `${skill.color}25`;
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = `${skill.color}12`;
            }}
          >
            {actionLoading ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : (skill.price_type === 'free' ? <Download size={14} /> : <ShoppingCart size={14} />)}
            {actionLoading ? 'Processing…' : (skill.price_type === 'free' ? 'Install' : `Purchase ($${skill.price_usd})`)}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────
export const MarketplaceTab: React.FC = () => {
  const [dbSkills, setDbSkills] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [sortBy, setSortBy] = useState('installed');
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 6; // Feel free to adjust

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, activeCategory, sortBy]);

  const showNotif = (message: string, type: 'success' | 'error' = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3000);
  };

  const fetchDbSkills = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('jarvis_auth_token') || '';
      const response = await fetch('/api/marketplace/skills', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setDbSkills(data.skills || []);
      }
    } catch (err) {
      console.error('Failed to fetch marketplace skills', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDbSkills(); }, [fetchDbSkills]);

  // Merge BUILTIN_SKILLS with any DB-only skills
  const [localInstalled, setLocalInstalled] = useState<Record<string, boolean>>({});

  const allSkills = React.useMemo(() => {
    const builtinIds = new Set(BUILTIN_SKILLS.map(s => s.id));
    const dbOnly = dbSkills.filter(s => !builtinIds.has(s.id));
    const merged = [
      ...BUILTIN_SKILLS.map(s => ({
        ...s,
        is_installed: localInstalled[s.id] !== undefined ? localInstalled[s.id] : s.is_installed,
      })),
      ...dbOnly.map(s => ({ ...s, icon: Package, color: '#94a3b8', tags: [] })),
    ];
    return merged;
  }, [dbSkills, localInstalled]);

  // Filtering & sorting
  const filteredSkills = React.useMemo(() => {
    let list = allSkills;
    if (activeCategory !== 'all') {
      list = list.filter(s => s.category === activeCategory);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(s =>
        s.display_name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        (s.tags || []).some((t: string) => t.toLowerCase().includes(q)) ||
        s.author.toLowerCase().includes(q)
      );
    }
    return [...list].sort((a, b) => {
      if (sortBy === 'name') return a.display_name.localeCompare(b.display_name);
      if (sortBy === 'installed') {
        if (a.is_installed && !b.is_installed) return -1;
        if (!a.is_installed && b.is_installed) return 1;
        return a.display_name.localeCompare(b.display_name);
      }
      if (sortBy === 'category') return a.category.localeCompare(b.category) || a.display_name.localeCompare(b.display_name);
      return 0;
    });
  }, [allSkills, activeCategory, searchQuery, sortBy]);

  const totalPages = Math.ceil(filteredSkills.length / itemsPerPage);
  const paginatedSkills = filteredSkills.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const handleInstall = async (skillId: string) => {
    const token = localStorage.getItem('jarvis_auth_token') || '';
    try {
      const response = await fetch(`/api/marketplace/skills/${skillId}/install`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        setLocalInstalled(prev => ({ ...prev, [skillId]: true }));
        showNotif(`Skill installed successfully`);
      } else {
        showNotif('Failed to install skill', 'error');
      }
    } catch (err) {
      showNotif('Network error during install', 'error');
    }
  };

  const handleUninstall = async (skillId: string) => {
    const token = localStorage.getItem('jarvis_auth_token') || '';
    try {
      const response = await fetch(`/api/marketplace/skills/${skillId}/uninstall`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        setLocalInstalled(prev => ({ ...prev, [skillId]: false }));
        showNotif(`Skill uninstalled`);
      } else {
        showNotif('Failed to uninstall skill', 'error');
      }
    } catch {
      showNotif('Network error during uninstall', 'error');
    }
  };

  const installedCount = allSkills.filter(s => s.is_installed || localInstalled[s.id]).length;
  const currentSortLabel = SORT_OPTIONS.find(o => o.value === sortBy)?.label ?? 'Sort';

  return (
    <div style={{
      padding: '24px',
      color: 'var(--text-primary, #f1f5f9)',
      fontFamily: 'var(--font-sans, Outfit, sans-serif)',
      minHeight: '100%',
      height: '100%',
      overflowY: 'auto',
      position: 'relative',
    }}>

      {/* Notification toast */}
      {notification && (
        <div style={{
          position: 'fixed', top: '20px', right: '20px', zIndex: 1000,
          padding: '12px 20px', borderRadius: '10px',
          background: notification.type === 'success' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
          border: `1px solid ${notification.type === 'success' ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)'}`,
          color: notification.type === 'success' ? '#10b981' : '#ef4444',
          fontSize: '0.875rem', fontWeight: 500,
          display: 'flex', alignItems: 'center', gap: '8px',
          backdropFilter: 'blur(12px)',
          boxShadow: `0 8px 32px rgba(0,0,0,0.4)`,
          animation: 'slideInRight 0.3s ease',
        }}>
          {notification.type === 'success' ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
          {notification.message}
        </div>
      )}

      {/* Header */}
      <div style={{ marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '8px' }}>
          <div style={{
            width: 42, height: 42, borderRadius: '10px',
            background: 'rgba(0,240,255,0.1)', border: '1px solid rgba(0,240,255,0.2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Package size={22} color="var(--accent-cyan, #00f0ff)" />
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-cyan, #00f0ff)', letterSpacing: '-0.02em' }}>
              Skills Marketplace
            </h2>
            <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-dim, #64748b)' }}>
              {installedCount} of {allSkills.length} skills active
            </p>
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', gap: '10px', alignItems: 'stretch' }}>
            {/* Stats chips */}
            <div style={{
              display: 'flex', gap: '8px',
            }}>
              {[
                { label: 'Installed', value: installedCount, color: '#10b981' },
                { label: 'Available', value: allSkills.length - installedCount, color: '#00f0ff' },
              ].map(stat => (
                <div key={stat.label} style={{
                  padding: '6px 14px', borderRadius: '8px',
                  background: `${stat.color}10`, border: `1px solid ${stat.color}25`,
                  textAlign: 'center',
                  display: 'flex', flexDirection: 'column', justifyContent: 'center'
                }}>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: stat.color, lineHeight: 1.2 }}>{stat.value}</div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-dim, #64748b)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{stat.label}</div>
                </div>
              ))}
            </div>

            <button
              onClick={fetchDbSkills}
              title="Refresh from registry"
              style={{
                background: 'rgba(0,240,255,0.08)', border: '1px solid rgba(0,240,255,0.15)',
                borderRadius: '8px', padding: '0 16px', cursor: 'pointer',
                color: 'var(--accent-cyan, #00f0ff)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                fontSize: '0.85rem', fontWeight: 500,
                transition: 'background 0.2s',
              }}
              onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,240,255,0.15)'}
              onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,240,255,0.08)'}
            >
              <RefreshCw size={14} />
              Sync
            </button>
          </div>
        </div>

        {/* Thin separator line */}
        <div style={{ height: '1px', background: 'linear-gradient(90deg, rgba(0,240,255,0.2), transparent)', marginTop: '20px' }} />
      </div>

      {/* Search + Sort toolbar */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {/* Search */}
        <div style={{
          flex: 1, minWidth: '220px', position: 'relative',
          display: 'flex', alignItems: 'center',
        }}>
          <Search size={15} style={{ position: 'absolute', left: '12px', color: 'var(--text-dim, #64748b)' }} />
          <input
            type="text"
            placeholder="Search skills, tools, tags…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              width: '100%', padding: '9px 12px 9px 36px',
              background: 'rgba(16,22,42,0.65)', border: '1px solid rgba(0,240,255,0.12)',
              borderRadius: '9px', color: 'var(--text-primary, #f1f5f9)',
              fontSize: '0.875rem', outline: 'none',
              fontFamily: 'var(--font-sans, Outfit, sans-serif)',
              transition: 'border-color 0.2s',
            }}
            onFocus={e => (e.target as HTMLInputElement).style.borderColor = 'rgba(0,240,255,0.35)'}
            onBlur={e => (e.target as HTMLInputElement).style.borderColor = 'rgba(0,240,255,0.12)'}
          />
        </div>

        {/* Sort dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowSortDropdown(x => !x)}
            style={{
              padding: '9px 14px', borderRadius: '9px', cursor: 'pointer',
              background: 'rgba(16,22,42,0.65)', border: '1px solid rgba(0,240,255,0.12)',
              color: 'var(--text-muted, #94a3b8)', fontSize: '0.875rem',
              display: 'flex', alignItems: 'center', gap: '8px',
              fontFamily: 'var(--font-sans, Outfit, sans-serif)',
            }}
          >
            <Filter size={14} />
            {currentSortLabel}
            <ChevronDown size={12} />
          </button>
          {showSortDropdown && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 4px)', right: 0,
              background: 'var(--bg-surface, #0c1122)', border: '1px solid rgba(0,240,255,0.15)',
              borderRadius: '10px', zIndex: 100, minWidth: '160px',
              overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            }}>
              {SORT_OPTIONS.map(opt => (
                <button key={opt.value} onClick={() => { setSortBy(opt.value); setShowSortDropdown(false); }}
                  style={{
                    width: '100%', padding: '10px 16px', border: 'none', cursor: 'pointer',
                    background: sortBy === opt.value ? 'rgba(0,240,255,0.1)' : 'transparent',
                    color: sortBy === opt.value ? 'var(--accent-cyan, #00f0ff)' : 'var(--text-muted, #94a3b8)',
                    textAlign: 'left', fontSize: '0.875rem',
                    fontFamily: 'var(--font-sans, Outfit, sans-serif)',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => {
                    if (sortBy !== opt.value)
                      (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,240,255,0.05)';
                  }}
                  onMouseLeave={e => {
                    if (sortBy !== opt.value)
                      (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Category tabs */}
      <div style={{
        display: 'flex', gap: '8px', marginBottom: '24px',
        overflowX: 'auto', paddingBottom: '4px',
      }}>
        {CATEGORIES.map(cat => {
          const CatIcon = cat.icon;
          const isActive = activeCategory === cat.id;
          return (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              style={{
                padding: '7px 16px', borderRadius: '50px', cursor: 'pointer',
                background: isActive ? 'rgba(0,240,255,0.12)' : 'rgba(16,22,42,0.5)',
                border: isActive ? '1px solid rgba(0,240,255,0.35)' : '1px solid rgba(0,240,255,0.08)',
                color: isActive ? 'var(--accent-cyan, #00f0ff)' : 'var(--text-muted, #94a3b8)',
                fontSize: '0.82rem', fontWeight: isActive ? 600 : 400, whiteSpace: 'nowrap',
                display: 'flex', alignItems: 'center', gap: '6px',
                fontFamily: 'var(--font-sans, Outfit, sans-serif)',
                transition: 'all 0.2s',
                boxShadow: isActive ? '0 0 12px rgba(0,240,255,0.15)' : 'none',
              }}
            >
              <CatIcon size={13} />
              {cat.label}
            </button>
          );
        })}
      </div>

      {/* Results summary */}
      {!loading && (
        <p style={{ fontSize: '0.78rem', color: 'var(--text-dim, #64748b)', marginBottom: '16px' }}>
          Showing {filteredSkills.length} skill{filteredSkills.length !== 1 ? 's' : ''}
          {activeCategory !== 'all' ? ` in ${CATEGORIES.find(c => c.id === activeCategory)?.label}` : ''}
          {searchQuery ? ` matching "${searchQuery}"` : ''}
        </p>
      )}

      {/* Skills grid */}
      {loading ? (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px',
        }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{
              height: '220px', borderRadius: '14px',
              background: 'rgba(16,22,42,0.4)', border: '1px solid rgba(0,240,255,0.06)',
              animation: 'pulse 1.8s ease-in-out infinite',
              animationDelay: `${i * 0.1}s`,
            }} />
          ))}
        </div>
      ) : filteredSkills.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '64px 24px',
          background: 'rgba(16,22,42,0.4)', border: '1px solid rgba(0,240,255,0.08)',
          borderRadius: '16px',
        }}>
          <Package size={48} color="rgba(0,240,255,0.2)" style={{ marginBottom: '16px' }} />
          <p style={{ color: 'var(--text-muted, #94a3b8)', marginBottom: '8px', fontSize: '1rem', fontWeight: 500 }}>
            No skills match your filters
          </p>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-dim, #64748b)' }}>
            Try clearing the search or selecting "All Skills"
          </p>
          <button
            onClick={() => { setSearchQuery(''); setActiveCategory('all'); }}
            style={{
              marginTop: '18px', padding: '8px 20px', borderRadius: '8px',
              background: 'rgba(0,240,255,0.1)', border: '1px solid rgba(0,240,255,0.25)',
              color: 'var(--accent-cyan, #00f0ff)', cursor: 'pointer',
              fontSize: '0.85rem', fontWeight: 500,
            }}
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: '16px',
          }}>
            {paginatedSkills.map(skill => (
              <SkillCard
                key={skill.id}
                skill={skill}
                onInstall={handleInstall}
                onUninstall={handleUninstall}
              />
            ))}
          </div>
          
          {totalPages > 1 && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', marginTop: '32px'
            }}>
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                style={{
                  background: 'rgba(0,240,255,0.08)', border: '1px solid rgba(0,240,255,0.15)',
                  borderRadius: '8px', padding: '8px', cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                  color: currentPage === 1 ? 'var(--text-dim, #64748b)' : 'var(--accent-cyan, #00f0ff)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.2s',
                }}
              >
                <ChevronLeft size={18} />
              </button>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted, #94a3b8)', fontFamily: 'var(--font-sans, Outfit, sans-serif)', fontWeight: 500 }}>
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                style={{
                  background: 'rgba(0,240,255,0.08)', border: '1px solid rgba(0,240,255,0.15)',
                  borderRadius: '8px', padding: '8px', cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                  color: currentPage === totalPages ? 'var(--text-dim, #64748b)' : 'var(--accent-cyan, #00f0ff)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.2s',
                }}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </>
      )}

      {/* Footer note */}
      <div style={{
        marginTop: '40px', padding: '16px 20px', borderRadius: '10px',
        background: 'rgba(0,240,255,0.04)', border: '1px solid rgba(0,240,255,0.08)',
        display: 'flex', alignItems: 'center', gap: '12px',
      }}>
        <ShieldCheck size={16} color="rgba(0,240,255,0.5)" style={{ flexShrink: 0 }} />
        <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-dim, #64748b)', lineHeight: 1.5 }}>
          All skills are <strong style={{ color: 'var(--text-muted)' }}>open source</strong> and run entirely on your infrastructure.
          Contribute your own via <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan, #00f0ff)', fontSize: '0.78rem' }}>hermes_sdk</code>.
        </p>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 0.3; }
        }
        @keyframes slideInRight {
          from { transform: translateX(20px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
};
