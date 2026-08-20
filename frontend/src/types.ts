import React from 'react';

export interface ToolCallLog {
  name: string;
  args: Record<string, unknown>;
  result: string;
  skill?: string | null;
}

export interface AgentThread {
  id: number;
  agent_id: string;
  agent_name: string;
  model: string;
  user_message: string;
  assistant_response: string;
  skills_used: string[];
  tool_calls_log: ToolCallLog[];
  latency_ms: number;
  cost_usd: number;
  timestamp: string;
  success: boolean;
  error?: string | null;
}

export interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  chat_id?: string | number;
  cost_usd?: number;
  timestamp?: string;
  created_at?: string;
  agent_threads?: AgentThread[];      // lazy-loaded subagent communication threads
  agent_threads_loaded?: boolean;     // true once fetch has been attempted
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
  is_scheduled?: boolean;
  job_id?: string;
  schedule_type?: 'one-shot' | 'alarm' | 'recurring' | string;
  schedule_info?: {
    status?: 'running' | 'paused' | 'completed' | 'cancelled' | string;
    label?: string;
    prompt?: string;
    duration?: number;
    target_time?: string;
    interval_hours?: number;
    time_left?: number;
    created_at?: string;
    fire_count?: number;
    [key: string]: any;
  };
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

