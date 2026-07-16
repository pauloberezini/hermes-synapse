import React, { useState, useEffect, useRef } from 'react';
import { 
  Layers, 
  GitBranch, 
  Wrench, 
  Plus, 
  CheckCircle2, 
  Trash2 
} from 'lucide-react';

export const SKILLS_LIST = [
  { id: 'web_search', name: 'Web Search', desc: 'DuckDuckGo search, weather, RSS news', color: 'var(--accent-cyan)' },
  { id: 'market_monitor', name: 'Market Monitor', desc: 'Stock quotes and alerts', color: '#10b981' },
  { id: 'obsidian_rag', name: 'Obsidian Vault', desc: 'Read and write Obsidian notes', color: '#8b5cf6' },
  { id: 'todoist_sync', name: 'Todoist Tasks', desc: 'Sync Todoist task lists', color: '#ef4444' },
  { id: 'google_calendar', name: 'Google Calendar', desc: 'Calendar scheduling', color: '#f59e0b' },
  { id: 'timers_alarms', name: 'Timers/Alarms', desc: 'Manage timers and alarms', color: '#3b82f6' },
  { id: 'shell_execution', name: 'Terminal Shell', desc: 'Execute server terminal commands', color: '#6b7280' },
  { id: 'python_sandbox', name: 'Python Sandbox', desc: 'Calculations and mathematical expectations', color: '#14b8a6' }
];

interface NetworkTabProps {
  subagents: any[];
  setSubagents: (s: any[]) => void;
  fetchSubagents: () => void;
  models: { id: string; name: string }[];
}

