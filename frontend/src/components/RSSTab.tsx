import React, { useState, useEffect } from 'react';
import {
  Rss,
  RefreshCw,
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Search,
  Sliders,
  Clock,
  Database
} from 'lucide-react';

export interface RSSNode {
  id: string;
  name: string;
  feed_urls: string;
  fetch_interval_minutes: number;
  output_limit: number;
  date_filter_days: number;
  keywords_filter: string;
  is_active: boolean;
  x: number;
  y: number;
  connected_agents: string;
  last_fetched_at?: string;
  created_at?: string;
}

export interface RSSItem {
  id: number;
  node_id: string;
  feed_url: string;
  guid: string;
  title: string;
  link: string;
  summary: string;
  published_at: string;
  fetched_at: string;
}

export function RSSTab() {
  const [nodes, setNodes] = useState<RSSNode[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [items, setItems] = useState<RSSItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetchingNodeId, setFetchingNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  // Form State
  const [formData, setFormData] = useState<Partial<RSSNode>>({
    id: '',
    name: '',
    feed_urls: '',
    fetch_interval_minutes: 15,
    output_limit: 10,
    date_filter_days: 0,
    keywords_filter: '',
    is_active: true
  });

  const fetchNodes = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/rss/nodes');
      if (res.ok) {
        const data = await res.json();
        setNodes(data);
        if (data.length > 0 && !selectedNodeId) {
          setSelectedNodeId(data[0].id);
        }
      }
    } catch (e) {
      console.error('Error fetching RSS nodes:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchNodeItems = async (nodeId: string) => {
    try {
      const res = await fetch(`/api/rss/nodes/${nodeId}/items?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
      }
    } catch (e) {
      console.error('Error fetching RSS items:', e);
    }
  };

  useEffect(() => {
    fetchNodes();
  }, []);

  useEffect(() => {
    if (selectedNodeId) {
      fetchNodeItems(selectedNodeId);
      const node = nodes.find(n => n.id === selectedNodeId);
      if (node) {
        setFormData(node);
      }
    }
  }, [selectedNodeId]);

  const handleManualFetch = async (nodeId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      setFetchingNodeId(nodeId);
      const res = await fetch(`/api/rss/nodes/${nodeId}/fetch`, { method: 'POST' });
      if (res.ok) {
        await fetchNodes();
        if (selectedNodeId === nodeId) {
          await fetchNodeItems(nodeId);
        }
      }
    } catch (err) {
      console.error('Error triggering manual fetch:', err);
    } finally {
      setFetchingNodeId(null);
    }
  };

  const handleCreateNew = () => {
    const newId = `rss_node_${Date.now().toString().slice(-4)}`;
    setFormData({
      id: newId,
      name: 'New RSS Feed Node',
      feed_urls: 'https://habr.com/ru/rss/news/',
      fetch_interval_minutes: 15,
      output_limit: 10,
      date_filter_days: 0,
      keywords_filter: '',
      is_active: true,
      x: 300,
      y: 200,
      connected_agents: ''
    });
    setSelectedNodeId(null);
    setIsEditing(true);
  };

  const handleSaveNode = async () => {
    if (!formData.id || !formData.name) return;
    try {
      const isExisting = nodes.some(n => n.id === formData.id);
      const url = isExisting ? `/api/rss/nodes/${formData.id}` : '/api/rss/nodes';
      const method = isExisting ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });

      if (res.ok) {
        await fetchNodes();
        setSelectedNodeId(formData.id);
        setIsEditing(false);
        // Automatically fetch data for newly created node
        if (!isExisting) {
          handleManualFetch(formData.id);
        }
      }
    } catch (e) {
      console.error('Error saving RSS node:', e);
    }
  };

  const handleDeleteNode = async (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to delete RSS node '${nodeId}'?`)) return;
    try {
      const res = await fetch(`/api/rss/nodes/${nodeId}`, { method: 'DELETE' });
      if (res.ok) {
        setSelectedNodeId(null);
        await fetchNodes();
      }
    } catch (e) {
      console.error('Error deleting node:', e);
    }
  };

  const selectedNode = nodes.find(n => n.id === selectedNodeId);

  const filteredItems = items.filter(item => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return item.title.toLowerCase().includes(q) || item.summary.toLowerCase().includes(q);
  });

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '100%',
      backgroundColor: '#020617',
      color: '#f8fafc',
      overflow: 'hidden'
    }}>
      {/* Top Header Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 24px',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(12px)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '38px',
            height: '38px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(249, 115, 22, 0.3)'
          }}>
            <Rss size={20} color="#ffffff" />
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#f8fafc' }}>
              RSS Autonomous Nodes
            </h2>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>
              Autonomous Python Background Poller & Agent Skill Rays
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={fetchNodes}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              background: 'rgba(30, 41, 59, 0.6)',
              color: '#cbd5e1',
              cursor: 'pointer',
              fontSize: '13px',
              transition: 'all 0.2s'
            }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh List
          </button>

          <button
            onClick={handleCreateNew}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: 'linear-gradient(135deg, #ea580c 0%, #c2410c 100%)',
              color: '#ffffff',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: 500,
              boxShadow: '0 2px 8px rgba(234, 88, 12, 0.4)'
            }}
          >
            <Plus size={16} />
            Add RSS Node
          </button>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left Sidebar: Node Selector */}
        <div style={{
          width: '320px',
          borderRight: '1px solid rgba(255, 255, 255, 0.08)',
          background: '#090d16',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, letterSpacing: '0.05em', color: '#64748b', textTransform: 'uppercase' }}>
              Configured RSS Nodes ({nodes.length})
            </span>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
            {nodes.length === 0 ? (
              <div style={{ padding: '24px 16px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
                No RSS nodes configured yet. Click "Add RSS Node" above to create your first autonomous news poller.
              </div>
            ) : (
              nodes.map(node => {
                const isSelected = selectedNodeId === node.id && !isEditing;
                const isFetching = fetchingNodeId === node.id;

                return (
                  <div
                    key={node.id}
                    onClick={() => {
                      setSelectedNodeId(node.id);
                      setIsEditing(false);
                    }}
                    style={{
                      padding: '12px 14px',
                      borderRadius: '10px',
                      marginBottom: '8px',
                      background: isSelected ? 'rgba(234, 88, 12, 0.15)' : 'rgba(30, 41, 59, 0.4)',
                      border: isSelected ? '1px solid rgba(249, 115, 22, 0.5)' : '1px solid rgba(255, 255, 255, 0.05)',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          background: node.is_active ? '#10b981' : '#64748b',
                          boxShadow: node.is_active ? '0 0 8px #10b981' : 'none'
                        }} />
                        <span style={{ fontWeight: 600, fontSize: '14px', color: isSelected ? '#fdba74' : '#f1f5f9' }}>
                          {node.name}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <button
                          onClick={(e) => handleManualFetch(node.id, e)}
                          title="Sync Feed Now"
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#94a3b8',
                            cursor: 'pointer',
                            padding: '4px',
                            borderRadius: '4px'
                          }}
                        >
                          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
                        </button>
                        <button
                          onClick={(e) => handleDeleteNode(node.id, e)}
                          title="Delete Node"
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#ef4444',
                            cursor: 'pointer',
                            padding: '4px',
                            borderRadius: '4px'
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>

                    <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Clock size={12} />
                      {node.last_fetched_at ? (
                        <span>Synced: {new Date(node.last_fetched_at).toLocaleTimeString()}</span>
                      ) : (
                        <span>Never synced</span>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '10px', background: 'rgba(255, 255, 255, 0.06)', padding: '2px 6px', borderRadius: '4px', color: '#cbd5e1' }}>
                        Limit: {node.output_limit} items
                      </span>
                      <span style={{ fontSize: '10px', background: 'rgba(255, 255, 255, 0.06)', padding: '2px 6px', borderRadius: '4px', color: '#cbd5e1' }}>
                        {node.fetch_interval_minutes}m interval
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Main Panel */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#020617' }}>
          {isEditing || !selectedNode ? (
            /* Node Form / Config Panel */
            <div style={{ padding: '24px', flex: 1, overflowY: 'auto' }}>
              <div style={{
                maxWidth: '700px',
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '12px',
                padding: '24px'
              }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sliders size={18} color="#f97316" />
                  {formData.id && nodes.some(n => n.id === formData.id) ? 'Edit RSS Node Settings' : 'Create New RSS Node'}
                </h3>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                      Node Unique ID
                    </label>
                    <input
                      type="text"
                      value={formData.id || ''}
                      onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                      disabled={nodes.some(n => n.id === formData.id)}
                      placeholder="e.g. habr_tech_news"
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        background: '#090d16',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '6px',
                        color: '#f8fafc',
                        fontSize: '13px'
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                      Node Display Name
                    </label>
                    <input
                      type="text"
                      value={formData.name || ''}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder="e.g. Habr Tech & IT News"
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        background: '#090d16',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '6px',
                        color: '#f8fafc',
                        fontSize: '13px'
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                      RSS Feed URLs (Comma or line separated)
                    </label>
                    <textarea
                      rows={3}
                      value={formData.feed_urls || ''}
                      onChange={(e) => setFormData({ ...formData, feed_urls: e.target.value })}
                      placeholder="https://habr.com/ru/rss/news/&#10;https://rssexport.rbc.ru/rbcnews/news/30/full.rss"
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        background: '#090d16',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '6px',
                        color: '#f8fafc',
                        fontSize: '13px',
                        fontFamily: 'monospace'
                      }}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                        Output Record Limit (Count)
                      </label>
                      <input
                        type="number"
                        value={formData.output_limit || 10}
                        onChange={(e) => setFormData({ ...formData, output_limit: parseInt(e.target.value) || 10 })}
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          background: '#090d16',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '13px'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                        Date Filter Window (Days, 0 = All Time)
                      </label>
                      <input
                        type="number"
                        value={formData.date_filter_days || 0}
                        onChange={(e) => setFormData({ ...formData, date_filter_days: parseInt(e.target.value) || 0 })}
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          background: '#090d16',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '13px'
                        }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                        Polling Interval (Minutes)
                      </label>
                      <input
                        type="number"
                        value={formData.fetch_interval_minutes || 15}
                        onChange={(e) => setFormData({ ...formData, fetch_interval_minutes: parseInt(e.target.value) || 15 })}
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          background: '#090d16',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '13px'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                        Keywords Filter (Comma separated)
                      </label>
                      <input
                        type="text"
                        value={formData.keywords_filter || ''}
                        onChange={(e) => setFormData({ ...formData, keywords_filter: e.target.value })}
                        placeholder="e.g. AI, Python, Market"
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          background: '#090d16',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '13px'
                        }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
                    <input
                      type="checkbox"
                      id="is_active_check"
                      checked={formData.is_active ?? true}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      style={{ cursor: 'pointer' }}
                    />
                    <label htmlFor="is_active_check" style={{ fontSize: '13px', color: '#e2e8f0', cursor: 'pointer' }}>
                      Enable Autonomous Poller for this Node
                    </label>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                    <button
                      onClick={handleSaveNode}
                      style={{
                        padding: '10px 20px',
                        borderRadius: '8px',
                        background: 'linear-gradient(135deg, #ea580c 0%, #c2410c 100%)',
                        color: '#ffffff',
                        border: 'none',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      Save RSS Node
                    </button>
                    {selectedNode && (
                      <button
                        onClick={() => setIsEditing(false)}
                        style={{
                          padding: '10px 16px',
                          borderRadius: '8px',
                          background: 'rgba(30, 41, 59, 0.6)',
                          color: '#cbd5e1',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          fontSize: '13px',
                          cursor: 'pointer'
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Selected Node View & Data Table */
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
              {/* Node Stats Header */}
              <div style={{
                padding: '16px 24px',
                borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                background: 'rgba(15, 23, 42, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', color: '#f8fafc' }}>
                      {selectedNode.name}
                    </h3>
                    <span style={{ fontSize: '11px', background: 'rgba(234, 88, 12, 0.2)', color: '#fdba74', padding: '2px 8px', borderRadius: '4px' }}>
                      ID: {selectedNode.id}
                    </span>
                  </div>
                  <span style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px', display: 'block' }}>
                    Sources: {selectedNode.feed_urls || 'Default standard feeds'}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <button
                    onClick={() => handleManualFetch(selectedNode.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 14px',
                      borderRadius: '6px',
                      background: 'rgba(234, 88, 12, 0.2)',
                      border: '1px solid rgba(234, 88, 12, 0.4)',
                      color: '#fdba74',
                      fontSize: '12px',
                      fontWeight: 500,
                      cursor: 'pointer'
                    }}
                  >
                    <RefreshCw size={13} className={fetchingNodeId === selectedNode.id ? 'animate-spin' : ''} />
                    Sync Now
                  </button>

                  <button
                    onClick={() => setIsEditing(true)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 14px',
                      borderRadius: '6px',
                      background: 'rgba(30, 41, 59, 0.8)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: '#cbd5e1',
                      fontSize: '12px',
                      cursor: 'pointer'
                    }}
                  >
                    <Edit3 size={13} />
                    Configure Node
                  </button>
                </div>
              </div>

              {/* Data Table Search Bar */}
              <div style={{
                padding: '12px 24px',
                borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: '#090d16', padding: '6px 12px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.08)', width: '320px' }}>
                  <Search size={14} color="#64748b" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search collected articles..."
                    style={{ background: 'none', border: 'none', color: '#f8fafc', fontSize: '13px', outline: 'none', width: '100%' }}
                  />
                </div>

                <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Database size={14} />
                  <span>Showing {filteredItems.length} stored articles in `rss_feed_items`</span>
                </div>
              </div>

              {/* Articles Data Grid */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
                {filteredItems.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '48px 0', color: '#64748b' }}>
                    <Rss size={32} style={{ marginBottom: '12px', opacity: 0.5 }} />
                    <p style={{ margin: 0, fontSize: '14px' }}>No articles found for this RSS node.</p>
                    <p style={{ margin: '4px 0 0 0', fontSize: '12px' }}>Click "Sync Now" above to trigger an instant RSS fetch.</p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {filteredItems.map(item => (
                      <div
                        key={item.id}
                        style={{
                          padding: '14px 16px',
                          borderRadius: '8px',
                          background: 'rgba(15, 23, 42, 0.5)',
                          border: '1px solid rgba(255, 255, 255, 0.06)',
                          transition: 'all 0.2s'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
                          <a
                            href={item.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              fontSize: '14px',
                              fontWeight: 600,
                              color: '#38bdf8',
                              textDecoration: 'none',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px'
                            }}
                          >
                            {item.title}
                            <ExternalLink size={12} color="#38bdf8" />
                          </a>

                          <span style={{ fontSize: '11px', color: '#64748b', whiteSpace: 'nowrap' }}>
                            {item.published_at || new Date(item.fetched_at).toLocaleDateString()}
                          </span>
                        </div>

                        {item.summary && (
                          <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: '#cbd5e1', lineHeight: '1.5' }}>
                            {item.summary.replace(/<[^>]*>?/gm, '').slice(0, 240)}
                            {item.summary.length > 240 ? '...' : ''}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
