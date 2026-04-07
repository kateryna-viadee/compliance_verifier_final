/**
 *
 * Key fixes:
 *
 * 3-tier fuzzy matching — each sentence now tries: exact match → whitespace-normalized → punctuation-stripped (new). The punctuation-stripped tier removes all ., ;, ,, ', ", etc. before comparing, so minor punctuation differences between the extracted segment and the original text no longer break matching.
 * Longest-subsequence fallback — if the full sentence still doesn't match, a sliding word-window tries to find the longest contiguous run of words (≥4 words) that does match. This handles cases where the LLM slightly modified the start or end of the extracted text.
 * Better sub-splitting — splits on ., ;, !, ? followed by whitespace (not just . and ;), with a minimum length of 5 chars to avoid false positives.
 * Multi-element lists already work independently — each element in the array is matched separately against the full process text, so non-sequential passages each get their own highlight region. The merging step only combines overlapping/adjacent regions (within 1 char), so distant passages stay separate.
 */


"use client"

import { useEffect, useRef, useMemo, useCallback } from "react"
import type { ComplianceSegment } from "@/lib/types"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { FileText } from "lucide-react"

interface TextViewerProps {
  process: string
  segments: ComplianceSegment[]
  activeSegmentId: string | null
  onSegmentSelect?: (segmentId: string) => void
}

interface TextPart {
  text: string
  isHighlighted: boolean
  segmentId?: string | null
  category?: string | null
}

/** A matched region in the process text (start inclusive, end exclusive). */
interface MatchRegion {
  start: number
  end: number
}

/**
 * Normalize a string for fuzzy comparison:
 * - collapse all whitespace into single spaces
 * - trim
 * - lowercase
 */
function normalize(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase()
}

/**
 * Aggressively normalize: also strip punctuation for even fuzzier matching.
 * This helps when extracted segments have slightly different punctuation
 * (e.g. missing period, extra semicolon, different quote chars).
 */
function normalizePunctuation(s: string): string {
  return s
    .replace(/\s+/g, " ")
    .replace(/[^\w\s]/g, "") // remove all punctuation
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
}

/**
 * Build a mapping from normalized string indices back to original string indices.
 * Returns { normalized, origIndices } where origIndices[i] = index in original.
 */
function buildNormMap(
  text: string,
  normFn: (ch: string) => boolean // returns true if char should be kept
): { normalized: string; origIndices: number[] } {
  const normChars: string[] = []
  const origIndices: number[] = []
  let prevWasSpace = true

  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (/\s/.test(ch)) {
      if (!prevWasSpace) {
        normChars.push(" ")
        origIndices.push(i)
      }
      prevWasSpace = true
    } else if (normFn(ch)) {
      normChars.push(ch.toLowerCase())
      origIndices.push(i)
      prevWasSpace = false
    } else {
      // Character filtered out (e.g. punctuation) — skip but don't add space
    }
  }

  // Trim trailing space
  if (normChars.length > 0 && normChars[normChars.length - 1] === " ") {
    normChars.pop()
    origIndices.pop()
  }

  return { normalized: normChars.join(""), origIndices }
}

/**
 * Try to find `needle` in `haystack` using a given normalization strategy.
 * Returns the [start, end) indices in the ORIGINAL haystack, or null.
 */
function findWithNorm(
  haystack: string,
  needle: string,
  keepChar: (ch: string) => boolean
): MatchRegion | null {
  const hMap = buildNormMap(haystack, keepChar)
  const nMap = buildNormMap(needle, keepChar)

  if (!nMap.normalized) return null

  const idx = hMap.normalized.indexOf(nMap.normalized)
  if (idx === -1) return null

  const origStart = hMap.origIndices[idx]
  // Find the end: last char of match in normalized, map back to original
  const lastNormIdx = idx + nMap.normalized.length - 1
  const origEnd = hMap.origIndices[lastNormIdx] + 1

  return { start: origStart, end: origEnd }
}

/**
 * Try to find needle in haystack with progressively fuzzier matching:
 * 1. Exact match
 * 2. Whitespace-normalized match (collapse whitespace, case-insensitive)
 * 3. Punctuation-stripped match (also remove all punctuation)
 */
function fuzzyFind(haystack: string, needle: string): MatchRegion | null {
  // 1. Exact
  const exactIdx = haystack.indexOf(needle)
  if (exactIdx !== -1) {
    return { start: exactIdx, end: exactIdx + needle.length }
  }

  // 2. Whitespace-normalized (keep all non-whitespace chars)
  const wsMatch = findWithNorm(haystack, needle, () => true)
  if (wsMatch) return wsMatch

  // 3. Punctuation-stripped (only keep word characters)
  const punctMatch = findWithNorm(haystack, needle, (ch) => /\w/.test(ch))
  if (punctMatch) return punctMatch

  return null
}

