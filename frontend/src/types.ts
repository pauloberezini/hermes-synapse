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
  unavailable?: string[];
  error?: string | null;
}

export interface RenderedListItem {
  indent: number;
  content: React.ReactNode[];
}
