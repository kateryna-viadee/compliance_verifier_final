"use client"

import { useState } from "react"
import { ComplianceVerifier } from "@/components/document-reviewer"
import type { DocumentData } from "@/lib/types"

export default function Page() {
  const [historyData, setHistoryData] = useState<DocumentData | null>(null)

  const handleBackToSelector = () => {
    setHistoryData(null)
  }

  return (
    <main className="h-dvh flex flex-col bg-background">
      <header className="border-b bg-card px-6 py-3 flex items-center gap-3 shrink-0">
        <div className="h-7 w-7 rounded-md bg-primary flex items-center justify-center">
          <span className="text-xs font-bold text-primary-foreground">CV</span>
        </div>
        <div className="flex-1">
          <h1 className="text-sm font-semibold text-foreground">
            Compliance Verifier
          </h1>
          <p className="text-xs text-muted-foreground">
            Automated compliance verification for your processes
          </p>
        </div>
      </header>
      <div className="flex-1 min-h-0">
        <ComplianceVerifier 
          initialData={historyData} 
          onBackToSelector={handleBackToSelector}
        />
      </div>
    </main>
  )
}
