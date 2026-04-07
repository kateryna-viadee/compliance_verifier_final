"use client"

import { useEffect, useRef, useMemo, useCallback } from "react"
import type { RegulationChunk, ComplianceSegment } from "@/lib/types"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn, getCategoryColor } from "@/lib/utils"
import { BookOpen } from "lucide-react"

/** Split text on a term (case-insensitive) and wrap matches in orange highlight */
function highlightTerm(text: string, term: string) {
  if (!term) return text
  const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi")
  const parts = text.split(regex)
  if (parts.length === 1) return text
  return parts.map((part, i) =>
    regex.test(part) ? (
      <span key={i} className="bg-orange-200 text-orange-900 rounded px-0.5">
        {part}
      </span>
    ) : (
      part
    )
  )
}

interface ChunkViewerProps {
  chunks: RegulationChunk[]
  segments: ComplianceSegment[]
  activeSegmentId: string | null
  ambiguousTerm?: string | null
  onSegmentSelect?: (segmentId: string) => void
}

export function ChunkViewer({
  chunks,
  segments,
  activeSegmentId,
  ambiguousTerm,
  onSegmentSelect,
}: ChunkViewerProps) {
  const highlightRef = useRef<HTMLSpanElement>(null)

  const activeChunkId = useMemo(() => {
    if (!activeSegmentId) return null
    const seg = segments.find((s) => s.id === activeSegmentId)
    return seg?.chunk_id ?? null
  }, [activeSegmentId, segments])

  /** Map chunk_id → category color for underline; pick the most severe category if multiple segments share a chunk */
  const chunkColorMap = useMemo(() => {
    const priority: Record<string, number> = { "NON-COMPLIANT": 3, "NO EVIDENCE": 2, "COMPLIANT": 1 }
    const map = new Map<string, string>()
    for (const seg of segments) {
      if (!seg.chunk_id || !seg.category) continue
      const existing = map.get(seg.chunk_id)
      if (!existing || (priority[seg.category] || 0) > (priority[existing] || 0)) {
        map.set(seg.chunk_id, seg.category)
      }
    }
    return map
  }, [segments])

  const scrollToHighlight = useCallback(() => {
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      })
    }
  }, [])

  useEffect(() => {
    if (activeChunkId) {
      const timer = setTimeout(scrollToHighlight, 50)
      return () => clearTimeout(timer)
    }
  }, [activeChunkId, scrollToHighlight])

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 border-b px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">
            Regulation Document
          </h2>
        </div>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        <article className="px-6 py-5 leading-relaxed text-sm text-foreground/90 max-w-none">
          {chunks.map((chunk, i) => {
            const isActive = chunk.chunk_id === activeChunkId
            const chunkCategory = chunkColorMap.get(chunk.chunk_id)
            const underlineColor = chunkCategory ? getCategoryColor(chunkCategory) : undefined
            return (
              <span
                key={chunk.chunk_id}
                ref={isActive ? highlightRef : undefined}
                className={cn(
                  "transition-all duration-300 whitespace-pre-wrap",
                  isActive &&
                    "bg-highlight/50 text-highlight-foreground rounded-sm ring-2 ring-highlight/60 ring-offset-1 ring-offset-background px-0.5 -mx-0.5",
                  onSegmentSelect && "cursor-pointer hover:bg-muted/50"
                )}
                style={underlineColor ? {
                  textDecoration: "underline",
                  textDecorationColor: underlineColor,
                  textUnderlineOffset: "3px",
                  textDecorationThickness: "2px",
                } : undefined}
                onClick={() => {
                  if (!onSegmentSelect) return
                  const match = segments.find((s) => s.chunk_id === chunk.chunk_id)
                  if (match) onSegmentSelect(match.id)
                }}
              >
                {ambiguousTerm ? highlightTerm(chunk.chunk_text, ambiguousTerm) : chunk.chunk_text}
                {i < chunks.length - 1 ? "\n\n" : ""}
              </span>
            )
          })}
        </article>
      </ScrollArea>
    </div>
  )
}
