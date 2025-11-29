"use client";

import { useState } from "react";
import { useInvestigation } from "@/context/InvestigationContext";

export function Sidebar() {
  const {
    investigations,
    currentInvestigation,
    createNewInvestigation,
    selectInvestigation,
    deleteInvestigation,
  } = useInvestigation();

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // Format date
  const formatDate = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
  };

  // Group investigations by date
  const groupedInvestigations = investigations.reduce((acc, inv) => {
    const dateKey = formatDate(inv.createdAt);
    if (!acc[dateKey]) acc[dateKey] = [];
    acc[dateKey].push(inv);
    return acc;
  }, {} as Record<string, typeof investigations>);

  if (isCollapsed) {
    return (
      <aside className="fixed left-0 top-0 h-screen w-16 bg-[#1a1a1a] flex flex-col items-center py-4 z-30">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-10 h-10 bg-white text-[#1a1a1a] flex items-center justify-center mb-4 hover:bg-[#fbbf24] transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
        </button>

        <button
          onClick={createNewInvestigation}
          className="w-10 h-10 bg-[#fbbf24] text-[#1a1a1a] flex items-center justify-center mb-4 hover:bg-[#f59e0b] transition-colors"
          title="New Investigation"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </aside>
    );
  }

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-[#1a1a1a] flex flex-col z-30">
      {/* Header */}
      <div className="p-4 border-b border-[#333]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#fbbf24] flex items-center justify-center">
              <svg className="w-5 h-5 text-[#1a1a1a]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <span className="text-white font-bold text-lg">Sherlock</span>
          </div>
          <button
            onClick={() => setIsCollapsed(true)}
            className="p-1.5 text-[#888] hover:text-white transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        </div>
      </div>

      {/* New Investigation Button */}
      <div className="p-3">
        <button
          onClick={createNewInvestigation}
          className="w-full py-2.5 px-4 bg-transparent border border-[#444] text-white font-medium flex items-center gap-2 hover:bg-[#333] transition-colors rounded-lg"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Investigation
        </button>
      </div>

      {/* Investigation List */}
      <div className="flex-1 overflow-y-auto px-2 custom-scrollbar">
        {Object.entries(groupedInvestigations).map(([dateKey, invs]) => (
          <div key={dateKey} className="mb-4">
            <p className="text-xs text-[#666] px-2 py-2 font-medium">{dateKey}</p>
            <div className="space-y-0.5">
              {invs.map((inv) => (
                <div
                  key={inv.id}
                  className="relative group"
                  onMouseEnter={() => setHoveredId(inv.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  <button
                    onClick={() => selectInvestigation(inv.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors text-sm ${
                      currentInvestigation?.id === inv.id
                        ? "bg-[#333] text-white"
                        : "text-[#999] hover:bg-[#2a2a2a] hover:text-white"
                    }`}
                  >
                    <p className="truncate pr-6">{inv.title}</p>
                  </button>
                  
                  {/* Delete button */}
                  {hoveredId === inv.id && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteInvestigation(inv.id);
                      }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#666] hover:text-red-400 transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}

        {investigations.length === 0 && (
          <div className="px-3 py-8 text-center">
            <p className="text-[#666] text-sm">No investigations yet</p>
            <p className="text-[#555] text-xs mt-1">Click &quot;New Investigation&quot; to start</p>
          </div>
        )}
      </div>

      {/* User */}
      <div className="p-3 border-t border-[#333]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-[#333] rounded-full flex items-center justify-center text-white text-sm font-medium">
            D
          </div>
          <span className="text-white text-sm">Detective</span>
        </div>
      </div>
    </aside>
  );
}
