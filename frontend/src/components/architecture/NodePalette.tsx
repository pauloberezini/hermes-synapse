import { useState } from 'react';
import { 
  Layers, 
  Bot, 
  ChevronLeft, 
  ChevronRight, 
  Plus, 
  Sparkles,
  Search,
  Cpu
} from 'lucide-react';
import { SKILLS_LIST } from '../NetworkTab';

interface NodePaletteProps {
  onAddSubagent: (type: 'orchestrator' | 'agent', archetype?: string) => void;
  onAddSkillToLayer: (skillId: string) => void;
}

export function NodePalette({ onAddSubagent, onAddSkillToLayer }: NodePaletteProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<'nodes' | 'skills'>('nodes');
  const [skillSearch, setSkillSearch] = useState('');

  const filteredSkills = SKILLS_LIST.filter(s => 
    s.name.toLowerCase().includes(skillSearch.toLowerCase()) || 
    s.desc.toLowerCase().includes(skillSearch.toLowerCase())
  );

  if (isCollapsed) {
    return (
      <div style={{
        position: 'absolute',
        left: 12,
        top: 60,
        zIndex: 20
      }}>
        <button
          onClick={() => setIsCollapsed(false)}
          title="Open Palette"
          style={{
            background: 'var(--bg-secondary, #1e293b)',
            color: 'var(--text-secondary, #9ca3af)',
            border: '1px solid var(--border-color, rgba(255,255,255,0.15))',
            borderRadius: '8px',
            padding: '10px',
            cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <ChevronRight size={18} />
        </button>
      </div>
    );
  }

  return (
    <div style={{
      position: 'absolute',
      left: 12,
      top: 60,
      width: 250,
      maxHeight: 'calc(100% - 80px)',
      background: 'var(--bg-secondary, #0f172a)',
      border: '1px solid var(--border-color, rgba(255,255,255,0.12))',
      borderRadius: '12px',
      zIndex: 20,
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
      overflow: 'hidden',
      backdropFilter: 'blur(12px)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 14px',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(0,0,0,0.2)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sparkles size={16} style={{ color: '#38bdf8' }} />
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#f3f4f6' }}>
            Node Palette
          </span>
        </div>
        <button
          onClick={() => setIsCollapsed(true)}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#6b7280',
            cursor: 'pointer',
            padding: '2px',
            borderRadius: '4px'
          }}
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(0,0,0,0.1)'
      }}>
        <button
          onClick={() => setActiveTab('nodes')}
          style={{
            flex: 1,
            padding: '8px 0',
            fontSize: '12px',
            fontWeight: 500,
            border: 'none',
            cursor: 'pointer',
            background: activeTab === 'nodes' ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
            color: activeTab === 'nodes' ? '#38bdf8' : '#9ca3af',
            borderBottom: activeTab === 'nodes' ? '2px solid #38bdf8' : '2px solid transparent'
          }}
        >
          Nodes & Agents
        </button>
        <button
          onClick={() => setActiveTab('skills')}
          style={{
            flex: 1,
            padding: '8px 0',
            fontSize: '12px',
            fontWeight: 500,
            border: 'none',
            cursor: 'pointer',
            background: activeTab === 'skills' ? 'rgba(168, 85, 247, 0.12)' : 'transparent',
            color: activeTab === 'skills' ? '#c084fc' : '#9ca3af',
            borderBottom: activeTab === 'skills' ? '2px solid #c084fc' : '2px solid transparent'
          }}
        >
          Skills & Tools
        </button>
      </div>

      {/* Body Content */}
      <div style={{ padding: '12px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {activeTab === 'nodes' ? (
          <>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#6b7280', fontWeight: 600, letterSpacing: '0.5px' }}>
              Orchestrators
            </div>

            <div
              onClick={() => onAddSubagent('orchestrator')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '10px',
                background: 'rgba(139, 92, 246, 0.12)',
                border: '1px solid rgba(139, 92, 246, 0.3)',
                borderRadius: '8px',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
            >
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '6px',
                background: 'rgba(139, 92, 246, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#c084fc'
              }}>
                <Layers size={18} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#f3f4f6' }}>Sub-Orchestrator</div>
                <div style={{ fontSize: '11px', color: '#9ca3af' }}>Delegator & Manager Node</div>
              </div>
              <Plus size={16} style={{ color: '#c084fc' }} />
            </div>

            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#6b7280', fontWeight: 600, letterSpacing: '0.5px', marginTop: '6px' }}>
              Agent Archetypes
            </div>

            {[
              { id: 'research', name: 'Research Agent', desc: 'Web search & summarize', color: '#38bdf8', icon: Search },
              { id: 'code', name: 'Code Agent', desc: 'Write & test code', color: '#10b981', icon: Cpu },
              { id: 'analyst', name: 'Analyst Agent', desc: 'Data & strategy analysis', color: '#f59e0b', icon: Bot },
              { id: 'custom', name: 'Custom Worker', desc: 'Blank agent instance', color: '#a855f7', icon: Bot }
            ].map(archetype => {
              const IconComp = archetype.icon;
              return (
                <div
                  key={archetype.id}
                  onClick={() => onAddSubagent('agent', archetype.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 10px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
                  }}
                >
                  <div style={{
                    width: '30px',
                    height: '30px',
                    borderRadius: '6px',
                    background: `${archetype.color}15`,
                    border: `1px solid ${archetype.color}30`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: archetype.color
                  }}>
                    <IconComp size={16} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '12px', fontWeight: 500, color: '#e5e7eb' }}>{archetype.name}</div>
                    <div style={{ fontSize: '10px', color: '#9ca3af' }}>{archetype.desc}</div>
                  </div>
                  <Plus size={14} style={{ color: '#6b7280' }} />
                </div>
              );
            })}
          </>
        ) : (
          <>
            <input
              type="text"
              placeholder="Search skills..."
              value={skillSearch}
              onChange={(e) => setSkillSearch(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '6px',
                padding: '6px 10px',
                color: '#fff',
                fontSize: '12px',
                outline: 'none',
                marginBottom: '4px'
              }}
            />

            {filteredSkills.map(skill => (
              <div
                key={skill.id}
                onClick={() => onAddSkillToLayer(skill.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 10px',
                  background: 'rgba(255,255,255,0.03)',
                  border: `1px solid ${skill.color}40`,
                  borderRadius: '8px',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
              >
                <div style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: skill.color
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '12px', fontWeight: 500, color: '#f3f4f6' }}>{skill.name}</div>
                  <div style={{ fontSize: '10px', color: '#9ca3af' }}>{skill.desc}</div>
                </div>
                <Plus size={14} style={{ color: skill.color }} />
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
