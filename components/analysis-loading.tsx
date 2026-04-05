
"use client"

import { Loader2 } from "lucide-react"

interface AnalysisLoadingProps {
  step?: string
}


export function AnalysisLoading({ step }: AnalysisLoadingProps) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="flex flex-col items-center gap-6 px-6 text-center">
        <div className="relative">
          <div className="h-16 w-16 rounded-full border-4 border-muted flex items-center justify-center">
            <Loader2 className="h-8 w-8 text-primary animate-spin" />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold text-foreground">
            Running Compliance Analysis
          </h2>
          <p className="text-sm text-muted-foreground max-w-sm">
            {step || "Processing documents and evaluating compliance rules..."}
          </p>
        </div>
      </div>
    </div>
  )
}

/* add more detailed loading info* see v19*/
