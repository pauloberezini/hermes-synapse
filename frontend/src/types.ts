import React from 'react';

export interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  chat_id?: string | number;
  cost_usd?: number;
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
}

