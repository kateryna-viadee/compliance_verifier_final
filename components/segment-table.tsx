"use client"

import type { ComplianceSegment } from "@/lib/types"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Checkbox } from "@/components/ui/checkbox"
import { cn } from "@/lib/utils"

/** Derive dot color from the category string */
function getCategoryDotClass(category: string): string {
  switch (category) {
    case "COMPLIANT":
      return "bg-emerald-500"
    case "NON-COMPLIANT":
      return "bg-red-500"
    case "NO EVIDENCE":
      return "bg-neutral-400"
    default:
      return "bg-neutral-400"
  }
}

/** Determine the 3-state type for a segment (used for inline icons only) */
function getFilterState(segment: ComplianceSegment): "consistent" | "assumption" | "ambiguous" {
  if (segment.s3_resolution === "strictness") return "ambiguous"
  if (segment.s4_compliance_category && segment.s4_compliance_category !== segment.category) return "ambiguous"
  if (segment.s4_assumption_needed === "Yes") return "assumption"
  return "consistent"
}

/** Render the inline icon (⚠ for assumption, nothing otherwise) */
function FilterIcon({ state }: { state: "consistent" | "assumption" | "ambiguous" }) {
  if (state === "assumption") {
    return (
      <span
        className="inline-flex items-center justify-center h-2.5 w-2.5 text-orange-500"
        title="Assumption needed"
        aria-label="Assumption needed"
      >
        ⚠
      </span>
    )
  }
  return null
}

interface SegmentTableProps {
  segments: ComplianceSegment[]
  activeSegmentId: string | null
  onSegmentClick: (segment: ComplianceSegment) => void
  activeCategories: Set<string>
  onToggleCategory: (category: string) => void
  categoryCounts: Record<string, number>
}

export function SegmentTable({
  segments,
  activeSegmentId,
  onSegmentClick,
  activeCategories,
  onToggleCategory,
  categoryCounts,
}: SegmentTableProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">
          Process Segments
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Click a row to highlight in the document
        </p>
        <div className="flex items-center gap-4 mt-2.5">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <Checkbox
              checked={activeCategories.has("NON-COMPLIANT")}
              onCheckedChange={() => onToggleCategory("NON-COMPLIANT")}
              className="h-3.5 w-3.5 border-red-400 data-[state=checked]:bg-red-500 data-[state=checked]:border-red-500"
            />
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className="block h-2 w-2 rounded-full bg-red-500" />
              Non-Compliant ({categoryCounts["NON-COMPLIANT"] || 0})
            </span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <Checkbox
              checked={activeCategories.has("COMPLIANT")}
              onCheckedChange={() => onToggleCategory("COMPLIANT")}
              className="h-3.5 w-3.5 border-emerald-400 data-[state=checked]:bg-emerald-500 data-[state=checked]:border-emerald-500"
            />
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className="block h-2 w-2 rounded-full bg-emerald-500" />
              Compliant ({categoryCounts["COMPLIANT"] || 0})
            </span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <Checkbox
              checked={activeCategories.has("NO EVIDENCE")}
              onCheckedChange={() => onToggleCategory("NO EVIDENCE")}
              className="h-3.5 w-3.5 border-neutral-300 data-[state=checked]:bg-neutral-400 data-[state=checked]:border-neutral-400"
            />
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className="block h-2 w-2 rounded-full bg-neutral-400" />
              No Evidence ({categoryCounts["NO EVIDENCE"] || 0})
            </span>
          </label>
        </div>
      </div>
      <ScrollArea className="flex-1 min-h-0 thin-scrollbar">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[10px] pl-4 pr-0">
                <span className="sr-only">Category</span>
              </TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Summary
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {segments.map((segment) => {
              const isActive = activeSegmentId === segment.id
              const filterState = getFilterState(segment)
              const isS3Split = filterState === "ambiguous" &&
                segment.s3_category_1 &&
                segment.s3_category_2 &&
                segment.s3_category_1 !== segment.s3_category_2
              const isS4Split = !isS3Split &&
                segment.s4_compliance_category &&
                segment.s4_compliance_category !== segment.category

              return (
                <TableRow
                  key={segment.id}
                  className="group border-b-0"
                >
                  <TableCell
                    colSpan={2}
                    className="p-0"
                  >
                    {/* Clickable main content */}
                    <div
                      onClick={() => onSegmentClick(segment)}
                      className={cn(
                        "flex items-start cursor-pointer transition-colors px-4 py-3",
                        isActive
                          ? "bg-highlight/30 hover:bg-highlight/40 border-l-2 border-l-primary"
                          : "hover:bg-muted/70 border-l-2 border-l-transparent"
                      )}
                      role="button"
                      tabIndex={0}
                      aria-pressed={isActive}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault()
                          onSegmentClick(segment)
                        }
                      }}
                    >
                      {/* Filter State Icon + Category Dot */}
                      <div className="pt-1.5 pr-3 shrink-0 flex flex-col items-center gap-0.5">
                        <FilterIcon state={filterState} />
                        {isS3Split ? (
                          <div className="flex h-2.5 w-2.5" title="S3 disagreement">
                            <div
                              className={cn(
                                "w-1/2 rounded-l-full",
                                getCategoryDotClass(segment.category)
                              )}
                            />
                            <div
                              className={cn(
                                "w-1/2 rounded-r-full",
                                getCategoryDotClass(
                                  segment.s3_category_1 === segment.category
                                    ? (segment.s3_category_2 ?? "")
                                    : (segment.s3_category_1 ?? "")
                                )
                              )}
                            />
                          </div>
                        ) : isS4Split ? (
                          <div className="flex h-2.5 w-2.5" title="S4 disagrees">
                            <div
                              className={cn(
                                "w-1/2 rounded-l-full",
                                getCategoryDotClass(segment.category)
                              )}
                            />
                            <div
                              className={cn(
                                "w-1/2 rounded-r-full",
                                getCategoryDotClass(segment.s4_compliance_category ?? "")
                              )}
                            />
                          </div>
                        ) : (
                          <span
                            className={cn(
                              "block h-2.5 w-2.5 rounded-full",
                              getCategoryDotClass(segment.category)
                            )}
                            title={segment.category}
                            aria-label={`Category: ${segment.category}`}
                          />
                        )}
                      </div>

                      {/* Summary + Rule */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground whitespace-normal leading-relaxed">
                          {segment.short_evidence}
                        </p>
                        <p className="text-[11px] text-muted-foreground mt-1 italic">
                          {segment.easy_rule}
                        </p>
                      </div>
                    </div>

                    {/* Separator */}
                    <div className="border-b" />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  )
}




