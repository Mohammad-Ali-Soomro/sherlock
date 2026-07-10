"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Types
export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  entities?: string[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties?: Record<string, unknown>;
  date?: string;              // ISO date string for timeline
  dateDescription?: string;   // Human-readable date description
  temporalOrder?: number;     // Numeric order for sequencing
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
}

export interface Investigation {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
  messages: Message[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface InvestigationContextType {
  investigations: Investigation[];
  currentInvestigation: Investigation | null;
  currentView: "chat" | "graph";
  isLoading: boolean;
  focusedNodeId: string | null;
  
  // Actions
  createNewInvestigation: () => void;
  selectInvestigation: (id: string) => void;
  deleteInvestigation: (id: string) => void;
  updateInvestigationTitle: (id: string, title: string) => void;
  addMessage: (message: Omit<Message, "id" | "timestamp">) => void;
  setGraphData: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setCurrentView: (view: "chat" | "graph") => void;
  setIsLoading: (loading: boolean) => void;
  refreshGraph: () => Promise<void>;
  focusOnNode: (nodeLabel: string) => void;
  clearFocusedNode: () => void;
}

const InvestigationContext = createContext<InvestigationContextType | undefined>(undefined);

// Generate unique ID
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// Create welcome message
const createWelcomeMessage = (): Message => ({
  id: generateId(),
  role: "assistant",
  content: "Welcome, Detective. I'm Sherlock, your AI investigative assistant. Upload evidence files or ask me questions about the crime network. I'll analyze connections, identify suspects, and help uncover hidden patterns.",
  timestamp: new Date(),
});

// Create new investigation
const createNewInvestigationData = (): Investigation => ({
  id: generateId(),
  title: "New Investigation",
  createdAt: new Date(),
  updatedAt: new Date(),
  messages: [createWelcomeMessage()],
  nodes: [],
  edges: [],
});

export function InvestigationProvider({ children }: { children: ReactNode }) {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [currentInvestigationId, setCurrentInvestigationId] = useState<string | null>(null);
  const [currentView, setCurrentView] = useState<"chat" | "graph">("chat");
  const [isLoading, setIsLoading] = useState(false);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  // Get current investigation
  const currentInvestigation = investigations.find((inv) => inv.id === currentInvestigationId) || null;

  // Create new investigation
  const createNewInvestigation = useCallback(() => {
    const newInvestigation = createNewInvestigationData();
    setInvestigations((prev) => [newInvestigation, ...prev]);
    setCurrentInvestigationId(newInvestigation.id);
    setCurrentView("chat");
  }, []);

  // Select investigation
  const selectInvestigation = useCallback((id: string) => {
    setCurrentInvestigationId(id);
    setCurrentView("chat");
  }, []);

  // Delete investigation
  const deleteInvestigation = useCallback((id: string) => {
    setInvestigations((prev) => prev.filter((inv) => inv.id !== id));
    if (currentInvestigationId === id) {
      setCurrentInvestigationId(null);
    }
  }, [currentInvestigationId]);

  // Update investigation title
  const updateInvestigationTitle = useCallback((id: string, title: string) => {
    setInvestigations((prev) =>
      prev.map((inv) =>
        inv.id === id ? { ...inv, title, updatedAt: new Date() } : inv
      )
    );
  }, []);

  // Add message to current investigation
  const addMessage = useCallback((message: Omit<Message, "id" | "timestamp">) => {
    if (!currentInvestigationId) return;

    const newMessage: Message = {
      ...message,
      id: generateId(),
      timestamp: new Date(),
    };

    setInvestigations((prev) =>
      prev.map((inv) => {
        if (inv.id !== currentInvestigationId) return inv;
        
        // Auto-update title from first user message
        let title = inv.title;
        if (inv.title === "New Investigation" && message.role === "user") {
          title = message.content.slice(0, 40) + (message.content.length > 40 ? "..." : "");
        }

        return {
          ...inv,
          title,
          messages: [...inv.messages, newMessage],
          updatedAt: new Date(),
        };
      })
    );
  }, [currentInvestigationId]);

  // Set graph data for current investigation
  const setGraphData = useCallback((nodes: GraphNode[], edges: GraphEdge[]) => {
    if (!currentInvestigationId) return;

    setInvestigations((prev) =>
      prev.map((inv) =>
        inv.id === currentInvestigationId
          ? { ...inv, nodes, edges, updatedAt: new Date() }
          : inv
      )
    );
  }, [currentInvestigationId]);

  // Refresh graph from backend for current investigation
  const refreshGraph = useCallback(async () => {
    if (!currentInvestigationId) return;

    try {
      // Fetch graph data filtered by investigation_id
      const res = await fetch(`${API_URL}/detective/full-graph?investigation_id=${currentInvestigationId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.nodes && data.nodes.length > 0) {
          const nameToId = new Map<string, string>();
          
          const nodes: GraphNode[] = data.nodes.map((n: { id: string; label: string; type: string; properties?: Record<string, unknown> }) => {
            nameToId.set(n.label, n.id);
            // Extract date fields from properties
            const props = n.properties || {};
            return {
              id: n.id,
              label: n.label,
              type: n.type || "Entity",
              properties: n.properties,
              date: props.date as string | undefined,
              dateDescription: props.date_description as string | undefined,
              temporalOrder: props.temporal_order as number | undefined,
            };
          });

          const edges: GraphEdge[] = data.relationships.map((r: { id?: string; source: string; target: string; type: string }, idx: number) => ({
            id: r.id || `edge-${idx}`,
            source: nameToId.get(r.source) || r.source,
            target: nameToId.get(r.target) || r.target,
            label: r.type,
            type: r.type,
          }));

          setGraphData(nodes, edges);

          // Add system message
          addMessage({
            role: "system",
            content: `📊 Graph updated: ${data.total_nodes} nodes, ${data.total_relationships} relationships`,
          });
        }
      }
    } catch (err) {
      console.error("Failed to fetch graph:", err);
    }
  }, [currentInvestigationId, setGraphData, addMessage]);

  // Focus on a node by label - switches to graph view and sets focused node
  const focusOnNode = useCallback((nodeLabel: string) => {
    if (!currentInvestigation) return;
    
    // Find the node by label
    const node = currentInvestigation.nodes.find(
      (n) => n.label.toLowerCase() === nodeLabel.toLowerCase()
    );
    
    if (node) {
      setFocusedNodeId(node.id);
      setCurrentView("graph");
    }
  }, [currentInvestigation]);

  // Clear focused node
  const clearFocusedNode = useCallback(() => {
    setFocusedNodeId(null);
  }, []);

  return (
    <InvestigationContext.Provider
      value={{
        investigations,
        currentInvestigation,
        currentView,
        isLoading,
        focusedNodeId,
        createNewInvestigation,
        selectInvestigation,
        deleteInvestigation,
        updateInvestigationTitle,
        addMessage,
        setGraphData,
        setCurrentView,
        setIsLoading,
        refreshGraph,
        focusOnNode,
        clearFocusedNode,
      }}
    >
      {children}
    </InvestigationContext.Provider>
  );
}

export function useInvestigation() {
  const context = useContext(InvestigationContext);
  if (!context) {
    throw new Error("useInvestigation must be used within InvestigationProvider");
  }
  return context;
}
