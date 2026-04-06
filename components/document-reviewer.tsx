"use client"

import { useState, useCallback } from "react"
import type { DocumentData, ComplianceSegment, AnalysisJob } from "@/lib/types"
import { cn } from "@/lib/utils"
import { SegmentTable } from "@/components/segment-table"
import { TextViewer } from "@/components/text-viewer"
import { ChunkViewer } from "@/components/chunk-viewer"
import { BpmnViewer } from "@/components/bpmn-viewer"
import { DocumentSelector, type AnalyzeParams } from "@/components/document-selector"
import { ManageDocuments } from "@/components/manage-documents"
import { HistoryView } from "@/components/history-view"
import { AnalysisLoading } from "@/components/analysis-loading"
import dynamic from "next/dynamic"

const ResizablePanelGroup = dynamic(
  () => import("@/components/ui/resizable").then((m) => m.ResizablePanelGroup),
  { ssr: false }
)
const ResizablePanel = dynamic(
  () => import("@/components/ui/resizable").then((m) => m.ResizablePanel),
  { ssr: false }
)
const ResizableHandle = dynamic(
  () => import("@/components/ui/resizable").then((m) => m.ResizableHandle),
  { ssr: false }
)
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { ArrowLeft } from "lucide-react"

type AppState =
  | { phase: "select" }
  | { phase: "manage-documents" }
  | { phase: "history" }
  | { phase: "results"; data: DocumentData }
  | { phase: "error"; message: string }

function LoadingSkeleton() {
  return (
    <div className="flex h-full">
      <div className="w-[320px] border-r p-4 flex flex-col gap-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3 w-56" />
        <div className="flex flex-col gap-2 mt-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))}
        </div>
      </div>
      <div className="flex-1 border-r p-6 flex flex-col gap-3">
        <Skeleton className="h-5 w-64" />
        <div className="flex flex-col gap-2 mt-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full rounded" />
          ))}
        </div>
      </div>
      <div className="w-[320px] p-6 flex flex-col gap-3">
        <Skeleton className="h-5 w-52" />
        <div className="flex flex-col gap-3 mt-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  )
}

interface ComplianceVerifierProps {
  initialData?: DocumentData | null
  onBackToSelector?: () => void
}

