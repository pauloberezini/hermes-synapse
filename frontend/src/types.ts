import React from 'react';

export interface LLMRunMeta {
  status?: 'success' | 'tool_call' | 'empty' | 'refusal' | 'timeout' | 'provider_error' | 'parse_error' | string;
  model?: string | null;
  provider?: string | null;
  finish_reason?: string | null;
  request_id?: string | null;
  latency_ms?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  tool_iterations?: number | null;
}

export interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  chat_id?: string | number;
  cost_usd?: number;
  meta?: LLMRunMeta;
  run_id?: string;
  streaming?: boolean;
  thinking?: string;
}

export interface DecisionLog {
  timestamp: string;
  session_id: string;
  model: string;
  latency_ms: number;
  success: boolean;
  error: string | null;
  prompt_tokens_estimate: number;
  user_message: string;
  assistant_response: string;
  traces?: { timestamp: string; agent: string; action: string; message: string; status: string }[];
  agent_id?: string;
  completion_tokens_estimate?: number;
  cost_usd?: number;
}

export interface ActivityLog {
  timestamp: string;
  type: 'active' | 'idle';
  source: string;
  message: string;
  token_cost: number;
}

export interface SystemConfig {
  system_prompt: string;
  model: string;
  fast_mode?: boolean;
  max_history_len?: number;
  max_tokens?: number;
  tool_max_tokens?: number;
  temperature?: number;
  auto_rag?: boolean;
  memory_enabled?: boolean;
  memory_auto_save?: boolean;
  memory_max_items?: number;
  provider?: 'ollama' | 'openrouter' | 'openai_compatible' | string;
  api_base?: string;
  ollama_base_url?: string;
  openai_api_base?: string;
  ollama_num_ctx?: number;
  ollama_keep_alive?: string | number;
  ollama_think?: boolean | 'low' | 'medium' | 'high' | string;
}

export interface OllamaModel {
  name: string;
  model?: string;
  size?: number;
  digest?: string;
  modified_at?: string;
  size_vram?: number;
  context_length?: number;
  expires_at?: string;
  details?: {
    family?: string;
    parameter_size?: string;
    quantization_level?: string;
    format?: string;
  };
}

export interface OllamaStatus {
  available: boolean;
  base_url: string;
  version?: string;
  models_count?: number;
  running_count?: number;
  error?: string;
  code?: string;
}

export interface AgentModel {
  id: string;
  name: string;
  system_prompt: string;
  model: string;
  created_at?: string;
  agent_type?: string;
  parent_id?: string | null;
  project?: string;
  project_id?: string;
  project_name?: string;
  workspace?: string;
  skills?: string;
  x?: number;
  y?: number;
  temperature?: number;
  role?: string;
  status?: 'idle' | 'working' | 'error' | 'disabled' | string;
  is_enabled?: boolean;
  model_provider?: string;
  model_type?: 'local' | 'external' | string;
  model_params?: Record<string, unknown>;
  current_task?: string;
  last_action?: string;
  last_error?: string;
  progress?: number;
  updated_at?: string;
  recent_events?: AgentEvent[];
}

export interface AgentEvent {
  id: number;
  agent_id: string;
  timestamp: string;
  event_type: string;
  message: string;
  status: string;
  task?: string;
  metadata?: Record<string, unknown>;
}

