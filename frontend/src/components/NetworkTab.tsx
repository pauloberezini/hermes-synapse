import React, { useState, useEffect, useRef } from 'react';
import { 
  Layers, 
  Bot, 
  Wrench, 
  Cpu,
  Rss
} from 'lucide-react';
import { OrchestratorLayerBar, type BreadcrumbItem } from './architecture/OrchestratorLayerBar';
import { NodePalette } from './architecture/NodePalette';
import { NodeInspectorDrawer } from './architecture/NodeInspectorDrawer';
import { LayerSandboxDrawer } from './architecture/LayerSandboxDrawer';

export const SKILLS_LIST = [
  { id: 'web_search', name: 'Web Search', desc: 'DuckDuckGo search, weather, RSS news', color: 'var(--accent-cyan, #06b6d4)' },
  { id: 'read_rss_node_feed', name: 'RSS News Ray', desc: 'Read news from autonomous RSS nodes', color: '#ea580c' },
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
  models: Array<{ id: string; name: string }>;
}

export function NetworkTab({ 
  subagents, 
  setSubagents, 
  fetchSubagents,
  models
}: NetworkTabProps) {
  // Layer & Navigation states
  const [viewMode, setViewMode] = useState<'layer' | 'mesh'>('layer');
  const [activeOrchestratorId, setActiveOrchestratorId] = useState<string>('jarvis');
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([
    { id: 'jarvis', name: 'Master Orchestrator' }
  ]);
  const [isSandboxOpen, setIsSandboxOpen] = useState(false);

  // RSS Nodes State
  const [rssNodes, setRssNodes] = useState<any[]>([]);

  const fetchRssNodes = async () => {
    try {
      const res = await fetch('/api/rss/nodes');
      if (res.ok) {
        const data = await res.json();
        setRssNodes(data);
      }
    } catch (e) {
      console.error('Error fetching RSS nodes:', e);
    }
  };

  useEffect(() => {
    fetchRssNodes();
  }, []);

  // Selection & Inspector states
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectionBox, setSelectionBox] = useState<{ startX: number; startY: number; endX: number; endY: number } | null>(null);
  const [canvasClickStart, setCanvasClickStart] = useState<{ x: number; y: number } | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<{ id: string; type: 'orchestrator' | 'agent' | 'rss_node'; x: number; y: number } | null>(null);
  const [cursorPos, setCursorPos] = useState({ x: 0, y: 0 });
  const [draggingNode, setDraggingNode] = useState<{
    mouseStartX: number;
    mouseStartY: number;
    nodes: Array<{ id: string; isSkill: boolean; isRss?: boolean; x: number; y: number }>;
  } | null>(null);

  // Skill Positions state (saves/loads from localStorage for persistence)
  const [skillPositions, setSkillPositions] = useState<Record<string, { x: number; y: number }>>(() => {
    const saved = localStorage.getItem('jarvis_skill_positions');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        let hasExtremeOffset = false;
        Object.values(parsed).forEach((v: any) => {
          if (v && typeof v.x === 'number' && v.x >= 2500) hasExtremeOffset = true;
        });
        if (!hasExtremeOffset) return parsed;
      } catch (e) {}
    }
    const defaults: Record<string, { x: number; y: number }> = {};
    SKILLS_LIST.forEach((skill, skIndex) => {
      defaults[skill.id] = { x: 1050, y: 50 + skIndex * 120 };
    });
    return defaults;
  });

  // Zoom & Pan states
  const [zoom, setZoom] = useState(1.0);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  const canvasContainerRef = useRef<HTMLDivElement | null>(null);

  // Extract list of Orchestrators across the system
  const orchestrators = [
    { id: 'jarvis', name: 'SYNAPSE' },
    ...subagents
      .filter(n => n.agent_type === 'orchestrator' || n.id.includes('orchestrator') || n.id.includes('trader'))
      .map(n => ({ id: n.id, name: n.name }))
  ].filter((v, i, a) => a.findIndex(t => t.id === v.id) === i);

  const activeOrchestratorNode = subagents.find(n => n.id === activeOrchestratorId) || {
    id: 'jarvis',
    name: 'SYNAPSE',
    model: 'google/gemini-2.5-flash',
    system_prompt: 'You are SYNAPSE, the Master Orchestrator.'
  };

  // Filter nodes visible on current canvas:
  // In Layer mode: show active orchestrator node + direct children (parent_id === activeOrchestratorId) + skills attached to layer
  // In Mesh mode: show all subagents & skills
  const visibleSubagentNodes = subagents.filter(node => {
    if (viewMode === 'mesh') return true;
    if (node.id === activeOrchestratorId) return true;
    if (node.parent_id === activeOrchestratorId) return true;
    if (!node.parent_id && activeOrchestratorId === 'jarvis') return true;
    return false;
  });

  // Center / Fit View to visible nodes
  const handleCenterView = () => {
    if (!canvasContainerRef.current) return;
    const containerRect = canvasContainerRef.current.getBoundingClientRect();
    
    const nodes = [
      ...visibleSubagentNodes.map(n => ({ x: n.x || 100, y: n.y || 100, w: 230, h: 100 })),
      ...SKILLS_LIST.map((skill, idx) => {
        const pos = skillPositions[skill.id] || { x: 1050, y: 50 + idx * 120 };
        return { x: pos.x, y: pos.y, w: 200, h: 70 };
      })
    ];
    
    if (nodes.length === 0) return;
    
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    
    nodes.forEach(n => {
      if (n.x < minX) minX = n.x;
      if (n.x + n.w > maxX) maxX = n.x + n.w;
      if (n.y < minY) minY = n.y;
      if (n.y + n.h > maxY) maxY = n.y + n.h;
    });
    
    const padding = 80;
    minX -= padding;
    maxX += padding;
    minY -= padding;
    maxY += padding;
    
    const contentW = maxX - minX;
    const contentH = maxY - minY;
    
    const zoomX = containerRect.width / contentW;
    const zoomY = containerRect.height / contentH;
    const newZoom = Math.max(0.25, Math.min(1.1, Math.min(zoomX, zoomY)));
    
    const newPanX = (containerRect.width - contentW * newZoom) / 2 - minX * newZoom;
    const newPanY = (containerRect.height - contentH * newZoom) / 2 - minY * newZoom;
    
    setZoom(newZoom);
    setPanOffset({ x: newPanX, y: newPanY });
  };

  const initialCenteredRef = useRef(false);
  useEffect(() => {
    if (subagents.length > 0 && !initialCenteredRef.current) {
      initialCenteredRef.current = true;
      const timer = setTimeout(() => handleCenterView(), 100);
      return () => clearTimeout(timer);
    }
  }, [subagents.length]);

  // Handle Wheel Zoom centering on mouse
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

  // Navigate Layer Breadcrumbs
  const handleNavigateBreadcrumb = (index: number) => {
    const target = breadcrumbs[index];
    if (target) {
      setActiveOrchestratorId(target.id);
      setBreadcrumbs(breadcrumbs.slice(0, index + 1));
    }
  };

  // Drill down into Sub-Orchestrator
  const handleDrillDownOrchestrator = (node: any) => {
    if (node.id === activeOrchestratorId) return;
    setActiveOrchestratorId(node.id);
    if (!breadcrumbs.some(b => b.id === node.id)) {
      setBreadcrumbs([...breadcrumbs, { id: node.id, name: node.name }]);
    }
  };

  // Save single agent or RSS node to server
  const saveAgentToServer = async (updatedNode: any) => {
    if (updatedNode.isRssNode || rssNodes.some(n => n.id === updatedNode.id)) {
      try {
        await fetch(`/api/rss/nodes/${updatedNode.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updatedNode)
        });
        await fetchRssNodes();
      } catch (err) {
        console.error('Error saving RSS node config:', err);
      }
      return;
    }

    try {
      const res = await fetch('/api/subagents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedNode)
      });
      if (res.ok) {
        fetchSubagents();
      }
    } catch (err) {
      console.error('Error saving agent config:', err);
    }
  };

  // Delete node
  const handleDeleteNode = async (nodeId: string) => {
    if (nodeId === 'jarvis') {
      alert('Cannot delete SYNAPSE Master Orchestrator!');
      return;
    }
    if (rssNodes.some(n => n.id === nodeId)) {
      if (confirm(`Delete RSS node "${nodeId}"?`)) {
        try {
          await fetch(`/api/rss/nodes/${nodeId}`, { method: 'DELETE' });
          await fetchRssNodes();
          setSelectedNodeId(null);
        } catch (err) {
          console.error('Error deleting RSS node:', err);
        }
      }
      return;
    }
    if (confirm(`Delete node "${nodeId}"?`)) {
      try {
        const res = await fetch(`/api/subagents/${nodeId}`, { method: 'DELETE' });
        if (res.ok) {
          fetchSubagents();
          setSelectedNodeId(null);
        }
      } catch (err) {
        console.error('Error deleting node:', err);
      }
    }
  };

  // Add Subagent or RSS Node from NodePalette
  const handleAddSubagent = async (type: 'orchestrator' | 'agent' | 'rss_node', archetype?: string) => {
    if (type === 'rss_node') {
      const randomSuffix = Math.floor(Math.random() * 899 + 100);
      const newId = `rss_node_${randomSuffix}`;
      const newRssNode = {
        id: newId,
        name: `RSS Feed Node #${randomSuffix}`,
        feed_urls: 'https://habr.com/ru/rss/news/',
        fetch_interval_minutes: 15,
        output_limit: 10,
        date_filter_days: 0,
        keywords_filter: '',
        is_active: 1,
        x: 350 + Math.floor(Math.random() * 150),
        y: 150 + Math.floor(Math.random() * 150),
        connected_agents: ''
      };
      await fetch('/api/rss/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newRssNode)
      });
      await fetchRssNodes();
      setSelectedNodeId(newId);
      return;
    }

    const randomSuffix = Math.floor(Math.random() * 899 + 100);
    const newId = type === 'orchestrator' ? `orch_${randomSuffix}` : `agent_${archetype || 'worker'}_${randomSuffix}`;
    const nameMap: Record<string, string> = {
      research: 'Research Agent',
      code: 'Code Agent',
      analyst: 'Analyst Agent',
      custom: 'Custom Agent Worker',
      orchestrator: 'Sub-Orchestrator Manager'
    };
    const defaultName = type === 'orchestrator' ? 'Sub-Orchestrator' : nameMap[archetype || 'custom'] || 'Worker Agent';

    const newNode = {
      id: newId,
      name: `${defaultName} #${randomSuffix}`,
      system_prompt: `You are a specialized ${defaultName} within the Hermes Synapse network.`,
      model: 'google/gemini-2.5-flash',
      agent_type: type,
      parent_id: activeOrchestratorId,
      skills: archetype === 'research' ? 'web_search' : archetype === 'code' ? 'python_sandbox' : '',
      x: 350 + Math.floor(Math.random() * 150),
      y: 150 + Math.floor(Math.random() * 150),
      temperature: 0.7
    };

    await saveAgentToServer(newNode);
    setSelectedNodeId(newId);
  };

  // Add Skill to layer
  const handleAddSkillToLayer = async (skillId: string) => {
    const activeOrch = subagents.find(n => n.id === activeOrchestratorId);
    if (activeOrch) {
      const currentSkills = activeOrch.skills ? activeOrch.skills.split(',').map((s: string) => s.trim()) : [];
      if (!currentSkills.includes(skillId)) {
        currentSkills.push(skillId);
        await saveAgentToServer({
          ...activeOrch,
          skills: currentSkills.join(',')
        });
      }
    }
  };

  // Mouse Handlers for Canvas Dragging & Selection
  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
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

  const handleMouseDownNode = (nodeId: string, e: React.MouseEvent, isSkill: boolean = false) => {
    e.preventDefault();
    e.stopPropagation();

    if (!isSkill) {
      setSelectedNodeId(nodeId);
    }

    if (canvasContainerRef.current) {
      const rect = canvasContainerRef.current.getBoundingClientRect();
      const mouseCanvasX = (e.clientX - rect.left - panOffset.x) / zoom;
      const mouseCanvasY = (e.clientY - rect.top - panOffset.y) / zoom;

      let dragNodes: Array<{ id: string; isSkill: boolean; isRss?: boolean; x: number; y: number }> = [];
      if (isSkill) {
        const skIndex = SKILLS_LIST.findIndex(s => s.id === nodeId);
        const pos = skillPositions[nodeId] || { x: 1050, y: 50 + skIndex * 120 };
        dragNodes = [{ id: nodeId, isSkill: true, isRss: false, x: pos.x, y: pos.y }];
      } else {
        const rssNode = rssNodes.find(n => n.id === nodeId);
        if (rssNode) {
          dragNodes = [{ id: nodeId, isSkill: false, isRss: true, x: rssNode.x || 300, y: rssNode.y || 200 }];
        } else {
          const node = subagents.find(n => n.id === nodeId) || { x: 100, y: 100 };
          dragNodes = [{ id: nodeId, isSkill: false, isRss: false, x: node.x || 100, y: node.y || 100 }];
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
      setSelectionBox(prev => prev ? { ...prev, endX: canvasX, endY: canvasY } : null);
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

      const rssToUpdate = draggingNode.nodes.filter(n => n.isRss);
      if (rssToUpdate.length > 0) {
        setRssNodes(prev => prev.map(n => {
          const match = rssToUpdate.find(dn => dn.id === n.id);
          if (match) {
            return { ...n, x: Math.round(match.x + dx), y: Math.round(match.y + dy) };
          }
          return n;
        }));
      }

      const subagentsToUpdate = draggingNode.nodes.filter(n => !n.isSkill && !n.isRss);
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
      setSelectionBox(null);
    }

    if (isPanning) {
      setIsPanning(false);
      if (canvasClickStart) {
        const dx = Math.abs(e.clientX - canvasClickStart.x);
        const dy = Math.abs(e.clientY - canvasClickStart.y);
        if (dx < 3 && dy < 3) {
          setSelectedNodeId(null);
        }
        setCanvasClickStart(null);
      }
    }

    if (draggingNode) {
      const subagentNodesToSave = subagents.filter(n => 
        draggingNode.nodes.some(dn => dn.id === n.id && !dn.isSkill && !dn.isRss)
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

      const rssNodesToSave = rssNodes.filter(n =>
        draggingNode.nodes.some(dn => dn.id === n.id && dn.isRss)
      );
      if (rssNodesToSave.length > 0) {
        try {
          await fetch('/api/rss/nodes/positions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              positions: rssNodesToSave.map(node => ({ id: node.id, x: node.x, y: node.y }))
            })
          });
        } catch (err) {
          console.error('Error saving RSS node positions:', err);
        }
      }

      setDraggingNode(null);
    }
  };

  // Bezier Path Helper
  const getBezierPath = (x1: number, y1: number, x2: number, y2: number) => {
    const dx = Math.max(80, Math.abs(x2 - x1) * 0.45);
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  };

  const handleConnectOutput = (nodeId: string, type: 'orchestrator' | 'agent' | 'rss_node', e: React.MouseEvent) => {
    e.stopPropagation();
    if (type === 'rss_node') {
      const node = rssNodes.find(n => n.id === nodeId);
      if (node) {
        const portX = (node.x || 300) + 230;
        const portY = (node.y || 200) + 45;
        setConnectingFrom({ id: nodeId, type, x: portX, y: portY });
        setCursorPos({ x: portX, y: portY });
      }
      return;
    }

    const node = subagents.find(n => n.id === nodeId);
    if (node) {
      const portX = (node.x || 100) + 230;
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

    if (sourceType === 'rss_node' && targetType === 'agent') {
      const rssNode = rssNodes.find(n => n.id === sourceId);
      if (rssNode) {
        const currentAgents = rssNode.connected_agents ? rssNode.connected_agents.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
        if (!currentAgents.includes(targetId)) {
          currentAgents.push(targetId);
          await fetch(`/api/rss/nodes/${sourceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ connected_agents: currentAgents.join(',') })
          });
          await fetchRssNodes();
        }
      }
      const targetAgent = subagents.find(n => n.id === targetId);
      if (targetAgent) {
        const currentSkills = targetAgent.skills ? targetAgent.skills.split(',').map((s: string) => s.trim()) : [];
        if (!currentSkills.includes('read_rss_node_feed')) {
          currentSkills.push('read_rss_node_feed');
          await saveAgentToServer({ ...targetAgent, skills: currentSkills.join(',') });
        }
      }
    } else if (sourceType === 'orchestrator' && targetType === 'agent') {
      const targetAgent = subagents.find(n => n.id === targetId);
      if (targetAgent) {
        const updatedAgent = { ...targetAgent, parent_id: sourceId };
        await saveAgentToServer(updatedAgent);
      }
    } else if (targetType === 'skill') {
      const agent = subagents.find(n => n.id === sourceId);
      if (agent) {
        const currentSkills = agent.skills ? agent.skills.split(',').map((s: string) => s.trim()) : [];
        if (!currentSkills.includes(targetId)) {
          currentSkills.push(targetId);
          await saveAgentToServer({ ...agent, skills: currentSkills.join(',') });
        }
      }
    }

    setConnectingFrom(null);
  };

  const selectedSubagentNode = subagents.find(n => n.id === selectedNodeId);
  const selectedRssNode = rssNodes.find(n => n.id === selectedNodeId);
  const selectedNodeObject = selectedRssNode ? { ...selectedRssNode, isRssNode: true } : (selectedSubagentNode || null);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '100%',
      overflow: 'hidden',
      position: 'relative',
      background: '#020617'
    }}>
      {/* Top Layer & Control Bar */}
      <OrchestratorLayerBar
        viewMode={viewMode}
        setViewMode={setViewMode}
        activeOrchestratorId={activeOrchestratorId}
        setActiveOrchestratorId={setActiveOrchestratorId}
        breadcrumbs={breadcrumbs}
        onNavigateBreadcrumb={handleNavigateBreadcrumb}
        orchestrators={orchestrators}
        onNewOrchestrator={() => handleAddSubagent('orchestrator')}
        zoom={zoom}
        setZoom={setZoom}
        onCenterView={handleCenterView}
        onToggleSandbox={() => setIsSandboxOpen(!isSandboxOpen)}
        isSandboxOpen={isSandboxOpen}
      />

      {/* Main Canvas Workspace */}
      <div 
        ref={canvasContainerRef}
        onMouseDown={handleCanvasMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        style={{
          flex: 1,
          height: '100%',
          overflow: 'hidden',
          backgroundColor: '#020617',
          backgroundImage: 'radial-gradient(rgba(255, 255, 255, 0.06) 1.2px, transparent 0)',
          backgroundSize: `${24 * zoom}px ${24 * zoom}px`,
          backgroundPosition: `${panOffset.x}px ${panOffset.y}px`,
          position: 'relative',
          cursor: isPanning ? 'grabbing' : connectingFrom ? 'crosshair' : 'default',
          userSelect: 'none'
        }}
      >
        {/* Node Palette (Left Sidebar) */}
        <NodePalette
          onAddSubagent={handleAddSubagent}
          onAddSkillToLayer={handleAddSkillToLayer}
        />

        {/* SVG Wire Connections */}
        <svg style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
          zIndex: 1
        }}>
          <g transform={`translate(${panOffset.x}, ${panOffset.y}) scale(${zoom})`}>
            {/* Direct Orchestrator to Child Connections */}
            {visibleSubagentNodes.map(node => {
              if (node.parent_id) {
                const parentNode = visibleSubagentNodes.find(p => p.id === node.parent_id);
                if (parentNode) {
                  const x1 = (parentNode.x || 100) + 230;
                  const y1 = (parentNode.y || 100) + 50;
                  const x2 = node.x || 100;
                  const y2 = (node.y || 100) + 50;
                  const isSelected = selectedNodeId === node.id || selectedNodeId === parentNode.id;

                  return (
                    <g key={`edge-${parentNode.id}-${node.id}`}>
                      <path
                        d={getBezierPath(x1, y1, x2, y2)}
                        fill="none"
                        stroke={isSelected ? '#38bdf8' : 'rgba(56, 189, 248, 0.4)'}
                        strokeWidth={isSelected ? 3 : 2}
                        strokeDasharray={isSelected ? '6,6' : undefined}
                      />
                    </g>
                  );
                }
              }
              return null;
            })}

            {/* Subagent to Skill Connections */}
            {visibleSubagentNodes.map(node => {
              if (!node.skills) return null;
              const nodeSkillIds = node.skills.split(',').map((s: string) => s.trim()).filter(Boolean);
              return nodeSkillIds.map((skId: string) => {
                const skIndex = SKILLS_LIST.findIndex(s => s.id === skId);
                if (skIndex === -1 && !skillPositions[skId]) return null;
                const pos = skillPositions[skId] || { x: 1050, y: 50 + skIndex * 120 };
                const x1 = (node.x || 100) + 230;
                const y1 = (node.y || 100) + 50;
                const x2 = pos.x;
                const y2 = pos.y + 35;
                const isSelected = selectedNodeId === node.id;

                return (
                  <g key={`skill-edge-${node.id}-${skId}`}>
                    <path
                      d={getBezierPath(x1, y1, x2, y2)}
                      fill="none"
                      stroke={isSelected ? '#c084fc' : 'rgba(192, 132, 252, 0.35)'}
                      strokeWidth={isSelected ? 2.5 : 1.5}
                      strokeDasharray="4,4"
                    />
                  </g>
                );
              });
            })}

            {/* RSS Node to Agent Connections (Skill Rays) */}
            {rssNodes.map(rssNode => {
              const connectedAgents = rssNode.connected_agents ? rssNode.connected_agents.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
              return connectedAgents.map((agentId: string) => {
                const targetAgent = visibleSubagentNodes.find(a => a.id === agentId);
                if (!targetAgent) return null;

                const x1 = (rssNode.x || 300) + 230;
                const y1 = (rssNode.y || 200) + 45;
                const x2 = targetAgent.x || 100;
                const y2 = (targetAgent.y || 100) + 50;
                const isSelected = selectedNodeId === rssNode.id || selectedNodeId === targetAgent.id;

                return (
                  <g key={`rss-edge-${rssNode.id}-${agentId}`}>
                    <path
                      d={getBezierPath(x1, y1, x2, y2)}
                      fill="none"
                      stroke={isSelected ? '#f97316' : 'rgba(249, 115, 22, 0.5)'}
                      strokeWidth={isSelected ? 3 : 2}
                      strokeDasharray="6,4"
                    />
                  </g>
                );
              });
            })}

            {/* Connecting Wire Preview */}
            {connectingFrom && (
              <path
                d={getBezierPath(connectingFrom.x, connectingFrom.y, cursorPos.x, cursorPos.y)}
                fill="none"
                stroke="#34d399"
                strokeWidth={3}
                strokeDasharray="5,5"
              />
            )}
          </g>
        </svg>

        {/* Nodes Canvas Layer */}
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoom})`,
          transformOrigin: '0 0',
          pointerEvents: 'auto',
          zIndex: 2
        }}>
          {/* Subagent & Orchestrator Nodes */}
          {visibleSubagentNodes.map(node => {
            const isSelected = selectedNodeId === node.id;
            const isOrchestrator = node.agent_type === 'orchestrator' || node.id === 'jarvis' || node.id === activeOrchestratorId;
            const skillCount = node.skills ? node.skills.split(',').filter(Boolean).length : 0;

            return (
              <div
                key={node.id}
                onMouseDown={(e) => handleMouseDownNode(node.id, e, false)}
                onMouseUp={() => {
                  if (connectingFrom && connectingFrom.id !== node.id) {
                    handleConnectInput(node.id, 'agent');
                  }
                }}
                onClick={() => {
                  if (connectingFrom && connectingFrom.id !== node.id) {
                    handleConnectInput(node.id, 'agent');
                  }
                }}
                onDoubleClick={() => isOrchestrator && handleDrillDownOrchestrator(node)}
                style={{
                  position: 'absolute',
                  left: `${node.x || 100}px`,
                  top: `${node.y || 100}px`,
                  width: 230,
                  minHeight: 100,
                  background: isOrchestrator 
                    ? 'linear-gradient(135deg, rgba(30, 27, 75, 0.95), rgba(15, 23, 42, 0.95))' 
                    : 'linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.95))',
                  border: isSelected 
                    ? '2px solid #38bdf8' 
                    : isOrchestrator 
                    ? '1.5px solid rgba(168, 85, 247, 0.6)' 
                    : '1.5px solid rgba(255, 255, 255, 0.12)',
                  borderRadius: '12px',
                  padding: '12px',
                  boxShadow: isSelected 
                    ? '0 0 20px rgba(56, 189, 248, 0.4)' 
                    : '0 8px 24px rgba(0, 0, 0, 0.4)',
                  cursor: 'grab',
                  backdropFilter: 'blur(8px)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  zIndex: isSelected ? 10 : 3
                }}
              >
                {/* Node Top Row */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '6px',
                      background: isOrchestrator ? 'rgba(168, 85, 247, 0.2)' : 'rgba(56, 189, 248, 0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: isOrchestrator ? '#c084fc' : '#38bdf8'
                    }}>
                      {isOrchestrator ? <Layers size={16} /> : <Bot size={16} />}
                    </div>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: '#f3f4f6', lineHeight: 1.2 }}>
                        {node.name || node.id}
                      </div>
                      <div style={{ fontSize: '10px', color: isOrchestrator ? '#c084fc' : '#9ca3af', fontWeight: 500 }}>
                        {isOrchestrator ? 'Orchestrator' : 'Worker Agent'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Node Details & Badges */}
                <div style={{ fontSize: '11px', color: '#9ca3af', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Cpu size={12} style={{ color: '#10b981' }} />
                    <span style={{ color: '#d1d5db', fontFamily: 'monospace' }}>{node.model || 'gemini-2.5-flash'}</span>
                  </div>
                  {skillCount > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Wrench size={12} style={{ color: '#c084fc' }} />
                      <span>{skillCount} active skills attached</span>
                    </div>
                  )}
                </div>

                {/* Ports / Connection Handles */}
                {/* Input Handle (Left) */}
                <div
                  onClick={(e) => { e.stopPropagation(); handleConnectInput(node.id, 'agent'); }}
                  onMouseDown={(e) => { e.stopPropagation(); handleConnectInput(node.id, 'agent'); }}
                  onMouseUp={(e) => { e.stopPropagation(); handleConnectInput(node.id, 'agent'); }}
                  title="Connect Input Handle"
                  style={{
                    position: 'absolute',
                    left: '-8px',
                    top: '46px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    background: '#38bdf8',
                    border: '2px solid #020617',
                    cursor: 'pointer',
                    zIndex: 5
                  }}
                />

                {/* Output Handle (Right) */}
                <div
                  onClick={(e) => handleConnectOutput(node.id, isOrchestrator ? 'orchestrator' : 'agent', e)}
                  onMouseDown={(e) => handleConnectOutput(node.id, isOrchestrator ? 'orchestrator' : 'agent', e)}
                  title="Drag Output Handle to Connect"
                  style={{
                    position: 'absolute',
                    right: '-8px',
                    top: '46px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    background: '#34d399',
                    border: '2px solid #020617',
                    cursor: 'pointer',
                    zIndex: 5
                  }}
                />
              </div>
            );
          })}

          {/* RSS Data Source Nodes */}
          {rssNodes.map(node => {
            const isSelected = selectedNodeId === node.id;

            return (
              <div
                key={node.id}
                onMouseDown={(e) => handleMouseDownNode(node.id, e, false)}
                style={{
                  position: 'absolute',
                  left: `${node.x || 300}px`,
                  top: `${node.y || 200}px`,
                  width: 230,
                  minHeight: 90,
                  background: 'linear-gradient(135deg, rgba(30, 15, 10, 0.95), rgba(15, 23, 42, 0.95))',
                  border: isSelected 
                    ? '2px solid #ea580c' 
                    : '1.5px solid rgba(249, 115, 22, 0.5)',
                  borderRadius: '12px',
                  padding: '12px',
                  boxShadow: isSelected 
                    ? '0 0 20px rgba(234, 88, 12, 0.4)' 
                    : '0 8px 24px rgba(0, 0, 0, 0.4)',
                  cursor: 'grab',
                  backdropFilter: 'blur(8px)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  zIndex: isSelected ? 10 : 3
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '6px',
                      background: 'rgba(249, 115, 22, 0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#ea580c'
                    }}>
                      <Rss size={16} />
                    </div>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', lineHeight: 1.2 }}>
                        {node.name}
                      </div>
                      <div style={{ fontSize: '10px', color: '#fdba74', fontWeight: 500 }}>
                        RSS Data Source Node
                      </div>
                    </div>
                  </div>
                </div>

                <div style={{ fontSize: '11px', color: '#9ca3af', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ color: '#cbd5e1' }}>Output Limit: {node.output_limit} items</span>
                  <span style={{ fontSize: '10px', color: node.is_active ? '#10b981' : '#64748b' }}>
                    {node.is_active ? '● Poller Active' : '○ Poller Paused'}
                  </span>
                </div>

                {/* Output Handle (Right) */}
                <div
                  onClick={(e) => { e.stopPropagation(); handleConnectOutput(node.id, 'rss_node', e); }}
                  onMouseDown={(e) => { e.stopPropagation(); handleConnectOutput(node.id, 'rss_node', e); }}
                  title="Click or Drag Output Handle to Connect Agent"
                  style={{
                    position: 'absolute',
                    right: '-8px',
                    top: '41px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    background: '#ea580c',
                    border: '2px solid #020617',
                    cursor: 'pointer',
                    zIndex: 5
                  }}
                />
              </div>
            );
          })}

          {/* Skill Nodes */}
          {SKILLS_LIST.map((skill, skIndex) => {
            const pos = skillPositions[skill.id] || { x: 1050, y: 50 + skIndex * 120 };

            return (
              <div
                key={skill.id}
                onMouseDown={(e) => handleMouseDownNode(skill.id, e, true)}
                style={{
                  position: 'absolute',
                  left: `${pos.x}px`,
                  top: `${pos.y}px`,
                  width: 200,
                  height: 65,
                  background: 'rgba(15, 23, 42, 0.9)',
                  border: `1.5px solid ${skill.color}60`,
                  borderRadius: '10px',
                  padding: '10px',
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
                  cursor: 'grab',
                  backdropFilter: 'blur(8px)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  zIndex: 3
                }}
              >
                {/* Input Socket Handle (Left) */}
                <div
                  onClick={() => handleConnectInput(skill.id, 'skill')}
                  title="Connect Agent to Skill"
                  style={{
                    position: 'absolute',
                    left: '-8px',
                    top: '25px',
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    background: skill.color,
                    border: '2px solid #020617',
                    cursor: 'pointer'
                  }}
                />

                <div style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: skill.color
                }} />
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#f3f4f6', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {skill.name}
                  </div>
                  <div style={{ fontSize: '10px', color: '#9ca3af', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {skill.desc}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Drawer: Node Inspector */}
      {selectedNodeId && (
        <NodeInspectorDrawer
          selectedNode={selectedNodeObject}
          onClose={() => setSelectedNodeId(null)}
          onSaveNode={async (updated) => {
            await saveAgentToServer(updated);
            setSelectedNodeId(null);
          }}
          onDeleteNode={handleDeleteNode}
          models={models}
          orchestrators={orchestrators}
        />
      )}

      {/* Bottom Drawer: Layer Testing Sandbox */}
      {isSandboxOpen && (
        <LayerSandboxDrawer
          activeOrchestrator={activeOrchestratorNode}
          onClose={() => setIsSandboxOpen(false)}
        />
      )}
    </div>
  );
}
