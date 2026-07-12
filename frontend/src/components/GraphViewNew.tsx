"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GraphCanvas, GraphCanvasRef } from "reagraph";
import { useInvestigation } from "@/context/InvestigationContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Professional color palette for entity types (optimized for light background)
const NODE_COLORS: Record<string, string> = {
  person: "#3B82F6",      // Blue
  organization: "#8B5CF6", // Purple
  location: "#F59E0B",     // Amber
  event: "#EF4444",        // Red
  crime: "#DC2626",        // Dark Red
  evidence: "#10B981",     // Emerald
  vehicle: "#6366F1",      // Indigo
  weapon: "#F97316",       // Orange
  default: "#6B7280",      // Gray
};

// Centrality data type
interface CentralityData {
  [nodeLabel: string]: number;
}

// Tooltip info
interface TooltipInfo {
  visible: boolean;
  x: number;
  y: number;
  node: {
    label: string;
    type: string;
    centrality: number;
    properties: Record<string, unknown>;
    connections: number;
    date?: string;
    dateDescription?: string;
  } | null;
}

// Clean light theme for the graph
const lightTheme = {
  canvas: { background: "#FAFBFC" },
  node: {
    fill: "#6B7280",
    activeFill: "#3B82F6",
    opacity: 1,
    selectedOpacity: 1,
    inactiveOpacity: 0.4,
    label: {
      color: "#1F2937",
      fontSize: 11,
      fontFamily: "Inter, system-ui, sans-serif",
      activeColor: "#111827",
    },
  },
  edge: {
    fill: "#D1D5DB",
    activeFill: "#3B82F6",
    opacity: 0.8,
    selectedOpacity: 1,
    inactiveOpacity: 0.3,
    label: {
      color: "#6B7280",
      fontSize: 9,
      fontFamily: "Inter, system-ui, sans-serif",
      activeColor: "#374151",
    },
  },
  ring: {
    fill: "#3B82F6",
    activeFill: "#2563EB",
  },
  arrow: {
    fill: "#9CA3AF",
    activeFill: "#3B82F6",
  },
  lasso: {
    background: "rgba(59, 130, 246, 0.1)",
    border: "#3B82F6",
  },
};

