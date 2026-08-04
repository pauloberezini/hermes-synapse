import React from 'react';
import { 
  Layers, 
  Globe, 
  ChevronRight, 
  Plus, 
  Maximize2, 
  ZoomIn, 
  ZoomOut, 
  Play
} from 'lucide-react';

export interface BreadcrumbItem {
  id: string;
  name: string;
}

interface OrchestratorLayerBarProps {
  viewMode: 'layer' | 'mesh';
  setViewMode: (mode: 'layer' | 'mesh') => void;
  activeOrchestratorId: string;
  setActiveOrchestratorId: (id: string) => void;
  breadcrumbs: BreadcrumbItem[];
  onNavigateBreadcrumb: (index: number) => void;
  orchestrators: Array<{ id: string; name: string }>;
  onNewOrchestrator: () => void;
  zoom: number;
  setZoom: React.Dispatch<React.SetStateAction<number>>;
  onCenterView: () => void;
  onToggleSandbox: () => void;
  isSandboxOpen: boolean;
}

export function OrchestratorLayerBar({
  viewMode,
  setViewMode,
  activeOrchestratorId,
  setActiveOrchestratorId,
  breadcrumbs,
  onNavigateBreadcrumb,
  orchestrators,
  onNewOrchestrator,
  zoom,
  setZoom,
  onCenterView,
  onToggleSandbox,
  isSandboxOpen
}: OrchestratorLayerBarProps) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 16px',
      background: 'var(--bg-secondary, #111827)',
      borderBottom: '1px solid var(--border-color, rgba(255,255,255,0.1))',
      gap: '12px',
      flexWrap: 'wrap',
      zIndex: 10
    }}>
      {/* Left: View Mode Toggle & Breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Mode Switcher */}
        <div style={{
          display: 'flex',
          background: 'rgba(0,0,0,0.3)',
          borderRadius: '8px',
          padding: '3px',
          border: '1px solid rgba(255,255,255,0.08)'
        }}>
          <button
            onClick={() => setViewMode('layer')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 500,
              border: 'none',
              cursor: 'pointer',
              background: viewMode === 'layer' ? 'var(--accent-cyan, #06b6d4)' : 'transparent',
              color: viewMode === 'layer' ? '#000' : 'var(--text-secondary, #9ca3af)',
              transition: 'all 0.2s ease'
            }}
          >
            <Layers size={14} />
            Layer Builder
          </button>

          <button
            onClick={() => setViewMode('mesh')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 500,
              border: 'none',
              cursor: 'pointer',
              background: viewMode === 'mesh' ? 'var(--accent-cyan, #06b6d4)' : 'transparent',
              color: viewMode === 'mesh' ? '#000' : 'var(--text-secondary, #9ca3af)',
              transition: 'all 0.2s ease'
            }}
          >
            <Globe size={14} />
            Global Mesh
          </button>
        </div>

        {/* Orchestrator Select Dropdown (when in layer mode) */}
        {viewMode === 'layer' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted, #6b7280)', fontWeight: 500 }}>
              Active Orchestrator:
            </span>
            <select
              value={activeOrchestratorId}
              onChange={(e) => setActiveOrchestratorId(e.target.value)}
              style={{
                background: 'rgba(15, 23, 42, 0.8)',
                color: '#f3f4f6',
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: '6px',
                padding: '5px 10px',
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

            <button
              onClick={onNewOrchestrator}
              title="Add New Orchestrator"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                background: 'rgba(139, 92, 246, 0.2)',
                color: '#a78bfa',
                border: '1px solid rgba(139, 92, 246, 0.4)',
                borderRadius: '6px',
                padding: '5px 10px',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: 500
              }}
            >
              <Plus size={14} />
              Orchestrator
            </button>
          </div>
        )}

        {/* Breadcrumb Trail */}
        {viewMode === 'layer' && breadcrumbs.length > 1 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            background: 'rgba(0,0,0,0.2)',
            padding: '4px 10px',
            borderRadius: '6px',
            fontSize: '12px'
          }}>
            {breadcrumbs.map((crumb, idx) => (
              <React.Fragment key={crumb.id}>
                {idx > 0 && <ChevronRight size={12} style={{ color: '#6b7280' }} />}
                <span
                  onClick={() => onNavigateBreadcrumb(idx)}
                  style={{
                    color: idx === breadcrumbs.length - 1 ? '#38bdf8' : '#9ca3af',
                    cursor: idx < breadcrumbs.length - 1 ? 'pointer' : 'default',
                    fontWeight: idx === breadcrumbs.length - 1 ? 600 : 400
                  }}
                >
                  {crumb.name}
                </span>
              </React.Fragment>
            ))}
          </div>
        )}
      </div>

      {/* Right: View Controls & Sandbox Trigger */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {/* Zoom & Fit View */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '2px',
          background: 'rgba(0,0,0,0.3)',
          borderRadius: '6px',
          padding: '2px',
          border: '1px solid rgba(255,255,255,0.08)'
        }}>
          <button
            onClick={() => setZoom(prev => Math.max(0.3, prev - 0.15))}
            title="Zoom Out"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#9ca3af',
              padding: '5px',
              cursor: 'pointer',
              borderRadius: '4px'
            }}
          >
            <ZoomOut size={14} />
          </button>
          <span style={{ fontSize: '11px', color: '#d1d5db', width: '36px', textAlign: 'center' }}>
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom(prev => Math.min(2.0, prev + 0.15))}
            title="Zoom In"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#9ca3af',
              padding: '5px',
              cursor: 'pointer',
              borderRadius: '4px'
            }}
          >
            <ZoomIn size={14} />
          </button>
          <button
            onClick={onCenterView}
            title="Center / Fit View"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#38bdf8',
              padding: '5px',
              cursor: 'pointer',
              borderRadius: '4px',
              marginLeft: '2px'
            }}
          >
            <Maximize2 size={14} />
          </button>
        </div>

        {/* Test / Sandbox Trigger Button */}
        <button
          onClick={onToggleSandbox}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: isSandboxOpen ? 'rgba(16, 185, 129, 0.25)' : 'rgba(16, 185, 129, 0.15)',
            color: '#34d399',
            border: '1px solid rgba(16, 185, 129, 0.4)',
            borderRadius: '6px',
            padding: '6px 12px',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
        >
          <Play size={13} fill="#34d399" />
          {isSandboxOpen ? 'Close Sandbox' : 'Test Layer Sandbox'}
        </button>
      </div>
    </div>
  );
}
