import { useState, useEffect } from 'react';
import { 
  X, 
  Save, 
  Trash2, 
  Bot, 
  Layers, 
  Wrench, 
  Sliders, 
  Cpu,
  FileText
} from 'lucide-react';
import { SKILLS_LIST } from '../NetworkTab';

interface NodeInspectorDrawerProps {
  selectedNode: any | null;
  onClose: () => void;
  onSaveNode: (updatedData: any) => Promise<void>;
  onDeleteNode: (nodeId: string) => Promise<void>;
  models: Array<{ id: string; name: string }>;
  orchestrators: Array<{ id: string; name: string }>;
}

export function NodeInspectorDrawer({
  selectedNode,
  onClose,
  onSaveNode,
  onDeleteNode,
  models,
  orchestrators
}: NodeInspectorDrawerProps) {
  const [name, setName] = useState('');
  const [model, setModel] = useState('google/gemini-2.5-flash');
  const [agentType, setAgentType] = useState<'orchestrator' | 'agent'>('agent');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [parentId, setParentId] = useState<string | null>(null);
  const [temperature, setTemperature] = useState(0.7);
  const [skills, setSkills] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (selectedNode) {
      setName(selectedNode.name || '');
      setModel(selectedNode.model || 'google/gemini-2.5-flash');
      setAgentType(selectedNode.agent_type || (selectedNode.id === 'jarvis' ? 'orchestrator' : 'agent'));
      setSystemPrompt(selectedNode.system_prompt || '');
      setParentId(selectedNode.parent_id || null);
      setTemperature(typeof selectedNode.temperature === 'number' ? selectedNode.temperature : 0.7);
      
      const skillStr = selectedNode.skills || '';
      const skillArr = skillStr ? skillStr.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
      setSkills(skillArr);
    }
  }, [selectedNode]);

  if (!selectedNode) return null;

  const handleToggleSkill = (skillId: string) => {
    if (skills.includes(skillId)) {
      setSkills(skills.filter(s => s !== skillId));
    } else {
      setSkills([...skills, skillId]);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSaveNode({
        id: selectedNode.id,
        name,
        model,
        agent_type: agentType,
        system_prompt: systemPrompt,
        parent_id: parentId,
        temperature,
        skills: skills.join(','),
        x: selectedNode.x || 100,
        y: selectedNode.y || 100
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div style={{
      position: 'absolute',
      right: 0,
      top: 0,
      bottom: 0,
      width: 380,
      background: 'var(--bg-secondary, #0f172a)',
      borderLeft: '1px solid var(--border-color, rgba(255,255,255,0.12))',
      zIndex: 30,
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '-8px 0 24px rgba(0,0,0,0.4)',
      backdropFilter: 'blur(12px)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 18px',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(0,0,0,0.2)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {agentType === 'orchestrator' ? (
            <Layers size={18} style={{ color: '#c084fc' }} />
          ) : (
            <Bot size={18} style={{ color: '#38bdf8' }} />
          )}
          <span style={{ fontSize: '14px', fontWeight: 600, color: '#f3f4f6' }}>
            Inspector: {selectedNode.name || selectedNode.id}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#6b7280',
            cursor: 'pointer',
            padding: '4px',
            borderRadius: '4px'
          }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Body / Form fields */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px'
      }}>
        {/* ID Badge */}
        <div style={{
          fontSize: '11px',
          fontFamily: 'monospace',
          color: '#9ca3af',
          background: 'rgba(0,0,0,0.3)',
          padding: '4px 8px',
          borderRadius: '4px',
          alignSelf: 'flex-start'
        }}>
          Node ID: {selectedNode.id}
        </div>

        {/* Display Name */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db' }}>Display Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{
              background: 'rgba(15, 23, 42, 0.8)',
              color: '#f3f4f6',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '13px',
              outline: 'none'
            }}
          />
        </div>

        {/* Node Type */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db' }}>Node Classification</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setAgentType('agent')}
              style={{
                flex: 1,
                padding: '8px',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: agentType === 'agent' ? '#38bdf8' : 'rgba(255,255,255,0.1)',
                background: agentType === 'agent' ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                color: agentType === 'agent' ? '#38bdf8' : '#9ca3af',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer'
              }}
            >
              Sub-Agent
            </button>
            <button
              onClick={() => setAgentType('orchestrator')}
              style={{
                flex: 1,
                padding: '8px',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: agentType === 'orchestrator' ? '#c084fc' : 'rgba(255,255,255,0.1)',
                background: agentType === 'orchestrator' ? 'rgba(192, 132, 252, 0.15)' : 'transparent',
                color: agentType === 'orchestrator' ? '#c084fc' : '#9ca3af',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer'
              }}
            >
              Sub-Orchestrator
            </button>
          </div>
        </div>

        {/* Model Selection */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Cpu size={14} style={{ color: '#10b981' }} />
            AI Model Engine
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{
              background: 'rgba(15, 23, 42, 0.8)',
              color: '#f3f4f6',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '13px',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            {models.map(m => (
              <option key={m.id} value={m.id}>
                {m.name || m.id}
              </option>
            ))}
          </select>
        </div>

        {/* Parent Orchestrator */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Layers size={14} style={{ color: '#c084fc' }} />
            Parent Orchestrator Scope
          </label>
          <select
            value={parentId || 'jarvis'}
            onChange={(e) => setParentId(e.target.value)}
            style={{
              background: 'rgba(15, 23, 42, 0.8)',
              color: '#f3f4f6',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '13px',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            {orchestrators.map(orch => (
              <option key={orch.id} value={orch.id}>
                {orch.name} ({orch.id})
              </option>
            ))}
          </select>
        </div>

        {/* Temperature Slider */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Sliders size={14} style={{ color: '#f59e0b' }} />
              Temperature
            </label>
            <span style={{ fontSize: '12px', color: '#f59e0b', fontWeight: 600 }}>{temperature}</span>
          </div>
          <input
            type="range"
            min="0.0"
            max="1.0"
            step="0.05"
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: '#f59e0b', cursor: 'pointer' }}
          />
        </div>

        {/* System Prompt */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <FileText size={14} style={{ color: '#38bdf8' }} />
            System Instructions / Prompt
          </label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={6}
            style={{
              background: 'rgba(15, 23, 42, 0.8)',
              color: '#f3f4f6',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '12px',
              fontFamily: 'monospace',
              outline: 'none',
              resize: 'vertical'
            }}
          />
        </div>

        {/* Attached Skills */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Wrench size={14} style={{ color: '#c084fc' }} />
            Attached Tool & Skill Sockets
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '180px', overflowY: 'auto' }}>
            {SKILLS_LIST.map(skill => {
              const isChecked = skills.includes(skill.id);
              return (
                <div
                  key={skill.id}
                  onClick={() => handleToggleSkill(skill.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    borderRadius: '6px',
                    background: isChecked ? 'rgba(139, 92, 246, 0.15)' : 'rgba(0,0,0,0.2)',
                    border: isChecked ? `1px solid ${skill.color}50` : '1px solid rgba(255,255,255,0.06)',
                    cursor: 'pointer'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: skill.color }} />
                    <span style={{ fontSize: '12px', color: isChecked ? '#f3f4f6' : '#9ca3af' }}>{skill.name}</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}} // handled by row click
                    style={{ cursor: 'pointer' }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Footer / Actions */}
      <div style={{
        padding: '14px 18px',
        borderTop: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(0,0,0,0.2)',
        display: 'flex',
        gap: '10px'
      }}>
        {selectedNode.id !== 'jarvis' && (
          <button
            onClick={() => onDeleteNode(selectedNode.id)}
            style={{
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#f87171',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '6px',
              padding: '8px 12px',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Trash2 size={14} />
            Delete
          </button>
        )}

        <button
          onClick={handleSave}
          disabled={isSaving}
          style={{
            flex: 1,
            background: 'var(--accent-cyan, #06b6d4)',
            color: '#000',
            border: 'none',
            borderRadius: '6px',
            padding: '8px 12px',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            opacity: isSaving ? 0.7 : 1
          }}
        >
          <Save size={14} />
          {isSaving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}
