"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useInvestigation } from "@/context/InvestigationContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Helper to render message content with clickable entity names
function RenderMessageWithEntities({
  content,
  nodes,
  onEntityClick,
  isUserMessage,
}: {
  content: string;
  nodes: { label: string }[];
  onEntityClick: (entityName: string) => void;
  isUserMessage: boolean;
}) {
  // Sort nodes by label length (longest first) to match longer names before shorter ones
  const sortedNodes = [...nodes].sort((a, b) => b.label.length - a.label.length);
  
  // Build regex to match all entity names (case insensitive)
  if (sortedNodes.length === 0) {
    return <>{content}</>;
  }
  
  // Escape special regex characters in entity names
  const escapeRegex = (str: string) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = sortedNodes.map(n => escapeRegex(n.label)).join('|');
  const regex = new RegExp(`(${pattern})`, 'gi');
  
  const parts = content.split(regex);
  
  return (
    <>
      {parts.map((part, index) => {
        // Check if this part matches any entity (case insensitive)
        const matchedNode = sortedNodes.find(
          n => n.label.toLowerCase() === part.toLowerCase()
        );
        
        if (matchedNode) {
          return (
            <button
              key={index}
              onClick={() => onEntityClick(matchedNode.label)}
              className={`inline font-semibold underline decoration-dotted underline-offset-2 cursor-pointer transition-all hover:decoration-solid ${
                isUserMessage 
                  ? "text-[#00f3ff] hover:text-[#66f7ff]" 
                  : "text-[#00f3ff] hover:text-[#00d4e0]"
              }`}
              title={`Click to focus on ${matchedNode.label} in graph`}
            >
              {part}
            </button>
          );
        }
        
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

export function ChatView() {
  const {
    currentInvestigation,
    addMessage,
    isLoading,
    setIsLoading,
    refreshGraph,
    focusOnNode,
  } = useInvestigation();

  const [inputValue, setInputValue] = useState("");
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentInvestigation?.messages]);

  // Handle sending message
  const handleSend = async () => {
    if (!inputValue.trim() || isLoading || !currentInvestigation) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setIsLoading(true);

    // Add user message
    addMessage({ role: "user", content: userMessage });

    try {
      const res = await fetch(`${API_URL}/detective/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          question: userMessage,
          investigation_id: currentInvestigation.id 
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      
      // Extract entities mentioned in response
      const entities = currentInvestigation.nodes
        .filter((n) => data.answer.toLowerCase().includes(n.label.toLowerCase()))
        .map((n) => n.label);

      addMessage({
        role: "assistant",
        content: data.answer,
        entities: entities.length > 0 ? entities : undefined,
      });
    } catch (err) {
      addMessage({
        role: "assistant",
        content: `⚠️ Error: ${err instanceof Error ? err.message : "Failed to get response"}. Make sure the backend is running.`,
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Handle file upload
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !currentInvestigation) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
      const text = e.target?.result as string;
      if (!text) {
        setUploadStatus("error");
        return;
      }

      setUploadStatus("uploading");
      
      // Add system message about upload
      addMessage({
        role: "system",
        content: `📎 Uploading evidence: ${file.name}...`,
      });

      try {
        const res = await fetch(`${API_URL}/ingest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            text, 
            source: file.name,
            investigation_id: currentInvestigation.id 
          }),
        });

        if (!res.ok) throw new Error(`Failed: ${res.status}`);

        const data = await res.json();
        setUploadStatus("success");
        
        // Add success message
        addMessage({
          role: "system",
          content: `✅ Evidence processed: Found ${data.nodes_created} entities and ${data.relationships_created} connections`,
        });
        
        // Refresh graph for this investigation
        await refreshGraph();

        setTimeout(() => setUploadStatus("idle"), 2000);
      } catch (err) {
        setUploadStatus("error");
        addMessage({
          role: "system",
          content: `❌ Failed to process evidence: ${err instanceof Error ? err.message : "Unknown error"}`,
        });
        setTimeout(() => setUploadStatus("idle"), 2000);
      }
    };

    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Handle keyboard
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Handle clicking on an entity name in the chat
  const handleEntityClick = useCallback((entityName: string) => {
    focusOnNode(entityName);
  }, [focusOnNode]);

  // Suggestion prompts
  const suggestions = [
    "Who was the victim?",
    "List all suspects",
    "What connections exist between entities?",
    "Summarize the case",
  ];

  if (!currentInvestigation) {
    return null;
  }

  const messages = currentInvestigation.messages;
  const showSuggestions = messages.length <= 1;
  const graphNodes = currentInvestigation.nodes;

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-3xl mx-auto px-4 py-8">
          {messages.map((message) => (
            <div key={message.id} className="mb-6">
              {message.role === "system" ? (
                <div className="flex justify-center">
                  <div className="px-4 py-2 bg-[#f0f0f0] rounded-full text-sm text-[#666]">
                    {message.content}
                  </div>
                </div>
              ) : (
                <div className={`flex gap-4 ${message.role === "user" ? "flex-row-reverse" : ""}`}>
                  {/* Avatar */}
                  <div className={`w-8 h-8 flex-shrink-0 flex items-center justify-center text-sm font-bold ${
                    message.role === "user" 
                      ? "bg-[#1a1a1a] text-white rounded-full" 
                      : "bg-[#fbbf24] text-[#1a1a1a]"
                  }`}>
                    {message.role === "user" ? "D" : "S"}
                  </div>

                  {/* Message content */}
                  <div className={`flex-1 ${message.role === "user" ? "text-right" : ""}`}>
                    <div className={`inline-block max-w-full text-left ${
                      message.role === "user"
                        ? "bg-[#1a1a1a] text-white px-4 py-3 rounded-2xl rounded-tr-sm"
                        : ""
                    }`}>
                      <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
                        <RenderMessageWithEntities
                          content={message.content}
                          nodes={graphNodes}
                          onEntityClick={handleEntityClick}
                          isUserMessage={message.role === "user"}
                        />
                      </p>

                      {message.entities && message.entities.length > 0 && (
                        <div className={`mt-3 pt-3 border-t ${message.role === "user" ? "border-[#333]" : "border-[#e0e0e0]"}`}>
                          <p className="text-xs text-[#888] flex flex-wrap gap-1.5 items-center">
                            <span>Related:</span>
                            {message.entities.map((entity, idx) => (
                              <button
                                key={idx}
                                onClick={() => handleEntityClick(entity)}
                                className="px-2 py-0.5 bg-[#00f3ff]/10 text-[#00f3ff] rounded-full text-xs hover:bg-[#00f3ff]/20 transition-colors"
                              >
                                {entity}
                              </button>
                            ))}
                          </p>
                        </div>
                      )}
                    </div>

                    <p className="text-[11px] text-[#999] mt-1">
                      {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="flex gap-4 mb-6">
              <div className="w-8 h-8 bg-[#fbbf24] flex items-center justify-center text-sm font-bold text-[#1a1a1a]">
                S
              </div>
              <div className="flex items-center gap-1.5 py-3">
                <div className="w-2 h-2 bg-[#999] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 bg-[#999] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 bg-[#999] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Suggestions */}
      {showSuggestions && (
        <div className="px-4 pb-4">
          <div className="max-w-3xl mx-auto">
            <div className="grid grid-cols-2 gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInputValue(suggestion)}
                  className="px-4 py-3 text-left text-sm bg-white border border-[#e0e0e0] rounded-xl hover:bg-[#f5f5f5] transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-[#e0e0e0] bg-white p-4">
        <div className="max-w-3xl mx-auto">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.json,.csv"
            onChange={handleFileUpload}
            className="hidden"
          />
          
          <div className="relative flex items-center gap-2">
            {/* Upload button (like ChatGPT's attachment) */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading || uploadStatus === "uploading"}
              className="flex-shrink-0 p-2.5 text-[#666] hover:text-[#1a1a1a] hover:bg-[#f0f0f0] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Upload evidence file"
            >
              {uploadStatus === "uploading" ? (
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              )}
            </button>

            {/* Text input */}
            <div className="relative flex-1">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about the investigation..."
                disabled={isLoading}
                rows={1}
                className="w-full px-4 py-3 pr-12 bg-[#f5f5f5] border border-[#e0e0e0] rounded-xl resize-none text-[15px] placeholder:text-[#999] focus:outline-none focus:border-[#999] disabled:opacity-50"
                style={{ minHeight: "48px", maxHeight: "200px" }}
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !inputValue.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-[#1a1a1a] text-white rounded-lg disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#333] transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
          <p className="text-[11px] text-[#999] text-center mt-2">
            Sherlock can make mistakes. Verify important information.
          </p>
        </div>
      </div>
    </div>
  );
}