export function NetworkTab({ 
  subagents, 
  setSubagents, 
  fetchSubagents,
  models,
}: NetworkTabProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodes, setSelectedNodes] = useState<Array<{ id: string; isSkill: boolean }>>([]);
  const [selectionBox, setSelectionBox] = useState<{ startX: number; startY: number; endX: number; endY: number } | null>(null);
  const [canvasClickStart, setCanvasClickStart] = useState<{ x: number; y: number } | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<{ id: string; type: 'orchestrator' | 'agent'; x: number; y: number } | null>(null);
  const [cursorPos, setCursorPos] = useState({ x: 0, y: 0 });
  const [draggingNode, setDraggingNode] = useState<{
    mouseStartX: number;
    mouseStartY: number;
    nodes: Array<{ id: string; isSkill: boolean; x: number; y: number }>;
  } | null>(null);

  // Skill Positions state (saves/loads from localStorage for persistence)
  const [skillPositions, setSkillPositions] = useState<Record<string, { x: number; y: number }>>(() => {
    const saved = localStorage.getItem('jarvis_skill_positions');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {}
    }
    const defaults: Record<string, { x: number; y: number }> = {};
    SKILLS_LIST.forEach((skill, skIndex) => {
      defaults[skill.id] = { x: 3500, y: 50 + skIndex * 135 };
    });
    return defaults;
  });

  // Zoom & Pan states
  const [zoom, setZoom] = useState(1.0);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  const canvasContainerRef = useRef<HTMLDivElement | null>(null);

  // Center / Fit View to all active nodes
  const handleCenterView = () => {
    if (!canvasContainerRef.current) return;
    const containerRect = canvasContainerRef.current.getBoundingClientRect();
    
    // Collect positions and dimensions of all nodes
    const nodes = [
      ...subagents.map(n => ({ x: n.x || 100, y: n.y || 100, w: 220, h: 100 })),
      ...SKILLS_LIST.map((skill, idx) => {
        const pos = skillPositions[skill.id] || { x: 3500, y: 50 + idx * 135 };
        return { x: pos.x, y: pos.y, w: 200, h: 70 };
      })
    ];
    
    if (nodes.length === 0) return;
    
    // Find bounding box
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    
    nodes.forEach(n => {
      if (n.x < minX) minX = n.x;
      if (n.x + n.w > maxX) maxX = n.x + n.w;
      if (n.y < minY) minY = n.y;
      if (n.y + n.h > maxY) maxY = n.y + n.h;
    });
    
    // Add margin padding
    const padding = 80;
    minX -= padding;
    maxX += padding;
    minY -= padding;
    maxY += padding;
    
    const contentW = maxX - minX;
    const contentH = maxY - minY;
    
    // Determine fit zoom factor
    const zoomX = containerRect.width / contentW;
    const zoomY = containerRect.height / contentH;
    const newZoom = Math.max(0.25, Math.min(1.1, Math.min(zoomX, zoomY)));
    
    // Align center
    const newPanX = (containerRect.width - contentW * newZoom) / 2 - minX * newZoom;
    const newPanY = (containerRect.height - contentH * newZoom) / 2 - minY * newZoom;
    
    setZoom(newZoom);
    setPanOffset({ x: newPanX, y: newPanY });
  };

  // Inspector panel form states
  const [inspectName, setInspectName] = useState('');
  const [inspectPrompt, setInspectPrompt] = useState('');
  const [inspectModel, setInspectModel] = useState('');
  const [inspectType, setInspectType] = useState('agent');
  const [inspectParent, setInspectParent] = useState<string | null>(null);
  const [inspectSkills, setInspectSkills] = useState<string>('');

  // New node form states
  const [showAddForm, setShowAddForm] = useState(false);
  const [addId, setAddId] = useState('');
  const [addName, setAddName] = useState('');
  const [addPrompt, setAddPrompt] = useState('');
  const [addModel, setAddModel] = useState('google/gemini-2.5-flash');
  const [addType, setAddType] = useState('agent');
  const [addParent, setAddParent] = useState('jarvis');

  // Load select node details into inspector form
  useEffect(() => {
    if (selectedNodeId) {
      const node = subagents.find(n => n.id === selectedNodeId);
      if (node) {
        setInspectName(node.name);
        setInspectPrompt(node.system_prompt);
        setInspectModel(node.model);
        setInspectType(node.agent_type || 'agent');
        setInspectParent(node.parent_id || null);
        setInspectSkills(node.skills || '');
      }
    }
  }, [selectedNodeId, subagents]);

  // Handle native Wheel Zoom (Ctrl/Scroll Zoom centering on mouse cursor)
  useEffect(() => {
    const el = canvasContainerRef.current;
    if (!el) return;
    
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = 0.06;
      let newZoom = zoom;
      if (e.deltaY < 0) {
        newZoom = Math.min(2.0, zoom + zoomFactor);
      } else {
        newZoom = Math.max(0.3, zoom - zoomFactor);
      }
      
      const rect = el.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      
      const canvasX = (mouseX - panOffset.x) / zoom;
      const canvasY = (mouseY - panOffset.y) / zoom;
      
      setPanOffset({
        x: mouseX - canvasX * newZoom,
        y: mouseY - canvasY * newZoom
      });
      setZoom(newZoom);
    };
    
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheel);
    };
  }, [zoom, panOffset]);

  // Handle Canvas drag panning and box selection
  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // left click only
    if (e.shiftKey) {
      if (canvasContainerRef.current) {
        const rect = canvasContainerRef.current.getBoundingClientRect();
        const mouseCanvasX = (e.clientX - rect.left - panOffset.x) / zoom;
        const mouseCanvasY = (e.clientY - rect.top - panOffset.y) / zoom;
        setSelectionBox({
          startX: mouseCanvasX,
          startY: mouseCanvasY,
          endX: mouseCanvasX,
          endY: mouseCanvasY
        });
      }
    } else {
      setIsPanning(true);
      setPanStart({
        x: e.clientX - panOffset.x,
        y: e.clientY - panOffset.y
      });
      setCanvasClickStart({
        x: e.clientX,
        y: e.clientY
      });
    }
  };

  // Handle Dragging nodes (both custom agent nodes and skill nodes)
  const handleMouseDown = (nodeId: string, e: React.MouseEvent, isSkill: boolean = false) => {
    e.preventDefault();
    e.stopPropagation();

    let currentSelection = [...selectedNodes];
    const isAlreadySelected = currentSelection.some(n => n.id === nodeId && n.isSkill === isSkill);

    if (e.shiftKey || e.metaKey || e.ctrlKey) {
      if (isAlreadySelected) {
        currentSelection = currentSelection.filter(n => !(n.id === nodeId && n.isSkill === isSkill));
      } else {
        currentSelection.push({ id: nodeId, isSkill });
      }
    } else {
      if (!isAlreadySelected) {
        currentSelection = [{ id: nodeId, isSkill }];
      }
    }

    setSelectedNodes(currentSelection);
    if (!isSkill) {
      setSelectedNodeId(nodeId);
    } else {
      if (!e.shiftKey && !e.metaKey && !e.ctrlKey) {
        setSelectedNodeId(null);
      }
    }

    if (canvasContainerRef.current) {
      const rect = canvasContainerRef.current.getBoundingClientRect();
      const mouseCanvasX = (e.clientX - rect.left - panOffset.x) / zoom;
      const mouseCanvasY = (e.clientY - rect.top - panOffset.y) / zoom;

      const dragNodes = currentSelection.map(sel => {
        if (sel.isSkill) {
          const skIndex = SKILLS_LIST.findIndex(s => s.id === sel.id);
          const pos = skillPositions[sel.id] || { x: 3500, y: 50 + skIndex * 135 };
          return { id: sel.id, isSkill: true, x: pos.x, y: pos.y };
        } else {
          const node = subagents.find(n => n.id === sel.id) || { x: 100, y: 100 };
          return { id: sel.id, isSkill: false, x: node.x || 100, y: node.y || 100 };
        }
      });

      if (dragNodes.length === 0 || !dragNodes.some(dn => dn.id === nodeId && dn.isSkill === isSkill)) {
        if (isSkill) {
          const skIndex = SKILLS_LIST.findIndex(s => s.id === nodeId);
          const pos = skillPositions[nodeId] || { x: 3500, y: 50 + skIndex * 135 };
          dragNodes.push({ id: nodeId, isSkill: true, x: pos.x, y: pos.y });
        } else {
          const node = subagents.find(n => n.id === nodeId) || { x: 100, y: 100 };
          dragNodes.push({ id: nodeId, isSkill: false, x: node.x || 100, y: node.y || 100 });
        }
      }

      setDraggingNode({
        mouseStartX: mouseCanvasX,
        mouseStartY: mouseCanvasY,
        nodes: dragNodes
      });
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!canvasContainerRef.current) return;
    const rect = canvasContainerRef.current.getBoundingClientRect();
    
    const canvasX = (e.clientX - rect.left - panOffset.x) / zoom;
    const canvasY = (e.clientY - rect.top - panOffset.y) / zoom;

    if (selectionBox) {
      setSelectionBox(prev => {
        if (!prev) return null;
        return {
          ...prev,
          endX: canvasX,
          endY: canvasY
        };
      });
    }

    if (draggingNode) {
      const dx = canvasX - draggingNode.mouseStartX;
      const dy = canvasY - draggingNode.mouseStartY;
      
      const skillsToUpdate = draggingNode.nodes.filter(n => n.isSkill);
      if (skillsToUpdate.length > 0) {
        setSkillPositions(prev => {
          const updated = { ...prev };
          skillsToUpdate.forEach(sk => {
            updated[sk.id] = { x: Math.round(sk.x + dx), y: Math.round(sk.y + dy) };
          });
          localStorage.setItem('jarvis_skill_positions', JSON.stringify(updated));
          return updated;
        });
      }

      const subagentsToUpdate = draggingNode.nodes.filter(n => !n.isSkill);
      if (subagentsToUpdate.length > 0) {
        setSubagents(subagents.map(n => {
          const match = subagentsToUpdate.find(dn => dn.id === n.id);
          if (match) {
            return { ...n, x: Math.round(match.x + dx), y: Math.round(match.y + dy) };
          }
          return n;
        }));
      }
    }

    if (connectingFrom) {
      setCursorPos({ x: canvasX, y: canvasY });
    }

    if (isPanning) {
      setPanOffset({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      });
    }
  };

  const handleMouseUp = async (e: React.MouseEvent) => {
    if (selectionBox) {
      const xMin = Math.min(selectionBox.startX, selectionBox.endX);
      const xMax = Math.max(selectionBox.startX, selectionBox.endX);
      const yMin = Math.min(selectionBox.startY, selectionBox.endY);
      const yMax = Math.max(selectionBox.startY, selectionBox.endY);

      const intersects = (nodeX: number, nodeY: number, nodeW: number, nodeH: number) => {
        return !(nodeX + nodeW < xMin || nodeX > xMax || nodeY + nodeH < yMin || nodeY > yMax);
      };

      const newlySelected: Array<{ id: string; isSkill: boolean }> = [];
      subagents.forEach(n => {
        const x = n.x || 100;
        const y = n.y || 100;
        if (intersects(x, y, 220, 100)) {
          newlySelected.push({ id: n.id, isSkill: false });
        }
      });
      SKILLS_LIST.forEach((skill, skIndex) => {
        const pos = skillPositions[skill.id] || { x: 3500, y: 50 + skIndex * 135 };
        if (intersects(pos.x, pos.y, 200, 70)) {
          newlySelected.push({ id: skill.id, isSkill: true });
        }
      });

      setSelectedNodes(newlySelected);
      const firstSubagent = newlySelected.find(s => !s.isSkill);
      setSelectedNodeId(firstSubagent ? firstSubagent.id : null);
      setSelectionBox(null);
    }

    if (isPanning) {
      setIsPanning(false);
      if (canvasClickStart) {
        const dx = Math.abs(e.clientX - canvasClickStart.x);
        const dy = Math.abs(e.clientY - canvasClickStart.y);
        if (dx < 3 && dy < 3) {
          setSelectedNodes([]);
          setSelectedNodeId(null);
        }
        setCanvasClickStart(null);
      }
    }

    if (draggingNode) {
      const subagentNodesToSave = subagents.filter(n => 
        draggingNode.nodes.some(dn => dn.id === n.id && !dn.isSkill)
      );
      if (subagentNodesToSave.length > 0) {
        try {
          await fetch('/api/subagents/positions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              positions: subagentNodesToSave.map(node => ({ id: node.id, x: node.x, y: node.y }))
            })
          });
        } catch (err) {
          console.error('Error saving node positions:', err);
        }
      }
      setDraggingNode(null);
    }
  };

  // Connection math helper
  const getBezierPath = (x1: number, y1: number, x2: number, y2: number) => {
    const dx = Math.max(80, Math.abs(x2 - x1) * 0.45);
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  };

  // Connect actions
  const handleConnectOutput = (nodeId: string, type: 'orchestrator' | 'agent', e: React.MouseEvent) => {
    e.stopPropagation();
    const node = subagents.find(n => n.id === nodeId);
    if (node) {
      const portX = (node.x || 100) + 220;
      const portY = (node.y || 100) + 50;
      setConnectingFrom({ id: nodeId, type, x: portX, y: portY });
      setCursorPos({ x: portX, y: portY });
    }
  };

  const handleConnectInput = async (targetId: string, targetType: 'agent' | 'skill') => {
    if (!connectingFrom) return;
    const sourceId = connectingFrom.id;
    const sourceType = connectingFrom.type;

    if (sourceId === targetId) {
      setConnectingFrom(null);
      return;
    }

    if (sourceType === 'orchestrator' && targetType === 'agent') {
      // Connect parent orchestrator to sub-orchestrator or sub-agent
      const targetAgent = subagents.find(n => n.id === targetId);
      if (targetAgent) {
        const updatedAgent = {
          ...targetAgent,
          parent_id: sourceId
        };
        await saveAgentToServer(updatedAgent);
      }
    } else if ((sourceType === 'agent' || (sourceType === 'orchestrator' && sourceId !== 'jarvis')) && targetType === 'skill') {
      // Connect sub-agent or sub-orchestrator to skill
      const agent = subagents.find(n => n.id === sourceId);
      if (agent) {
        const currentSkills = agent.skills ? agent.skills.split(',').map((s: string) => s.trim()) : [];
        if (!currentSkills.includes(targetId)) {
          currentSkills.push(targetId);
          const updatedAgent = {
            ...agent,
            skills: currentSkills.filter(Boolean).join(',')
          };
          await saveAgentToServer(updatedAgent);
        }
      }
    }

    setConnectingFrom(null);
  };

  const saveAgentToServer = async (agent: any) => {
    try {
      const res = await fetch('/api/subagents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: agent.id,
          name: agent.name,
          system_prompt: agent.system_prompt,
          model: agent.model,
          agent_type: agent.agent_type || 'agent',
          parent_id: agent.parent_id || null,
          skills: agent.skills || '',
          x: agent.x || 100,
          y: agent.y || 100
        })
      });
      if (res.ok) {
        fetchSubagents();
      }
    } catch (err) {
      console.error('Error saving agent config:', err);
    }
  };

  // Disconnect Handlers
  const disconnectParent = async (agentId: string) => {
    const agent = subagents.find(n => n.id === agentId);
    if (agent) {
      const updated = { ...agent, parent_id: null };
      await saveAgentToServer(updated);
    }
  };

  const disconnectSkill = async (agentId: string, skillId: string) => {
    const agent = subagents.find(n => n.id === agentId);
    if (agent) {
      const currentSkills = agent.skills ? agent.skills.split(',').map((s: string) => s.trim()) : [];
      const updated = {
        ...agent,
        skills: currentSkills.filter((s: string) => s !== skillId).join(',')
      };
      await saveAgentToServer(updated);
    }
  };

  // Inspector CRUD updates
  const handleUpdateInspector = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedNodeId) return;
    const node = subagents.find(n => n.id === selectedNodeId);
    if (node) {
      const updated = {
        ...node,
        name: inspectName,
        system_prompt: inspectPrompt,
        model: inspectModel,
        agent_type: inspectType,
        parent_id: inspectParent,
        skills: inspectSkills
      };
      await saveAgentToServer(updated);
      setSelectedNodeId(null);
    }
  };

  const handleDeleteInspector = async () => {
    if (!selectedNodeId) return;
    if (confirm(`Delete node ${selectedNodeId}?`)) {
      try {
        const res = await fetch(`/api/subagents/${selectedNodeId}`, { method: 'DELETE' });
        if (res.ok) {
          fetchSubagents();
          setSelectedNodes(prev => prev.filter(sn => sn.id !== selectedNodeId));
          setSelectedNodeId(null);
        }
      } catch (err) {
        console.error('Error deleting node:', err);
      }
    }
  };

  // Add Node handler
  const handleAddNode = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanId = addId.replace(/[^a-zA-Z0-9_-]/g, '').toLowerCase();
    if (!cleanId) return;
    if (subagents.some(n => n.id === cleanId) || cleanId === 'jarvis') {
      alert('A node with this ID already exists!');
      return;
    }

    const newNode = {
      id: cleanId,
      name: addName,
      system_prompt: addPrompt,
      model: addModel,
      agent_type: addType,
      parent_id: addParent || null,
      skills: '',
      x: 350 + Math.floor(Math.random() * 200),
      y: 200 + Math.floor(Math.random() * 200)
    };

    await saveAgentToServer(newNode);
    setAddId('');
    setAddName('');
    setAddPrompt('');
    setShowAddForm(false);
  };

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%', overflow: 'hidden', position: 'relative' }} className="glass-panel">
      {/* Node Canvas Area */}
      <div 
        ref={canvasContainerRef}
        style={{
          flex: 1,
          height: '100%',
          overflow: 'hidden',
          backgroundColor: '#020617',
          backgroundImage: 'radial-gradient(rgba(255, 255, 255, 0.05) 1.2px, transparent 0)',
          backgroundSize: `${24 * zoom}px ${24 * zoom}px`,
          backgroundPosition: `${panOffset.x}px ${panOffset.y}px`,
          position: 'relative',
          cursor: isPanning ? 'grabbing' : connectingFrom ? 'crosshair' : 'default',
          userSelect: 'none'
        }}
        onMouseDown={handleCanvasMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        {/* Inner zoomable/pannable viewport container */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoom})`,
            transformOrigin: '0 0',
            pointerEvents: 'none'
          }}
        >
          {/* SVG connection overlay */}
          <svg 
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '1px',
              height: '1px',
              overflow: 'visible',
              pointerEvents: 'none',
              zIndex: 1
            }}
          >
            {/* Render connection lines */}
            {/* Main Vexa connections */}
            {subagents.map(n => {
              if (n.parent_id === 'jarvis') {
                const jarvisNode = subagents.find(p => p.id === 'jarvis') || { x: 100, y: 200 };
                const startX = (jarvisNode.x || 100) + 220;
                const startY = (jarvisNode.y || 200) + 50;
                const endX = n.x || 100;
                const endY = (n.y || 100) + 50;
                const path = getBezierPath(startX, startY, endX, endY);
                const midX = (startX + endX) / 2;
                const midY = (startY + endY) / 2;
                return (
                  <g key={`jarvis-${n.id}`}>
                    <path d={path} stroke="var(--accent-cyan)" strokeWidth="2.5" fill="none" opacity="0.6" />
                    {/* Disconnect handle */}
                    <circle 
                      cx={midX} 
                      cy={midY} 
                      r="8" 
                      fill="#ef4444" 
                      style={{ pointerEvents: 'auto', cursor: 'pointer' }} 
                      onClick={() => disconnectParent(n.id)}
                    >
                      <title>Disconnect</title>
                    </circle>
                    <text x={midX} y={midY + 3} textAnchor="middle" fill="#fff" fontSize="8px" fontWeight="bold" style={{ pointerEvents: 'none' }}>×</text>
                  </g>
                );
              }
              return null;
            })}

            {/* Child Connections between custom nodes */}
            {subagents.map(n => {
              if (n.parent_id && n.parent_id !== 'jarvis') {
                const parent = subagents.find(p => p.id === n.parent_id);
                if (parent) {
                  const startX = (parent.x || 100) + 220;
                  const startY = (parent.y || 100) + 50;
                  const endX = n.x || 100;
                  const endY = (n.y || 100) + 50;
                  const path = getBezierPath(startX, startY, endX, endY);
                  const midX = (startX + endX) / 2;
                  const midY = (startY + endY) / 2;
                  return (
                    <g key={`parent-${parent.id}-${n.id}`}>
                      <path d={path} stroke="var(--accent-cyan)" strokeWidth="2.5" fill="none" opacity="0.6" />
                      <circle 
                        cx={midX} 
                        cy={midY} 
                        r="8" 
                        fill="#ef4444" 
                        style={{ pointerEvents: 'auto', cursor: 'pointer' }} 
                        onClick={() => disconnectParent(n.id)}
                      >
                        <title>Disconnect</title>
                      </circle>
                      <text x={midX} y={midY + 3} textAnchor="middle" fill="#fff" fontSize="8px" fontWeight="bold" style={{ pointerEvents: 'none' }}>×</text>
                    </g>
                  );
                }
              }
              return null;
            })}

            {/* Agent -> Skill Connections */}
            {subagents.map(n => {
              if (n.skills) {
                const skillIds = n.skills.split(',').map((s: string) => s.trim());
                return skillIds.map((skId: string) => {
                  const skIndex = SKILLS_LIST.findIndex(s => s.id === skId);
                  if (skIndex !== -1) {
                    const startX = (n.x || 100) + 220;
                    const startY = (n.y || 100) + 50;
                    const skillPos = skillPositions[skId] || { x: 3500, y: 50 + skIndex * 135 };
                    const endX = skillPos.x;
                    const endY = skillPos.y + 35;
                    const path = getBezierPath(startX, startY, endX, endY);
                    const midX = (startX + endX) / 2;
                    const midY = (startY + endY) / 2;
                    return (
                      <g key={`skill-${n.id}-${skId}`}>
                        <path d={path} stroke="#10b981" strokeWidth="2.5" fill="none" opacity="0.6" />
                        <circle 
                          cx={midX} 
                          cy={midY} 
                          r="8" 
                          fill="#ef4444" 
                          style={{ pointerEvents: 'auto', cursor: 'pointer' }} 
                          onClick={() => disconnectSkill(n.id, skId)}
                        >
                          <title>Remove skill</title>
                        </circle>
                        <text x={midX} y={midY + 3} textAnchor="middle" fill="#fff" fontSize="8px" fontWeight="bold" style={{ pointerEvents: 'none' }}>×</text>
                      </g>
                    );
                  }
                  return null;
                });
              }
              return null;
            })}

            {/* Render active connection line preview */}
            {connectingFrom && (
              <path 
                d={getBezierPath(connectingFrom.x, connectingFrom.y, cursorPos.x, cursorPos.y)} 
                stroke="#ffd200" 
                strokeWidth="2.5" 
                strokeDasharray="5,5" 
                fill="none" 
              />
            )}

            {selectionBox && (
              <rect
                x={Math.min(selectionBox.startX, selectionBox.endX)}
                y={Math.min(selectionBox.startY, selectionBox.endY)}
                width={Math.abs(selectionBox.endX - selectionBox.startX)}
                height={Math.abs(selectionBox.endY - selectionBox.startY)}
                fill="rgba(0, 240, 255, 0.08)"
                stroke="var(--accent-cyan)"
                strokeWidth="1.5"
                strokeDasharray="4,3"
              />
            )}
          </svg>

          {/* 2. Custom nodes (Orchestrators, Sub-orchestrators & Sub-agents) */}
          {subagents.map(node => {
            const isVexaMain = node.id === 'jarvis';
            const isOrch = node.agent_type === 'orchestrator' || node.agent_type === 'sub-orchestrator';
            const isSelected = selectedNodes.some(sn => sn.id === node.id && !sn.isSkill);
            const borderColor = isSelected ? '#ffd200' : (isVexaMain ? 'var(--accent-cyan)' : (isOrch ? '#8b5cf6' : 'var(--accent-orange)'));
            const glowColor = isSelected ? 'rgba(255, 210, 0, 0.45)' : (isVexaMain ? 'rgba(0, 240, 255, 0.2)' : (isOrch ? 'rgba(139, 92, 246, 0.25)' : 'rgba(255, 159, 0, 0.2)'));
            const borderWidth = isSelected ? '2px' : '1.5px';
            const glowWidth = isSelected ? '18px' : '12px';
            
            return (
              <div
                key={node.id}
                style={{
                  position: 'absolute',
                  left: `${node.x || 100}px`,
                  top: `${node.y || 100}px`,
                  width: '220px',
                  height: '100px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(12, 16, 32, 0.85)',
                  border: `${borderWidth} solid ${borderColor}`,
                  boxShadow: `0 0 ${glowWidth} ${glowColor}`,
                  zIndex: 2,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                  cursor: 'grab',
                  pointerEvents: 'auto'
                }}
                onMouseDown={(e) => handleMouseDown(node.id, e, false)}
              >
                {/* Header block (Draggable) */}
                <div 
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    padding: '10px 10px 4px 10px',
                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                    pointerEvents: 'none'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                    {isOrch ? <Layers size={14} style={{ color: '#8b5cf6', flexShrink: 0 }} /> : <GitBranch size={14} style={{ color: 'var(--accent-orange)', flexShrink: 0 }} />}
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {node.name}
                    </span>
                  </div>
                  <span style={{ fontSize: '0.55rem', color: 'var(--text-dim)', flexShrink: 0 }}>
                    {node.model.split('/').pop()}
                  </span>
                </div>

                {/* Subtitle */}
                <div style={{ flex: 1, padding: '4px 10px', display: 'flex', alignItems: 'center', pointerEvents: 'none' }}>
                  <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)', lineHeight: '1.2' }}>
                    {node.id === 'jarvis' ? 'Vexa Main Orchestrator' : (node.agent_type === 'sub-orchestrator' ? 'Sub-orchestrator' : 'Sub-agent')} / ID: {node.id}
                  </span>
                </div>

                {/* Left input handle port */}
                {!isVexaMain && (
                  <div 
                    style={{
                      position: 'absolute',
                      left: '-6px',
                      top: '44px',
                      width: '12px',
                      height: '12px',
                      borderRadius: '50%',
                      backgroundColor: '#9ca3af',
                      border: '2px solid #030712',
                      cursor: 'pointer',
                      boxShadow: '0 0 5px rgba(255,255,255,0.2)',
                      pointerEvents: 'auto'
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleConnectInput(node.id, 'agent');
                    }}
                    title="Connect to parent"
                  />
                )}

                {/* Right output handle port */}
                <div 
                  style={{
                    position: 'absolute',
                    right: '-6px',
                    top: '44px',
                    width: '12px',
                    height: '12px',
                    borderRadius: '50%',
                    backgroundColor: borderColor,
                    border: '2px solid #030712',
                    cursor: 'pointer',
                    boxShadow: `0 0 8px ${borderColor}`,
                    pointerEvents: 'auto'
                  }}
                  onClick={(e) => handleConnectOutput(node.id, isOrch ? 'orchestrator' : 'agent', e)}
                  title={isOrch ? "Link to agents" : "Connect skills"}
                />
              </div>
            );
          })}

          {/* 3. Static global Skills nodes (Column 4) */}
          {SKILLS_LIST.map((skill, skIndex) => {
            const skillPos = skillPositions[skill.id] || { x: 3500, y: 50 + skIndex * 135 };
            const isSelected = selectedNodes.some(sn => sn.id === skill.id && sn.isSkill);
            const borderColor = isSelected ? '#ffd200' : '#10b981';
            const glowColor = isSelected ? 'rgba(255, 210, 0, 0.45)' : 'rgba(16, 185, 129, 0.12)';
            const borderWidth = isSelected ? '2px' : '1.5px';
            const glowWidth = isSelected ? '18px' : '10px';

            return (
              <div
                key={skill.id}
                style={{
                  position: 'absolute',
                  left: `${skillPos.x}px`,
                  top: `${skillPos.y}px`,
                  width: '200px',
                  height: '70px',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(10, 24, 20, 0.85)',
                  border: `${borderWidth} solid ${borderColor}`,
                  boxShadow: `0 0 ${glowWidth} ${glowColor}`,
                  padding: '10px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  zIndex: 2,
                  pointerEvents: 'auto',
                  cursor: 'grab',
                  transition: 'border-color 0.2s, box-shadow 0.2s'
                }}
                onMouseDown={(e) => handleMouseDown(skill.id, e, true)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', pointerEvents: 'none' }}>
                  <Wrench size={14} style={{ color: '#10b981' }} />
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#fff' }}>{skill.name}</span>
                </div>
                <span style={{ fontSize: '0.55rem', color: 'var(--text-dim)', marginTop: '4px', display: 'block', pointerEvents: 'none' }}>{skill.desc}</span>

                {/* Left input handle port */}
                <div 
                  style={{
                    position: 'absolute',
                    left: '-6px',
                    top: '29px',
                    width: '12px',
                    height: '12px',
                    borderRadius: '50%',
                    backgroundColor: '#10b981',
                    border: '2px solid #030712',
                    cursor: 'pointer',
                    boxShadow: '0 0 6px #10b981',
                    pointerEvents: 'auto'
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleConnectInput(skill.id, 'skill');
                  }}
                  title="Connect skill to agent"
                />
              </div>
            );
          })}
        </div>

        {/* Zoom / Pan Controls (Static overlay, zIndex: 10) */}
        <div 
          style={{
            position: 'absolute',
            right: '20px',
            bottom: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            zIndex: 10,
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            backdropFilter: 'blur(8px)',
            padding: '6px',
            borderRadius: '8px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            boxShadow: '0 4px 15px rgba(0, 0, 0, 0.3)',
            pointerEvents: 'auto'
          }}
        >
          <button 
            onClick={() => setZoom(z => Math.min(2.0, z + 0.1))} 
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              color: '#fff',
              fontSize: '18px',
              fontWeight: 'bold',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s'
            }}
            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)'}
            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
            title="Zoom In"
          >
            +
          </button>
          <span style={{ fontSize: '0.62rem', color: '#fff', fontWeight: 600, textAlign: 'center', margin: '2px 0' }}>
            {Math.round(zoom * 100)}%
          </span>
          <button 
            onClick={() => setZoom(z => Math.max(0.3, z - 0.1))} 
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              color: '#fff',
              fontSize: '18px',
              fontWeight: 'bold',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s'
            }}
            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)'}
            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
            title="Zoom Out"
          >
            -
          </button>
          <button 
            onClick={handleCenterView} 
            style={{
              borderRadius: '4px',
              border: 'none',
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              color: '#10b981',
              fontSize: '9px',
              fontWeight: 700,
              cursor: 'pointer',
              padding: '4px 6px',
              textAlign: 'center',
              transition: 'background-color 0.2s',
              marginBottom: '4px'
            }}
            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'rgba(16, 185, 129, 0.3)'}
            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'rgba(16, 185, 129, 0.15)'}
            title="Fit to Screen"
          >
            CENTER
          </button>
          <button 
            onClick={() => {
              setZoom(1.0);
              setPanOffset({ x: 0, y: 0 });
            }} 
            style={{
              borderRadius: '4px',
              border: 'none',
              backgroundColor: 'rgba(0, 240, 255, 0.1)',
              color: 'var(--accent-cyan)',
              fontSize: '9px',
              fontWeight: 700,
              cursor: 'pointer',
              padding: '4px 6px',
              textAlign: 'center',
              transition: 'background-color 0.2s'
            }}
            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'rgba(0, 240, 255, 0.2)'}
            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'rgba(0, 240, 255, 0.1)'}
            title="Reset View"
          >
            RESET
          </button>
        </div>
      </div>

      {/* Floating Canvas Controls */}
      <div 
        style={{
          position: 'absolute',
          left: '20px',
          bottom: '20px',
          display: 'flex',
          gap: '10px',
          zIndex: 10
        }}
      >
        <button 
          onClick={() => setShowAddForm(true)} 
          className="btn-primary" 
          style={{ boxShadow: '0 4px 15px rgba(0, 240, 255, 0.2)' }}
        >
          <Plus size={16} />
          <span>Add node</span>
        </button>
      </div>

      {/* Node Inspector Sidebar Panel */}
      {selectedNodeId && (
        <div 
          style={{
            width: '320px',
            height: '100%',
            backgroundColor: 'rgba(8, 12, 24, 0.96)',
            borderLeft: '1px solid rgba(255, 255, 255, 0.05)',
            boxShadow: '-10px 0 30px rgba(0,0,0,0.5)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 20,
            position: 'relative'
          }}
          className="glass-panel animate-fade-in"
        >
          {/* Header */}
          <div style={{ padding: '16px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }} className="glow-text-cyan">NODE INSPECTOR</span>
            <button 
              onClick={() => setSelectedNodeId(null)}
              style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
            >
              ×
            </button>
          </div>

          {/* Form Content */}
          <form onSubmit={handleUpdateInspector} style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>NODE ID</label>
              <input type="text" value={selectedNodeId} disabled className="form-input" style={{ opacity: 0.6, cursor: 'not-allowed' }} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>NAME</label>
              <input type="text" value={inspectName} onChange={e => setInspectName(e.target.value)} className="form-input" required />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>NODE TYPE</label>
              <select value={inspectType} onChange={e => setInspectType(e.target.value)} className="form-input">
                <option value="agent">Sub-agent (Executor)</option>
                <option value="sub-orchestrator">Sub-orchestrator (Coordinator)</option>
                <option value="orchestrator">Orchestrator</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>PARENT NODE</label>
              <select 
                value={inspectParent || ''} 
                onChange={e => setInspectParent(e.target.value || null)} 
                className="form-input"
              >
                <option value="">None (Root Node)</option>
                <option value="jarvis">Vexa Main</option>
                {subagents
                  .filter(n => n.id !== selectedNodeId && n.id !== 'jarvis' && (n.agent_type === 'orchestrator' || n.agent_type === 'sub-orchestrator'))
                  .map(n => <option key={n.id} value={n.id}>{n.name}</option>)
                }
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>INSTRUCTIONS (SYSTEM PROMPT)</label>
              <textarea value={inspectPrompt} onChange={e => setInspectPrompt(e.target.value)} className="form-input" rows={6} required />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>AI MODEL</label>
              <input value={inspectModel} onChange={e => setInspectModel(e.target.value)} className="form-input" list="network-model-options" placeholder="qwen3:8b" />
              <datalist id="network-model-options">
                {models.map(model => <option key={model.id} value={model.id}>{model.name || model.id}</option>)}
              </datalist>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>SKILLS</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '150px', overflowY: 'auto', padding: '8px', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
                {SKILLS_LIST.map(skill => {
                  const currentSkills = inspectSkills ? inspectSkills.split(',').map(s => s.trim()).filter(Boolean) : [];
                  const hasSkill = currentSkills.includes(skill.id);
                  return (
                    <label key={skill.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.75rem', color: '#fff' }}>
                      <input 
                        type="checkbox" 
                        checked={hasSkill}
                        onChange={(e) => {
                          let newSkills = [...currentSkills];
                          if (e.target.checked) {
                            if (!newSkills.includes(skill.id)) newSkills.push(skill.id);
                          } else {
                            newSkills = newSkills.filter(s => s !== skill.id);
                          }
                          setInspectSkills(newSkills.join(','));
                        }}
                        style={{ accentColor: 'var(--accent-cyan)', cursor: 'pointer' }}
                      />
                      <span style={{ display: 'flex', flexDirection: 'column' }}>
                        <span>{skill.name}</span>
                        <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>{skill.desc}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>

            <button type="submit" className="btn-primary" style={{ marginTop: '10px' }}>
              <CheckCircle2 size={16} />
              <span>Save Node</span>
            </button>
            
            <button 
              type="button" 
              onClick={handleDeleteInspector} 
              className="btn-secondary" 
              style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }}
            >
              <Trash2 size={16} />
              <span>Delete Node</span>
            </button>
          </form>
        </div>
      )}

      {/* Add Node Modal Dialog */}
      {showAddForm && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100
        }}>
          <div style={{
            width: '450px',
            backgroundColor: 'rgba(10, 15, 30, 0.95)',
            border: '1px solid rgba(0, 240, 255, 0.2)',
            borderRadius: '12px',
            padding: '24px',
            boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px'
          }} className="glass-panel">
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }} className="glow-text-cyan">CREATE NEW NODE</h3>
            
            <form onSubmit={handleAddNode} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Unique ID (latin)</label>
                <input type="text" value={addId} onChange={e => setAddId(e.target.value)} placeholder="e.g. sports_betting_agent" className="form-input" required />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Node name</label>
                <input type="text" value={addName} onChange={e => setAddName(e.target.value)} placeholder="e.g. Sports Sub-agent" className="form-input" required />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Node Type</label>
                <select value={addType} onChange={e => setAddType(e.target.value)} className="form-input">
                  <option value="agent">Sub-agent (Executor)</option>
                  <option value="sub-orchestrator">Sub-orchestrator (Coordinator)</option>
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Parent Node</label>
                <select value={addParent} onChange={e => setAddParent(e.target.value)} className="form-input">
                  <option value="jarvis">Vexa Main</option>
                  {subagents
                    .filter(n => n.id !== 'jarvis' && (n.agent_type === 'orchestrator' || n.agent_type === 'sub-orchestrator'))
                    .map(n => <option key={n.id} value={n.id}>{n.name}</option>)
                  }
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Instructions</label>
                <textarea value={addPrompt} onChange={e => setAddPrompt(e.target.value)} placeholder="Instructions for work..." className="form-input" rows={4} required />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>AI Model</label>
                <select value={addModel} onChange={e => setAddModel(e.target.value)} className="form-input">
                  {models && models.length > 0 ? (
                    models.map(m => (
                      <option key={m.id} value={m.id}>{m.name || m.id}</option>
                    ))
                  ) : (
                    <>
                      <option value="google/gemini-2.5-flash">Gemini 2.5 Flash</option>
                      <option value="google/gemini-2.5-pro">Gemini 2.5 Pro</option>
                      <option value="deepseek/deepseek-v4-flash">DeepSeek V4 Flash</option>
                    </>
                  )}
                </select>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button type="submit" className="btn-primary" style={{ flex: 1 }}>Create</button>
                <button type="button" onClick={() => setShowAddForm(false)} className="btn-secondary" style={{ flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', color: '#fff' }}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
