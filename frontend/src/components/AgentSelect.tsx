import React, { useState, useRef, useEffect, useMemo } from 'react';
import { ChevronDown, Search, X, Check } from 'lucide-react';
import { getSortedAgents, getAgentIcon, isOrchestratorAgent } from '../utils';

export interface AgentOption {
  id: string;
  name?: string;
  agent_type?: string;
  skills?: string;
  model?: string;
}

export interface AgentSelectProps {
  agents: AgentOption[];
  value: string;
  onChange: (agentId: string) => void;
  placeholder?: string;
  labelPrefix?: string;
  style?: React.CSSProperties;
  variant?: 'compact' | 'full' | 'subtle';
  disabled?: boolean;
}

export function AgentSelect({
  agents,
  value,
  onChange,
  placeholder = 'Search agent...',
  labelPrefix,
  style,
  variant = 'compact',
  disabled = false
}: AgentSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Sorted list of all agents (Orchestrators first A-Z, then Worker Agents A-Z)
  const sortedAgents = useMemo(() => {
    return getSortedAgents(Array.isArray(agents) ? agents : []);
  }, [agents]);

  // Current selected agent
  const selectedAgent = useMemo(() => {
    return sortedAgents.find(a => a.id === value) || sortedAgents[0] || { id: value, name: value };
  }, [sortedAgents, value]);

  // Filtered agents based on user input
  const filteredAgents = useMemo(() => {
    if (!searchQuery.trim()) return sortedAgents;
    const q = searchQuery.toLowerCase().trim();
    return sortedAgents.filter(a => 
      (a.name || '').toLowerCase().includes(q) ||
      a.id.toLowerCase().includes(q) ||
      (a.agent_type || '').toLowerCase().includes(q) ||
      (a.skills || '').toLowerCase().includes(q)
    );
  }, [sortedAgents, searchQuery]);

  // Handle click outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setSearchQuery('');
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Auto-focus input when opened
  useEffect(() => {
    if (isOpen) {
      setHighlightedIndex(0);
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const handleSelect = (agentId: string) => {
    onChange(agentId);
    setIsOpen(false);
    setSearchQuery('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'Enter' || e.key === 'ArrowDown' || e.key === ' ') {
        setIsOpen(true);
        e.preventDefault();
      }
      return;
    }

    if (e.key === 'Escape') {
      setIsOpen(false);
      setSearchQuery('');
      e.preventDefault();
    } else if (e.key === 'ArrowDown') {
      setHighlightedIndex(prev => (prev + 1) % (filteredAgents.length || 1));
      e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      setHighlightedIndex(prev => (prev - 1 + filteredAgents.length) % (filteredAgents.length || 1));
      e.preventDefault();
    } else if (e.key === 'Enter') {
      if (filteredAgents[highlightedIndex]) {
        handleSelect(filteredAgents[highlightedIndex].id);
      }
      e.preventDefault();
    }
  };

  const isCompact = variant === 'compact' || variant === 'subtle';

  return (
    <div
      ref={containerRef}
      onKeyDown={handleKeyDown}
      style={{
        position: 'relative',
        display: 'inline-block',
        minWidth: isCompact ? '200px' : '100%',
        ...style
      }}
    >
      {/* Trigger Button / Header */}
      <div
        onClick={() => !disabled && setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          padding: isCompact ? '5px 10px' : '9px 12px',
          background: variant === 'subtle' 
            ? 'rgba(15, 23, 42, 0.6)' 
            : 'rgba(15, 23, 42, 0.9)',
          border: isOpen 
            ? '1px solid var(--accent-cyan, #00f0ff)' 
            : '1px solid rgba(255, 255, 255, 0.12)',
          borderRadius: '8px',
          color: '#fff',
          cursor: disabled ? 'not-allowed' : 'pointer',
          fontSize: isCompact ? '0.78rem' : '0.88rem',
          fontWeight: 600,
          boxShadow: isOpen ? '0 0 12px rgba(0, 240, 255, 0.25)' : 'none',
          transition: 'all 0.2s ease',
          userSelect: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 }}>
          {labelPrefix && (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-dim, #94a3b8)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
              {labelPrefix}
            </span>
          )}
          <span style={{ fontSize: '0.95rem', flexShrink: 0 }}>
            {getAgentIcon(selectedAgent)}
          </span>
          <span style={{ 
            color: isOrchestratorAgent(selectedAgent) ? 'var(--accent-cyan, #00f0ff)' : '#fff',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {selectedAgent.name || selectedAgent.id}
          </span>
          {isOrchestratorAgent(selectedAgent) && (
            <span style={{
              fontSize: '0.55rem',
              fontWeight: 700,
              padding: '1px 5px',
              borderRadius: '4px',
              background: 'rgba(168, 85, 247, 0.2)',
              color: '#c084fc',
              border: '1px solid rgba(168, 85, 247, 0.4)',
              textTransform: 'uppercase',
              flexShrink: 0
            }}>
              Orch
            </span>
          )}
        </div>
        <ChevronDown size={14} style={{ color: 'var(--text-dim)', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
      </div>

      {/* Autocomplete Dropdown Menu */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            right: 0,
            zIndex: 9999,
            background: '#0b0f19',
            border: '1px solid rgba(0, 240, 255, 0.3)',
            borderRadius: '10px',
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.8), 0 0 16px rgba(0, 240, 255, 0.15)',
            padding: '6px',
            minWidth: '240px',
            maxHeight: '340px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            backdropFilter: 'blur(16px)'
          }}
        >
          {/* Autocomplete Search Input */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '6px',
            padding: '6px 10px'
          }}>
            <Search size={13} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setHighlightedIndex(0);
              }}
              placeholder={placeholder}
              style={{
                width: '100%',
                background: 'transparent',
                border: 'none',
                color: '#fff',
                fontSize: '0.8rem',
                outline: 'none',
                fontFamily: 'inherit'
              }}
            />
            {searchQuery && (
              <X
                size={13}
                onClick={() => setSearchQuery('')}
                style={{ color: 'var(--text-dim)', cursor: 'pointer', flexShrink: 0 }}
              />
            )}
          </div>

          {/* Filtered Agent List */}
          <div style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {filteredAgents.length === 0 ? (
              <div style={{ padding: '12px', textAlign: 'center', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                No agents match "{searchQuery}"
              </div>
            ) : (
              filteredAgents.map((agent, idx) => {
                const isOrch = isOrchestratorAgent(agent);
                const icon = getAgentIcon(agent);
                const isSelected = agent.id === value;
                const isHighlighted = idx === highlightedIndex;

                return (
                  <div
                    key={agent.id}
                    onClick={() => handleSelect(agent.id)}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '7px 10px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      background: isSelected 
                        ? 'rgba(0, 240, 255, 0.15)' 
                        : isHighlighted 
                          ? 'rgba(255, 255, 255, 0.06)' 
                          : 'transparent',
                      border: isSelected 
                        ? '1px solid rgba(0, 240, 255, 0.4)' 
                        : isHighlighted 
                          ? '1px solid rgba(255, 255, 255, 0.1)' 
                          : '1px solid transparent',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
                      <span style={{ fontSize: '1rem', flexShrink: 0 }}>{icon}</span>
                      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{
                            fontSize: '0.8rem',
                            fontWeight: 600,
                            color: isSelected ? 'var(--accent-cyan)' : '#fff',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis'
                          }}>
                            {agent.name || agent.id}
                          </span>
                          {isOrch && (
                            <span style={{
                              fontSize: '0.55rem',
                              fontWeight: 700,
                              padding: '1px 5px',
                              borderRadius: '4px',
                              background: 'rgba(168, 85, 247, 0.25)',
                              color: '#c084fc',
                              border: '1px solid rgba(168, 85, 247, 0.4)',
                              textTransform: 'uppercase',
                              flexShrink: 0
                            }}>
                              Orchestrator
                            </span>
                          )}
                        </div>
                        {agent.model && (
                          <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)' }}>
                            {agent.model.split('/').pop()}
                          </span>
                        )}
                      </div>
                    </div>

                    {isSelected && (
                      <Check size={14} style={{ color: 'var(--accent-cyan)', flexShrink: 0 }} />
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