/**
 * Try to find needle using a sliding window of words.
 * If the full needle doesn't match, try progressively smaller windows
 * to find the longest matching subsequence.
 */
function fuzzyFindLongestSubsequence(
  haystack: string,
  needle: string,
  minWords: number = 4
): MatchRegion | null {
  const words = needle.split(/\s+/).filter((w) => w.length > 0)
  if (words.length < minWords) return null

  // Try from the full length down to minWords
  for (let windowSize = words.length; windowSize >= minWords; windowSize--) {
    for (let start = 0; start <= words.length - windowSize; start++) {
      const sub = words.slice(start, start + windowSize).join(" ")
      const match = fuzzyFind(haystack, sub)
      if (match) return match
    }
  }

  return null
}

/**
 * Manually parse a stringified Python list with mixed quotes.
 */
function parsePythonList(s: string): string[] | null {
  const trimmed = s.trim()
  if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) return null

  const inner = trimmed.slice(1, -1)
  const results: string[] = []
  let i = 0

  while (i < inner.length) {
    while (
      i < inner.length &&
      (inner[i] === " " ||
        inner[i] === "," ||
        inner[i] === "\n" ||
        inner[i] === "\r" ||
        inner[i] === "\t")
    ) {
      i++
    }
    if (i >= inner.length) break

    const quoteChar = inner[i]
    if (quoteChar !== '"' && quoteChar !== "'") {
      return null
    }

    i++
    let item = ""
    while (i < inner.length) {
      const ch = inner[i]

      if (ch === "\\" && i + 1 < inner.length) {
        item += inner[i + 1]
        i += 2
        continue
      }

      if (ch === quoteChar) {
        const next = i + 1 < inner.length ? inner[i + 1] : "]"
        if (
          next === "," ||
          next === "]" ||
          next === " " ||
          next === "\n" ||
          next === "\r" ||
          next === "\t" ||
          i + 1 >= inner.length
        ) {
          i++
          break
        }
        item += ch
        i++
        continue
      }

      item += ch
      i++
    }

    const trimmedItem = item.trim()
    if (trimmedItem.length > 0) {
      results.push(trimmedItem)
    }
  }

  return results.length > 0 ? results.map(stripWrappingQuotes) : null
}

function stripWrappingQuotes(s: string): string {
  let result = s
  if (result.startsWith('"') && result.endsWith('"') && result.length >= 2) {
    result = result.slice(1, -1)
  }
  if (result.startsWith("'") && result.endsWith("'") && result.length >= 2) {
    result = result.slice(1, -1)
  }
  return result.trim()
}

function parseSegments(raw: string | string[]): string[] {
  if (Array.isArray(raw)) {
    return raw.map((s) => stripWrappingQuotes(s)).filter((s) => s.length > 0)
  }

  const trimmed = raw.trim()

  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    try {
      const parsed = JSON.parse(trimmed)
      if (Array.isArray(parsed)) {
        return parsed
          .map((s: string) => stripWrappingQuotes(String(s)))
          .filter((s: string) => s.length > 0)
      }
    } catch {
      // ignore
    }

    const pyParsed = parsePythonList(trimmed)
    if (pyParsed) return pyParsed
  }

  return [trimmed]
}

/**
 * Find each sentence from extracted_process_segment in the process text.
 * Uses progressively fuzzier matching strategies.
 * Each sentence is matched individually — they can be non-sequential.
 */
function findAllRegions(
  process: string,
  rawSegment: string | string[]
): MatchRegion[] {
  const sentences = parseSegments(rawSegment)
  const regions: MatchRegion[] = []

  for (let si = 0; si < sentences.length; si++) {
    const sentence = sentences[si].trim()
    if (!sentence || sentence.length < 3) continue

    // Strategy 1: Full fuzzy match (exact → whitespace-norm → punct-stripped)
    const match = fuzzyFind(process, sentence)
    if (match) {
      regions.push(match)
      continue
    }

    // Strategy 2: Try longest matching subsequence (sliding word window)
    const subseqMatch = fuzzyFindLongestSubsequence(process, sentence, 4)
    if (subseqMatch) {
      regions.push(subseqMatch)
      continue
    }

    // Strategy 3: Split by sentence-ending punctuation and match sub-parts
    const subParts = sentence
      .split(/(?<=[.;!?])\s+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 5)

    if (subParts.length > 1) {
      for (const sub of subParts) {
        const subMatch = fuzzyFind(process, sub)
        if (subMatch) {
          regions.push(subMatch)
          continue
        }
        const subSeq = fuzzyFindLongestSubsequence(process, sub, 3)
        if (subSeq) {
          regions.push(subSeq)
        }
      }
    }
  }

  // Sort by start position and merge overlapping/adjacent regions
  regions.sort((a, b) => a.start - b.start)
  const merged: MatchRegion[] = []
  for (const r of regions) {
    const last = merged[merged.length - 1]
    if (last && r.start <= last.end + 1) {
      last.end = Math.max(last.end, r.end)
    } else {
      merged.push({ ...r })
    }
  }

  return merged
}

