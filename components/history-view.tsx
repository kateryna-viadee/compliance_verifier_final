"use client"

// History View Component - Displays past compliance analyses
import { useState } from "react"
import useSWR from "swr"
import type { HistoryItem, DocumentData } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { FileText, Calendar, ArrowRight, RefreshCw } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5005"

const fetcher = (url: string) => fetch(url).then((res) => res.json())

interface HistoryViewProps {
  onLoadHistory: (data: DocumentData) => void
}

export function HistoryView({ onLoadHistory }: HistoryViewProps) {
  const { data, isLoading, error, mutate } = useSWR<{ items: HistoryItem[] }>(
    `${API_BASE}/api/history`,
    fetcher
  )
  const [loadingId, setLoadingId] = useState<string | null>(null)

  const handleLoadItem = async (item: HistoryItem) => {
    setLoadingId(item.id)
    try {
      // Use the full item.id which contains filename|dataset_id|run_id
      const res = await fetch(`${API_BASE}/api/history/${encodeURIComponent(item.id)}`)
      if (!res.ok) {
        throw new Error(`Failed to load history: ${res.statusText}`)
      }
      const historyData: DocumentData = await res.json()
      onLoadHistory(historyData)
    } catch (err) {
      console.error("[v0] Error loading history item:", err)
      alert("Failed to load history item. Please try again.")
    } finally {
      setLoadingId(null)
    }
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="w-full max-w-2xl space-y-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="text-center space-y-4">
          <p className="text-sm text-muted-foreground">
            Failed to load history. Make sure the backend is running.
          </p>
          <Button variant="outline" onClick={() => mutate()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </div>
      </div>
    )
  }

  const items = data?.items || []

  if (items.length === 0) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="text-center space-y-2">
          <FileText className="h-12 w-12 mx-auto text-muted-foreground/50" />
          <h2 className="text-lg font-semibold text-foreground">No History Yet</h2>
          <p className="text-sm text-muted-foreground max-w-md">
            Your past compliance analyses will appear here. Run a new analysis to get started,
            or place Excel result files in the <code className="text-xs bg-muted px-1 py-0.5 rounded">backend/history/</code> folder.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-4 border-b bg-muted/30">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Analysis History</h2>
            <p className="text-xs text-muted-foreground">
              {items.length} past {items.length === 1 ? "analysis" : "analyses"} available
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => mutate()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-6 space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="group border rounded-lg p-4 bg-card hover:bg-muted/50 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-primary shrink-0" />
                    <span className="text-sm font-medium text-foreground truncate">
                      {item.process_name}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate pl-6">
                    Regulation: {item.regulation_name}
                  </p>
                  {(item.dataset_id || item.run_id) && (
                    <div className="flex items-center gap-2 pl-6">
                      {item.dataset_id && (
                        <span className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono text-muted-foreground">
                          {item.dataset_id}
                        </span>
                      )}
                      {item.run_id && (
                        <span className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono text-muted-foreground">
                          Run: {item.run_id}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-1 text-xs text-muted-foreground pl-6">
                    <Calendar className="h-3 w-3" />
                    <span>{item.date}</span>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleLoadItem(item)}
                  disabled={loadingId === item.id}
                  className="shrink-0"
                >
                  {loadingId === item.id ? (
                    <>
                      <RefreshCw className="mr-2 h-3 w-3 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      View
                      <ArrowRight className="ml-2 h-3 w-3" />
                    </>
                  )}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