export function ComplianceVerifier({ initialData, onBackToSelector }: ComplianceVerifierProps) {
  const [state, setState] = useState<AppState>(() =>
    initialData ? { phase: "results", data: initialData } : { phase: "select" }
  )
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null)
  const [activeCategories, setActiveCategories] = useState<Set<string>>(
    () => new Set(["NON-COMPLIANT"])
  )
  const [activeFilterStates, setActiveFilterStates] = useState<Set<string>>(
    () => new Set(["consistent", "assumption", "ambiguous"])
  )
  const [jobs, setJobs] = useState<AnalysisJob[]>([])

  const updateJob = useCallback((jobId: string, updates: Partial<AnalysisJob>) => {
    setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, ...updates } : j)))
  }, [])

  const runAnalysis = useCallback(
    async (jobId: string, params: AnalyzeParams) => {
      try {
        let body: string | FormData
        let headers: HeadersInit = {}

        if (params.bpmn_file) {
          const formData = new FormData()
          formData.append("bpmn_file", params.bpmn_file)
          formData.append("processName", params.processName || "")
          formData.append("saveProcess", String(params.saveProcess || false))
          formData.append("regulationId", params.regulationId || "")
          body = formData
        } else {
          headers["Content-Type"] = "application/json"
          body = JSON.stringify({
            processId: params.processId,
            processText: params.processText,
            processName: params.processName,
            saveProcess: params.saveProcess,
            regulationId: params.regulationId,
          })
        }

        const res = await fetch("/api/analyze", {
          method: "POST",
          headers,
          body,
        })

        if (!res.ok) {
          const info = await res.json().catch(() => ({}))
          throw new Error(info.error || `Request failed with status ${res.status}`)
        }

        const contentType = res.headers.get("content-type") || ""

        if (contentType.includes("text/event-stream")) {
          const reader = res.body?.getReader()
          if (!reader) throw new Error("No response body")

          const decoder = new TextDecoder()
          let buffer = ""
          let resultData: DocumentData | null = null

          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split("\n")
            buffer = lines.pop() || ""

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue
              try {
                const event = JSON.parse(line.slice(6))
                if (event.type === "log") {
                  updateJob(jobId, { step: event.message })
                } else if (event.type === "error") {
                  throw new Error(event.message)
                } else if (event.type === "result") {
                  resultData = event.data
                }
              } catch (e) {
                if (e instanceof Error && e.message !== "Unexpected end of JSON input") {
                  throw e
                }
              }
            }
          }

          if (!resultData || !resultData.process || !resultData.segments || !resultData.chunks) {
            throw new Error("Invalid response: missing process, segments, or chunks data")
          }

          updateJob(jobId, { status: "done", data: resultData, step: undefined })
        } else {
          const data: DocumentData = await res.json()
          if (!data.process || !data.segments || !data.chunks) {
            throw new Error("Invalid response: missing process, segments, or chunks data")
          }
          updateJob(jobId, { status: "done", data, step: undefined })
        }
      } catch (err) {
        updateJob(jobId, {
          status: "error",
          error: err instanceof Error ? err.message : "An unknown error occurred",
          step: undefined,
        })
      }
    },
    [updateJob]
  )

  const handleAnalyze = useCallback(
    (params: AnalyzeParams) => {
      const jobId = `job-${Date.now()}`
      const pName = params.processName || params.processId || "Custom Process"
      const rName = params.regulationId || "Custom Regulation"

      const newJob: AnalysisJob = {
        id: jobId,
        processName: pName,
        regulationName: rName,
        status: "running",
        startedAt: Date.now(),
      }

      setJobs((prev) => [newJob, ...prev])
      // Run in background — don't await
      runAnalysis(jobId, params)
    },
    [runAnalysis]
  )

  const handleViewJob = useCallback((job: AnalysisJob) => {
    if (job.data) {
      setState({ phase: "results", data: job.data })
    }
  }, [])

  const handleRemoveJob = useCallback((jobId: string) => {
    setJobs((prev) => prev.filter((j) => j.id !== jobId))
  }, [])

  const handleBack = useCallback(() => {
    setState({ phase: "select" })
    setActiveSegmentId(null)
    setActiveCategories(new Set(["NON-COMPLIANT"]))
    setActiveFilterStates(new Set(["consistent", "assumption", "ambiguous"]))
    onBackToSelector?.()
  }, [onBackToSelector])

  // --- Select phase ---
  if (state.phase === "select") {
    return (
      <DocumentSelector
        onAnalyze={handleAnalyze}
        onManageDocuments={() => setState({ phase: "manage-documents" })}
        onHistory={() => setState({ phase: "history" })}
        jobs={jobs}
        onViewJob={handleViewJob}
        onRemoveJob={handleRemoveJob}
      />
    )
  }

  // --- Manage documents phase ---
  if (state.phase === "manage-documents") {
    return <ManageDocuments onBack={() => setState({ phase: "select" })} />
  }

  // --- History phase ---
  if (state.phase === "history") {
    return (
      <HistoryView
        onBack={() => setState({ phase: "select" })}
        onLoadHistory={(data) => setState({ phase: "results", data })}
      />
    )
  }

  // --- Error phase ---
  if (state.phase === "error") {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center flex flex-col items-center gap-4">
          <p className="text-sm font-medium text-destructive">
            Analysis Failed
          </p>
          <p className="text-xs text-muted-foreground max-w-sm">
            {state.message}
          </p>
          <Button variant="outline" size="sm" onClick={handleBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Selection
          </Button>
        </div>
      </div>
    )
  }

  // --- Results phase ---
  const { data } = state

    const sortedSegments = [...data.segments].sort((a, b) => {
    // Push unmatched segments (process_id = -1) to the end
    if (a.process_id === -1 && b.process_id === -1) return 0
    if (a.process_id === -1) return 1
    if (b.process_id === -1) return -1
    return a.process_id - b.process_id
  })

  // Helper: compute filter state for a segment (mirrors segment-table logic)
  function getSegmentFilterState(s: ComplianceSegment): "consistent" | "assumption" | "ambiguous" {
      if (s.s3_resolution === "strictness") return "ambiguous"
    if (s.s4_compliance_category && s.s4_compliance_category !== s.category) return "ambiguous"
    if (s.s4_assumption_needed === "Yes") return "assumption"
    return "consistent"
  }

  const filteredSegments = sortedSegments.filter((s) =>
    s.category && s.category !== "nan" &&
    activeCategories.has(s.category) && activeFilterStates.has(getSegmentFilterState(s))
  )

  const categoryCounts: Record<string, number> = {}
  for (const s of sortedSegments) {
    categoryCounts[s.category] = (categoryCounts[s.category] || 0) + 1
  }

  const filterStateCounts: Record<string, number> = {}
  for (const s of sortedSegments) {
    const fs = getSegmentFilterState(s)
    filterStateCounts[fs] = (filterStateCounts[fs] || 0) + 1
  }

  const toggleCategory = (category: string) => {
    setActiveCategories((prev) => {
      const next = new Set(prev)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  const toggleFilterState = (filterState: string) => {
    setActiveFilterStates((prev) => {
      const next = new Set(prev)
      if (next.has(filterState)) next.delete(filterState)
      else next.add(filterState)
      return next
    })
  }

  const handleSegmentClick = (segment: ComplianceSegment) => {
    setActiveSegmentId((prev) => (prev === segment.id ? null : segment.id))
  }

  // Get BPMN element ID from active segment
  const activeSegment = sortedSegments.find(s => s.id === activeSegmentId)
  const highlightedBpmnElementId = activeSegment?.matched_bpmn_element_id ?? null
  const complianceReport = activeSegment?.compliance_report?.trim()

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b bg-muted/30 px-4 py-2 flex items-center">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleBack}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1 h-3.5 w-3.5" />
          New Analysis
        </Button>
      </div>
      <div className="flex-1 min-h-0">
        <ResizablePanelGroup direction="horizontal" className="h-full">
          <ResizablePanel defaultSize={30} minSize={20} maxSize={40}>
            <div className="h-full overflow-hidden">
              <SegmentTable
                segments={filteredSegments}
                activeSegmentId={activeSegmentId}
                onSegmentClick={handleSegmentClick}
                activeCategories={activeCategories}
                onToggleCategory={toggleCategory}
                categoryCounts={categoryCounts}
                activeFilterStates={activeFilterStates}
                onToggleFilterState={toggleFilterState}
                filterStateCounts={filterStateCounts}
              />
            </div>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={40} minSize={25}>
            <ResizablePanelGroup direction="vertical" className="h-full">
              <ResizablePanel defaultSize={50} minSize={25}>
                <div className="h-full overflow-hidden">
                  <TextViewer
                    process={data.process}
                    segments={data.segments}
                    activeSegmentId={activeSegmentId}
                  />
                </div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel defaultSize={50} minSize={20}>
                <div className="h-full border-t bg-card">
                  <div className="px-3 py-2 border-b text-xs font-medium text-muted-foreground">
                    BPMN Model
                  </div>
                  <div className="h-[calc(100%-33px)]">
                    <BpmnViewer
                      bpmnXml={data.bpmnXml}
                      highlightedElementId={highlightedBpmnElementId}
                    />
                  </div>
                </div>
              </ResizablePanel>
            </ResizablePanelGroup>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={30} minSize={20}>
            <div className="h-full overflow-hidden border-l bg-card">
              <ResizablePanelGroup direction="vertical" className="h-full">
                <ResizablePanel defaultSize={50} minSize={20}>
                  <div className="h-full overflow-hidden flex flex-col">
                    <div className="px-3 py-2 border-b shrink-0">
                      <span className="text-xs font-medium text-muted-foreground">Regulatory Document</span>
                    </div>
                    <div className="flex-1 min-h-0 overflow-auto">
                      <ChunkViewer
                        chunks={data.chunks}
                        segments={data.segments}
                        activeSegmentId={activeSegmentId}
                      />
                    </div>
                  </div>
                </ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={50} minSize={15}>
                  <div className="h-full overflow-hidden flex flex-col border-t">
                    <div className="px-3 py-2 border-b shrink-0">
                      <span className="text-xs font-medium text-muted-foreground">Reasoning Report</span>
                    </div>
                    <div className="flex-1 min-h-0 overflow-auto p-4">
                      {!activeSegmentId ? (
                        <p className="text-sm text-muted-foreground">
                          Select a segment to view its compliance reasoning report.
                        </p>
                      ) : (
                        <div className="space-y-4">
                          {/* S3 Reasoning */}
                          {(activeSegment?.s3_reasoning_1 || activeSegment?.s3_reasoning_2) && (
                            <div className="space-y-2">
                              <h4 className="text-xs font-semibold text-foreground">S3 Analysis</h4>
                              {activeSegment.s3_category_1 === activeSegment.s3_category_2 ? (
                                // Both runs agree
                                <div className="text-xs text-foreground leading-relaxed">
                                  <span className="font-medium">{activeSegment.s3_category_1}:</span> {activeSegment.s3_reasoning_1}
                                </div>
                              ) : (
                                // Runs disagree — show both
                                <div className="space-y-2">
                                  {activeSegment.s3_reasoning_1 && (
                                    <div className={cn(
                                      "text-xs leading-relaxed px-2 py-1 rounded",
                                      activeSegment.s3_category_1 === "COMPLIANT" ? "bg-emerald-100 text-emerald-900" :
                                      activeSegment.s3_category_1 === "NON-COMPLIANT" ? "bg-red-100 text-red-900" :
                                      "bg-neutral-100 text-neutral-900"
                                    )}>
                                      <span className="font-medium">{activeSegment.s3_category_1} (Run 1):</span> {activeSegment.s3_reasoning_1}
                                    </div>
                                  )}
                                  {activeSegment.s3_reasoning_2 && (
                                    <div className={cn(
                                      "text-xs leading-relaxed px-2 py-1 rounded",
                                      activeSegment.s3_category_2 === "COMPLIANT" ? "bg-emerald-100 text-emerald-900" :
                                      activeSegment.s3_category_2 === "NON-COMPLIANT" ? "bg-red-100 text-red-900" :
                                      "bg-neutral-100 text-neutral-900"
                                    )}>
                                      <span className="font-medium">{activeSegment.s3_category_2} (Run 2):</span> {activeSegment.s3_reasoning_2}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Assumptions needed */}
                          {activeSegment?.s4_assumption_needed === "Yes" && (
                            <div className="space-y-2 border-t pt-3">
                              <div className="flex items-center gap-1">
                                <span className="text-orange-500 font-bold">⚠</span>
                                <h4 className="text-xs font-semibold text-orange-700">Assumptions needed</h4>
                              </div>
                              {activeSegment.s4_ambiguous_term && activeSegment.s4_ambiguous_term !== "None" && (
                                <div className="text-xs text-foreground">
                                  <span className="font-medium">Ambiguous term:</span> "{activeSegment.s4_ambiguous_term}"
                                </div>
                              )}
                              {activeSegment.s4_mapped_evidence && activeSegment.s4_mapped_evidence !== "None" && (
                                <div className="text-xs text-foreground">
                                  <span className="font-medium">Mapped evidence:</span> {activeSegment.s4_mapped_evidence}
                                </div>
                              )}
                              {activeSegment.s4_assumption && activeSegment.s4_assumption !== "None" && (
                                <div className={cn(
                                  "text-xs leading-relaxed px-2 py-1 rounded",
                                  activeSegment.s4_compliance_category === "COMPLIANT" ? "bg-emerald-100 text-emerald-900" :
                                  activeSegment.s4_compliance_category === "NON-COMPLIANT" ? "bg-red-100 text-red-900" :
                                  "bg-orange-100 text-orange-900"
                                )}>
                                  <span className="font-medium">Assumption ({activeSegment.s4_compliance_category}):</span> {activeSegment.s4_assumption}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Confidence Scores */}
                          {(activeSegment?.s3_category_confidence_1 || activeSegment?.s3_category_confidence_2) && (
                            <div className="border-t pt-3 space-y-1">
                              <h4 className="text-xs font-semibold text-muted-foreground">Confidence Scores</h4>
                              {activeSegment.s3_category_confidence_1 && (
                                <div className="text-xs text-muted-foreground">
                                  Run 1: {(activeSegment.s3_category_confidence_1 * 100).toFixed(0)}%
                                </div>
                              )}
                              {activeSegment.s3_category_confidence_2 && (
                                <div className="text-xs text-muted-foreground">
                                  Run 2: {(activeSegment.s3_category_confidence_2 * 100).toFixed(0)}%
                                </div>
                              )}
                            </div>
                          )}

                          {/* Fallback to compliance_report if available */}
                          {complianceReport && !activeSegment?.s3_reasoning_1 && (
                            <div className="text-xs leading-relaxed">
                              <pre className="whitespace-pre-wrap break-words font-sans">
                                {complianceReport}
                              </pre>
                            </div>
                          )}

                          {!complianceReport && !activeSegment?.s3_reasoning_1 && (
                            <p className="text-sm text-muted-foreground">
                              No detailed reasoning available for this segment.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </ResizablePanel>
              </ResizablePanelGroup>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  )
}
