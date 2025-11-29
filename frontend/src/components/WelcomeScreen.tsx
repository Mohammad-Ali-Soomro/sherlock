"use client";

import { useInvestigation } from "@/context/InvestigationContext";

export function WelcomeScreen() {
  const { createNewInvestigation } = useInvestigation();

  return (
    <div className="h-full flex items-center justify-center bg-[#fafafa]">
      <div className="text-center max-w-md px-6">
        {/* Logo */}
        <div className="w-16 h-16 mx-auto mb-6 bg-[#1a1a1a] flex items-center justify-center">
          <svg className="w-10 h-10 text-[#fbbf24]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <h1 className="text-2xl font-bold text-[#1a1a1a] mb-2">
          Welcome to Sherlock
        </h1>
        <p className="text-[#666] mb-8">
          Your AI-powered crime investigation assistant. Upload evidence, build knowledge graphs, and uncover hidden connections.
        </p>

        <button
          onClick={createNewInvestigation}
          className="px-6 py-3 bg-[#1a1a1a] text-white font-medium rounded-xl hover:bg-[#333] transition-colors inline-flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Start New Investigation
        </button>

        {/* Features */}
        <div className="mt-12 grid grid-cols-3 gap-6 text-left">
          <div>
            <div className="w-10 h-10 bg-[#f0f0f0] rounded-lg flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-[#666]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-sm font-medium text-[#1a1a1a] mb-1">Upload Evidence</h3>
            <p className="text-xs text-[#666]">Import documents, reports, and witness statements</p>
          </div>

          <div>
            <div className="w-10 h-10 bg-[#f0f0f0] rounded-lg flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-[#666]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
            </div>
            <h3 className="text-sm font-medium text-[#1a1a1a] mb-1">Build Graphs</h3>
            <p className="text-xs text-[#666]">AI extracts entities and maps relationships</p>
          </div>

          <div>
            <div className="w-10 h-10 bg-[#f0f0f0] rounded-lg flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-[#666]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h3 className="text-sm font-medium text-[#1a1a1a] mb-1">Ask Questions</h3>
            <p className="text-xs text-[#666]">Query the network with natural language</p>
          </div>
        </div>
      </div>
    </div>
  );
}
