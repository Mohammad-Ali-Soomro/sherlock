"use client";

import { Sidebar } from "@/components/Sidebar";
import { ChatView } from "@/components/ChatView";
import { GraphView } from "@/components/GraphViewNew";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { useInvestigation } from "@/context/InvestigationContext";

function MainContent() {
  const { currentInvestigation, currentView, setCurrentView } = useInvestigation();

  // No investigation selected - show welcome
  if (!currentInvestigation) {
    return <WelcomeScreen />;
  }

  return (
    <div className="h-full flex flex-col">
      {/* View Toggle Header */}
      <div className="bg-white border-b border-[#e0e0e0] px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-base font-semibold text-[#1a1a1a] truncate max-w-md">
            {currentInvestigation.title}
          </h1>
          <span className="text-xs text-[#999] bg-[#f5f5f5] px-2 py-1 rounded">
            {currentInvestigation.messages.length - 1} messages
          </span>
        </div>

        {/* View Toggle */}
        <div className="flex items-center bg-[#f5f5f5] rounded-lg p-1">
          <button
            onClick={() => setCurrentView("chat")}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              currentView === "chat"
                ? "bg-white text-[#1a1a1a] shadow-sm"
                : "text-[#666] hover:text-[#1a1a1a]"
            }`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Chat
            </span>
          </button>
          <button
            onClick={() => setCurrentView("graph")}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              currentView === "graph"
                ? "bg-white text-[#1a1a1a] shadow-sm"
                : "text-[#666] hover:text-[#1a1a1a]"
            }`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              Graph
              {currentInvestigation.nodes.length > 0 && (
                <span className="text-xs bg-[#fbbf24] text-[#1a1a1a] px-1.5 py-0.5 rounded-full font-bold">
                  {currentInvestigation.nodes.length}
                </span>
              )}
            </span>
          </button>
        </div>
      </div>

      {/* View Content */}
      <div className="flex-1 overflow-hidden">
        {currentView === "chat" ? <ChatView /> : <GraphView />}
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <div className="h-screen flex bg-[#fafafa]">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content */}
      <main className="flex-1 ml-64 h-full overflow-hidden">
        <MainContent />
      </main>
    </div>
  );
}