/** A region tagged with the segment it belongs to */
interface TaggedRegion {
  start: number
  end: number
  segmentId: string
  category: string
}

/** Priority for overlapping underlines: most severe category wins */
const SEVERITY: Record<string, number> = {
  "NON-COMPLIANT": 3,
  "NO EVIDENCE": 2,
  "COMPLIANT": 1,
}

function buildParts(
  process: string,
  segments: ComplianceSegment[],
  activeSegmentId: string | null
): TextPart[] {
  // Find regions for ALL segments
  const allRegions: TaggedRegion[] = []
  for (const seg of segments) {
    if (!seg.extracted_process_segment) continue
    const regions = findAllRegions(process, seg.extracted_process_segment)
    for (const r of regions) {
      allRegions.push({ ...r, segmentId: seg.id, category: seg.category })
    }
  }

  if (allRegions.length === 0) {
    return [{ text: process, isHighlighted: false }]
  }

  // Sort by start position
  allRegions.sort((a, b) => a.start - b.start)

  // Build a coverage map: for each character position, track the best segment
  // Active segment always wins; otherwise highest severity wins
  const charMap = new Array<{ segmentId: string; category: string } | null>(process.length).fill(null)

  for (const r of allRegions) {
    for (let i = r.start; i < r.end && i < process.length; i++) {
      const existing = charMap[i]
      if (!existing) {
        charMap[i] = { segmentId: r.segmentId, category: r.category }
      } else if (r.segmentId === activeSegmentId) {
        charMap[i] = { segmentId: r.segmentId, category: r.category }
      } else if (existing.segmentId !== activeSegmentId) {
        // Higher severity wins
        if ((SEVERITY[r.category] || 0) > (SEVERITY[existing.category] || 0)) {
          charMap[i] = { segmentId: r.segmentId, category: r.category }
        }
      }
    }
  }

  // Convert char map into runs of same (segmentId, category)
  const parts: TextPart[] = []
  let runStart = 0
  let runInfo = charMap[0]

  for (let i = 1; i <= process.length; i++) {
    const cur = i < process.length ? charMap[i] : null
    const same = cur?.segmentId === runInfo?.segmentId

    if (!same) {
      parts.push({
        text: process.slice(runStart, i),
        isHighlighted: runInfo?.segmentId === activeSegmentId,
        segmentId: runInfo?.segmentId ?? null,
        category: runInfo?.category ?? null,
      })
      runStart = i
      runInfo = cur
    }
  }

  return parts
}

export function TextViewer({
  process,
  segments,
  activeSegmentId,
  onSegmentSelect,
}: TextViewerProps) {
  const highlightRef = useRef<HTMLSpanElement>(null)

  const parts = useMemo(
    () => buildParts(process, segments, activeSegmentId),
    [process, segments, activeSegmentId]
  )

  const firstHighlightIdx = useMemo(
    () => parts.findIndex((p) => p.isHighlighted),
    [parts]
  )

  const scrollToHighlight = useCallback(() => {
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      })
    }
  }, [])

  useEffect(() => {
    if (activeSegmentId) {
      const timer = setTimeout(scrollToHighlight, 50)
      return () => clearTimeout(timer)
    }
  }, [activeSegmentId, scrollToHighlight])

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 border-b px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">Process</h2>
        </div>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        <article className="px-6 py-5 leading-relaxed text-sm text-foreground/90 max-w-none">
          {parts.map((part, i) => {
            const color =
              part.category === "NON-COMPLIANT" ? "#ef4444" :
              part.category === "COMPLIANT" ? "#10b981" :
              part.category === "NO EVIDENCE" ? "#f97316" :
              undefined

            return (
              <span
                key={`${activeSegmentId}-${i}`}
                ref={i === firstHighlightIdx ? highlightRef : undefined}
                className={cn(
                  "transition-all duration-300 whitespace-pre-wrap",
                  part.isHighlighted &&
                    "bg-highlight/50 text-highlight-foreground rounded-sm ring-2 ring-highlight/60 ring-offset-1 ring-offset-background px-0.5 -mx-0.5",
                  !part.isHighlighted && part.segmentId &&
                    "cursor-pointer hover:bg-primary/10"
                )}
                style={
                  !part.isHighlighted && part.segmentId && color
                    ? { borderBottom: `2px solid ${color}`, paddingBottom: 1 }
                    : undefined
                }
                onClick={
                  part.segmentId && onSegmentSelect
                    ? () => onSegmentSelect(part.segmentId!)
                    : undefined
                }
              >
                {part.text}
              </span>
            )
          })}
        </article>
      </ScrollArea>
    </div>
  )
}