export interface WorkflowTask {
  id: string;
  parent_id?: string | null;
  origin: string;
  requester: string;
  goal: string;
  tool_name?: string | null;
  tool_arguments?: Record<string, unknown>;
  assignee: string;
  risk_class: 'R0' | 'R1' | 'R2' | 'R3' | 'R4';
  autonomy_level: 'L0' | 'L1' | 'L2' | 'L3' | 'L4' | 'L5';
  data_class: string;
  status: 'queued' | 'running' | 'blocked' | 'awaiting_approval' | 'approved' | 'done' | 'failed' | 'killed' | 'rejected';
  approvals_required: number;
  approval_count: number;
  approval_required: boolean;
  budget_commands: number;
  budget_tokens: number;
  budget_wallclock_s: number;
  commands_used: number;
  tokens_used: number;
  acceptance: string[];
  rollback: string;
  result: string;
  error: string;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface WorkflowEvent {
  id: number;
  evidence_id: string;
  task_id?: string | null;
  event_type: string;
  actor: string;
  message: string;
  risk_class: string;
  confidence: string;
  output_hash: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface ControlPlaneSummary {
  state: {
    kill_switch: boolean;
    reason: string;
    updated_by: string;
    updated_at: string;
  };
  counts: Record<string, number>;
  pending_approvals: WorkflowTask[];
  tasks: WorkflowTask[];
  events: WorkflowEvent[];
  policy: {
    risk_levels: string[];
    unknown_tools: string;
    r4_double_confirmation: boolean;
  };
}

export interface AutonomyCapability {
  id: string;
  label: string;
  required: boolean;
  status: 'ready' | 'missing';
  active_provider?: string | null;
  install_available: boolean;
  providers: Array<{ id: string; status: 'ready' | 'missing' | 'broken'; detail: string }>;
}

export interface AutonomyPlan {
  id: string;
  goal: string;
  tier: string;
  status: 'planned' | 'running' | 'completed' | 'failed' | string;
  capabilities: string[];
  steps: Array<{
    id: string;
    agent: string;
    title: string;
    status: string;
    attempts: number;
  }>;
  updated_at: string;
}

export interface AutonomySummary {
  workspace: string;
  capabilities: {
    status: 'ready' | 'degraded';
    ready: number;
    total: number;
    checked_at: string;
    capabilities: AutonomyCapability[];
  };
  memory: {
    files: number;
    bytes: number;
    fresh_at?: string | null;
    entries: number;
  };
  plans: AutonomyPlan[];
  proposals: Array<{
    id: string;
    capability_id: string;
    status: string;
    risk_class: string;
    control_task_id?: string | null;
    plan?: {
      recipe?: {
        package?: string;
        version?: string;
        license?: string;
      };
      enabled?: boolean;
      isolation?: Record<string, boolean>;
    };
    created_at: string;
    updated_at?: string;
  }>;
}

export interface SystemStats {
  available?: boolean;
  cpu_load_percent?: number | null;
  ram_used_percent?: number | null;
  ram_total_gb?: number | null;
  disk_used_percent?: number | null;
  disk_total_gb?: number | null;
  disk_used_gb?: number | null;
  status: string;
  scope?: string;
  source?: string;
  warning?: string;
  host_error?: string;
  unavailable?: string[];
  error?: string | null;
  collected_at?: string;
  age_seconds?: number | null;
  stale?: boolean;
  host?: HostTelemetry;
  runtime?: Omit<SystemStats, 'host' | 'runtime'>;
}

export interface HostTelemetry {
  hostname?: string;
  os?: string;
  kernel?: string;
  architecture?: string;
  uptime_seconds?: number;
  boot_time?: string | null;
  process_count?: number;
  cpu?: {
    model?: string;
    logical_cores?: number;
    usage_percent?: number | null;
    load_1m?: number | null;
    load_5m?: number | null;
    load_15m?: number | null;
  };
  memory?: {
    total_bytes?: number;
    used_bytes?: number;
    available_bytes?: number;
    usage_percent?: number | null;
    swap_total_bytes?: number;
    swap_used_bytes?: number;
  };
  disks?: Array<{
    device?: string;
    mountpoint?: string;
    filesystem?: string;
    total_bytes?: number;
    used_bytes?: number;
    available_bytes?: number;
    usage_percent?: number | null;
  }>;
  network?: {
    primary_ip?: string | null;
    rx_bytes?: number;
    tx_bytes?: number;
    rx_bytes_per_second?: number;
    tx_bytes_per_second?: number;
    interfaces?: Array<{
      name?: string;
      rx_bytes?: number;
      tx_bytes?: number;
      rx_bytes_per_second?: number;
      tx_bytes_per_second?: number;
    }>;
  };
  gpus?: Array<{
    index?: number;
    name?: string;
    uuid?: string;
    driver_version?: string;
    memory_total_bytes?: number | null;
    memory_used_bytes?: number | null;
    memory_usage_percent?: number | null;
    utilization_percent?: number | null;
    memory_utilization_percent?: number | null;
    temperature_celsius?: number | null;
    power_draw_watts?: number | null;
    power_limit_watts?: number | null;
    fan_percent?: number | null;
  }>;
  containers?: Array<{
    name?: string;
    image?: string;
    state?: string;
    health?: string;
    status?: string;
    ports?: string;
    cpu_percent?: number | null;
    memory_percent?: number | null;
    memory_usage?: string | null;
    network_io?: string | null;
    block_io?: string | null;
    pids?: number | null;
  }>;
}

export interface RenderedListItem {
  indent: number;
  content: React.ReactNode[];
}

export interface AppSettings {
  language: string; // BCP-47 short code: 'ru', 'en', 'he', 'de', 'es', 'fr'
}

export interface ChatSession {
  id: string;
  title: string;
  agent_id?: string;
}