export function GraphView() {
  const { currentInvestigation, refreshGraph, focusedNodeId, clearFocusedNode } = useInvestigation();
  const graphRef = useRef<GraphCanvasRef | null>(null);
  
  // State
  const [is3D, setIs3D] = useState(false);
  const [centralityScores, setCentralityScores] = useState<CentralityData>({});
  const [tooltip, setTooltip] = useState<TooltipInfo>({
    visible: false,
    x: 0,
    y: 0,
    node: null,
  });

  // Timeline state
  const [timelineEnabled, setTimelineEnabled] = useState(false);
  const [timelinePosition, setTimelinePosition] = useState(100);
  const [isPlaying, setIsPlaying] = useState(false);

  const nodes = useMemo(() => currentInvestigation?.nodes || [], [currentInvestigation?.nodes]);
  const edges = useMemo(() => currentInvestigation?.edges || [], [currentInvestigation?.edges]);

  // Timeline calculations
  const timelineData = useMemo(() => {
    const nodesWithDates = nodes.filter(n => n.date);
    if (nodesWithDates.length === 0) {
      return { hasTimeline: false, minDate: null, maxDate: null, sortedDates: [] };
    }
    
    const sortedDates = nodesWithDates
      .map(n => ({ nodeId: n.id, date: new Date(n.date!), label: n.label, dateDesc: n.dateDescription }))
      .sort((a, b) => a.date.getTime() - b.date.getTime());
    
    return {
      hasTimeline: true,
      minDate: sortedDates[0].date,
      maxDate: sortedDates[sortedDates.length - 1].date,
      sortedDates,
    };
  }, [nodes]);

  // Visible nodes based on timeline
  const visibleNodeIds = useMemo(() => {
    if (!timelineEnabled || !timelineData.hasTimeline || !timelineData.minDate || !timelineData.maxDate) {
      return new Set(nodes.map(n => n.id));
    }
    
    const minTime = timelineData.minDate.getTime();
    const maxTime = timelineData.maxDate.getTime();
    const timeRange = maxTime - minTime;
    const cutoffTime = minTime + (timeRange * timelinePosition / 100);
    
    const visibleIds = new Set<string>();
    nodes.forEach(n => {
      if (!n.date) {
        visibleIds.add(n.id);
      } else {
        const nodeTime = new Date(n.date).getTime();
        if (nodeTime <= cutoffTime) {
          visibleIds.add(n.id);
        }
      }
    });
    
    return visibleIds;
  }, [timelineEnabled, timelineData, timelinePosition, nodes]);

  // Current timeline date
  const currentTimelineDate = useMemo(() => {
    if (!timelineData.hasTimeline || !timelineData.minDate || !timelineData.maxDate) return null;
    
    const minTime = timelineData.minDate.getTime();
    const maxTime = timelineData.maxDate.getTime();
    const timeRange = maxTime - minTime;
    const currentTime = minTime + (timeRange * timelinePosition / 100);
    
    return new Date(currentTime);
  }, [timelineData, timelinePosition]);

  // Timeline playback
  useEffect(() => {
    if (!isPlaying) return;
    
    const interval = setInterval(() => {
      setTimelinePosition(prev => {
        if (prev >= 100) {
          setIsPlaying(false);
          return 100;
        }
        return Math.min(100, prev + 2);
      });
    }, 150);
    
    return () => clearInterval(interval);
  }, [isPlaying]);

  // Fetch centrality scores
  useEffect(() => {
    const fetchCentrality = async () => {
      if (!currentInvestigation || nodes.length === 0) {
        setCentralityScores({});
        return;
      }
      
      try {
        const response = await fetch(`${API_URL}/detective/analyze/most-important?top_n=100`);
        if (response.ok) {
          const data = await response.json();
          const scores: CentralityData = {};
          for (const influencer of data.influencers || []) {
            scores[influencer.name] = influencer.betweenness_score;
          }
          setCentralityScores(scores);
        }
      } catch (error) {
        console.error("Failed to fetch centrality scores:", error);
      }
    };
    
    fetchCentrality();
  }, [currentInvestigation, nodes.length]);

  // Handle focused node
  useEffect(() => {
    if (focusedNodeId && graphRef.current) {
      // Check if the focused node exists in the current visible nodes
      const visibleNodes = nodes.filter(n => visibleNodeIds.has(n.id));
      const nodeExists = visibleNodes.some(n => n.id === focusedNodeId);
      
      if (!nodeExists) {
        // Node might be hidden by timeline filter - check if it exists in full nodes
        const existsInFullNodes = nodes.some(n => n.id === focusedNodeId);
        
        if (existsInFullNodes && timelineEnabled) {
          // Disable timeline to show the node, then focus
          setTimelineEnabled(false);
          setTimelinePosition(100);
        } else if (!existsInFullNodes) {
          // Node truly doesn't exist, clear focus
          console.warn(`Focused node ${focusedNodeId} not found in graph`);
          clearFocusedNode();
          return;
        }
      }
      
      // Wait for graph to render/update
      const timeoutId = setTimeout(() => {
        // Re-check node exists after potential timeline change
        const stillExists = graphRef.current && nodes.some(n => n.id === focusedNodeId);
        if (!stillExists) {
          clearFocusedNode();
          return;
        }
        
        try {
          graphRef.current?.centerGraph([focusedNodeId]);
          graphRef.current?.zoomIn?.();
        } catch (error) {
          console.warn("Failed to center on node:", error);
        }
        setTimeout(() => clearFocusedNode(), 1500);
      }, 400); // Increased delay to ensure graph is fully rendered
      
      return () => clearTimeout(timeoutId);
    }
  }, [focusedNodeId, clearFocusedNode, visibleNodeIds, nodes, timelineEnabled]);

  // Get connection count
  const getNodeConnections = useCallback((nodeId: string): number => {
    return edges.filter(e => e.source === nodeId || e.target === nodeId).length;
  }, [edges]);

  // Tooltip handlers
  const handleNodePointerOver = useCallback((node: { id: string; label?: string; data?: unknown }, event: { nativeEvent: { clientX: number; clientY: number } }) => {
    const originalNode = nodes.find(n => n.id === node.id);
    if (!originalNode) return;
    
    setTooltip({
      visible: true,
      x: event.nativeEvent.clientX,
      y: event.nativeEvent.clientY,
      node: {
        label: originalNode.label,
        type: originalNode.type,
        centrality: centralityScores[originalNode.label] || 0,
        properties: originalNode.properties || {},
        connections: getNodeConnections(node.id),
        date: originalNode.date,
        dateDescription: originalNode.dateDescription,
      },
    });
  }, [nodes, centralityScores, getNodeConnections]);

  const handleNodePointerOut = useCallback(() => {
    setTooltip(prev => ({ ...prev, visible: false }));
  }, []);

  // Node size based on centrality
  const getNodeSize = (nodeLabel: string): number => {
    const score = centralityScores[nodeLabel] || 0;
    const minSize = 4;
    const maxSize = 16;
    const scaledSize = minSize + (score * 2) * (maxSize - minSize);
    return Math.min(maxSize, Math.max(minSize, scaledSize));
  };

  // Transform nodes for reagraph
  const graphNodes = nodes
    .filter(node => visibleNodeIds.has(node.id))
    .map((node) => {
      const nodeType = node.type.toLowerCase();
      const color = NODE_COLORS[nodeType] || NODE_COLORS.default;
      const size = getNodeSize(node.label);
      
      return {
        id: node.id,
        label: node.label,
        fill: color,
        size: size,
        data: { 
          type: nodeType,
          centrality: centralityScores[node.label] || 0,
          properties: node.properties || {},
          date: node.date,
          dateDescription: node.dateDescription,
        }
      };
    });

  // Transform edges for reagraph
  const graphEdges = edges
    .filter(edge => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
    }));

  // Controls
  const handleZoomIn = useCallback(() => graphRef.current?.zoomIn?.(), []);
  const handleZoomOut = useCallback(() => graphRef.current?.zoomOut?.(), []);
  const handleCenter = useCallback(() => graphRef.current?.centerGraph?.(), []);
  const handleFit = useCallback(() => graphRef.current?.fitNodesInView?.(), []);

  if (!currentInvestigation) {
    return null;
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Clean Header */}
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex items-center justify-between shadow-sm">
        <div>
          <h2 className="text-base font-semibold text-gray-800 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            Knowledge Graph
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {graphNodes.length} entities • {graphEdges.length} connections
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* View Toggle */}
          <div className="flex items-center bg-gray-100 rounded-lg p-0.5">
            <button
              onClick={() => setIs3D(false)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                !is3D 
                  ? "bg-white text-gray-800 shadow-sm" 
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              2D
            </button>
            <button
              onClick={() => setIs3D(true)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                is3D 
                  ? "bg-white text-gray-800 shadow-sm" 
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              3D
            </button>
          </div>

          {/* Refresh */}
          <button
            onClick={refreshGraph}
            className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Graph Area */}
        <div className="flex-1 relative bg-[#FAFBFC]">
          {/* Subtle Grid */}
          <div 
            className="absolute inset-0 opacity-40"
            style={{
              backgroundImage: `
                linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px)
              `,
              backgroundSize: '40px 40px'
            }}
          />

          {nodes.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center p-8">
                <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-gray-700 mb-1">No Graph Data</h3>
                <p className="text-xs text-gray-500 max-w-xs mx-auto">
                  Upload evidence files to extract entities and build the knowledge graph.
                </p>
              </div>
            </div>
          ) : (
            <>
              <GraphCanvas
                ref={graphRef}
                nodes={graphNodes}
                edges={graphEdges}
                theme={lightTheme}
                layoutType={is3D ? "forceDirected3d" : "forceDirected2d"}
                labelType="all"
                draggable
                cameraMode={is3D ? "rotate" : "pan"}
                layoutOverrides={{ 
                  nodeStrength: -600, 
                  linkDistance: 150 
                }}
                onNodePointerOver={handleNodePointerOver}
                onNodePointerOut={handleNodePointerOut}
                actives={focusedNodeId ? [focusedNodeId] : undefined}
              />

              {/* Tooltip */}
              {tooltip.visible && tooltip.node && (
                <div
                  className="fixed z-50 pointer-events-none"
                  style={{
                    left: tooltip.x + 12,
                    top: tooltip.y + 12,
                  }}
                >
                  <div className="bg-white rounded-lg border border-gray-200 p-3 shadow-lg min-w-[200px] max-w-[280px]">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2 mb-2 pb-2 border-b border-gray-100">
                      <h3 className="text-sm font-semibold text-gray-800 leading-tight">
                        {tooltip.node.label}
                      </h3>
                      <span 
                        className="px-1.5 py-0.5 text-[10px] font-semibold uppercase rounded"
                        style={{
                          backgroundColor: `${NODE_COLORS[tooltip.node.type.toLowerCase()] || NODE_COLORS.default}15`,
                          color: NODE_COLORS[tooltip.node.type.toLowerCase()] || NODE_COLORS.default,
                        }}
                      >
                        {tooltip.node.type}
                      </span>
                    </div>

                    {/* Stats */}
                    <div className="grid grid-cols-2 gap-2 mb-2">
                      <div className="bg-gray-50 rounded px-2 py-1.5">
                        <p className="text-[9px] text-gray-500 uppercase">Connections</p>
                        <p className="text-sm font-semibold text-gray-800">{tooltip.node.connections}</p>
                      </div>
                      <div className="bg-gray-50 rounded px-2 py-1.5">
                        <p className="text-[9px] text-gray-500 uppercase">Importance</p>
                        <p className="text-sm font-semibold text-blue-600">
                          {(tooltip.node.centrality * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>

                    {/* Date if available */}
                    {tooltip.node.date && (
                      <div className="bg-amber-50 rounded px-2 py-1.5 mb-2">
                        <p className="text-[9px] text-amber-600 uppercase">Date</p>
                        <p className="text-xs font-medium text-amber-800">
                          {tooltip.node.dateDescription || new Date(tooltip.node.date).toLocaleDateString()}
                        </p>
                      </div>
                    )}

                    {/* Properties */}
                    {Object.keys(tooltip.node.properties).length > 0 && (
                      <div className="pt-2 border-t border-gray-100">
                        <p className="text-[9px] text-gray-500 uppercase mb-1">Details</p>
                        <div className="space-y-0.5">
                          {Object.entries(tooltip.node.properties)
                            .filter(([key]) => !['name', 'investigation_id', 'date', 'date_description', 'temporal_order'].includes(key))
                            .slice(0, 3)
                            .map(([key, value]) => (
                              <div key={key} className="flex justify-between text-[10px]">
                                <span className="text-gray-500 capitalize">{key.replace(/_/g, ' ')}</span>
                                <span className="text-gray-700 font-medium truncate max-w-[120px]">
                                  {String(value)}
                                </span>
                              </div>
                            ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Controls */}
              <div className="absolute top-3 right-3 bg-white rounded-lg border border-gray-200 shadow-sm p-1 flex flex-col gap-0.5">
                <button
                  onClick={handleZoomIn}
                  className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
                  title="Zoom In"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                </button>
                <button
                  onClick={handleZoomOut}
                  className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
                  title="Zoom Out"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                  </svg>
                </button>
                <div className="border-t border-gray-200 my-0.5" />
                <button
                  onClick={handleCenter}
                  className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
                  title="Center"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5v14" />
                  </svg>
                </button>
                <button
                  onClick={handleFit}
                  className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
                  title="Fit to View"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  </svg>
                </button>
              </div>

              {/* Timeline Panel */}
              {timelineData.hasTimeline && (
                <div className="absolute bottom-3 left-1/2 -translate-x-1/2 w-[50%] max-w-[500px] bg-white rounded-lg border border-gray-200 shadow-sm p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="text-xs font-semibold text-gray-700">Timeline</span>
                    </div>
                    
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          setTimelineEnabled(!timelineEnabled);
                          if (!timelineEnabled) setTimelinePosition(0);
                          else setTimelinePosition(100);
                        }}
                        className={`px-2 py-1 text-[10px] font-semibold rounded transition-all ${
                          timelineEnabled
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        }`}
                      >
                        {timelineEnabled ? 'ON' : 'OFF'}
                      </button>

                      {timelineEnabled && (
                        <button
                          onClick={() => {
                            if (timelinePosition >= 100) setTimelinePosition(0);
                            setIsPlaying(!isPlaying);
                          }}
                          className="w-6 h-6 flex items-center justify-center bg-amber-500 text-white rounded hover:bg-amber-600 transition-colors"
                        >
                          {isPlaying ? (
                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                              <rect x="6" y="4" width="4" height="16" />
                              <rect x="14" y="4" width="4" height="16" />
                            </svg>
                          ) : (
                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M8 5v14l11-7z" />
                            </svg>
                          )}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Date Display */}
                  {timelineEnabled && currentTimelineDate && (
                    <div className="text-center mb-2">
                      <span className="text-sm font-semibold text-gray-800">
                        {currentTimelineDate.toLocaleDateString('en-US', { 
                          year: 'numeric', 
                          month: 'short', 
                          day: 'numeric' 
                        })}
                      </span>
                    </div>
                  )}

                  {/* Slider */}
                  <div className="relative">
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-blue-400 to-amber-500 transition-all duration-100"
                        style={{ width: `${timelineEnabled ? timelinePosition : 100}%` }}
                      />
                    </div>
                    
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={timelineEnabled ? timelinePosition : 100}
                      onChange={(e) => {
                        if (timelineEnabled) {
                          setIsPlaying(false);
                          setTimelinePosition(Number(e.target.value));
                        }
                      }}
                      disabled={!timelineEnabled}
                      className="absolute inset-0 w-full h-1.5 opacity-0 cursor-pointer disabled:cursor-not-allowed"
                    />
                    
                    {timelineEnabled && (
                      <div 
                        className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-amber-500 rounded-full border-2 border-white shadow transition-all duration-100 pointer-events-none"
                        style={{ left: `calc(${timelinePosition}% - 6px)` }}
                      />
                    )}
                  </div>

                  {/* Date Range */}
                  <div className="flex justify-between mt-1 text-[9px] text-gray-500">
                    <span>{timelineData.minDate?.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                    <span>{timelineData.maxDate?.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                  </div>

                  {/* Stats */}
                  {timelineEnabled && (
                    <div className="flex justify-center gap-4 mt-2 pt-2 border-t border-gray-100">
                      <div className="text-center">
                        <span className="text-sm font-semibold text-blue-600">{graphNodes.length}</span>
                        <span className="text-[9px] text-gray-500 block">Visible</span>
                      </div>
                      <div className="text-center">
                        <span className="text-sm font-semibold text-gray-400">{nodes.length - graphNodes.length}</span>
                        <span className="text-[9px] text-gray-500 block">Hidden</span>
                      </div>
                      <div className="text-center">
                        <span className="text-sm font-semibold text-amber-500">{timelineData.sortedDates.length}</span>
                        <span className="text-[9px] text-gray-500 block">Events</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Legend Sidebar */}
        <div className="w-48 bg-white border-l border-gray-200 p-4 overflow-y-auto">
          <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-3">Entity Types</h3>
          <div className="space-y-2">
            {Object.entries(NODE_COLORS)
              .filter(([k]) => k !== "default")
              .map(([type, color]) => (
                <div key={type} className="flex items-center gap-2">
                  <div 
                    className="w-3 h-3 rounded-full flex-shrink-0" 
                    style={{ backgroundColor: color }} 
                  />
                  <span className="text-xs text-gray-600 capitalize">{type}</span>
                </div>
              ))}
          </div>
          
          {/* Size Legend */}
          <div className="mt-6 pt-4 border-t border-gray-100">
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-3">Node Size</h3>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-gray-400" />
                <span className="text-xs text-gray-500">Low importance</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full bg-gray-400" />
                <span className="text-xs text-gray-500">High importance</span>
              </div>
            </div>
          </div>

          {/* View Mode */}
          <div className="mt-6 pt-4 border-t border-gray-100">
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">View Mode</h3>
            <p className="text-xs text-gray-500">
              {is3D ? "3D Perspective" : "2D Flat View"}
            </p>
          </div>

          {/* Tips */}
          <div className="mt-6 pt-4 border-t border-gray-100">
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">Tips</h3>
            <ul className="text-[10px] text-gray-500 space-y-1">
              <li>• Hover nodes for details</li>
              <li>• Drag to reposition</li>
              <li>• Scroll to zoom</li>
              <li>• Click entities in chat</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
