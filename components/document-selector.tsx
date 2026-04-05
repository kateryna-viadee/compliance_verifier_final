"use client"

import { useState } from "react"
import useSWR from "swr"
import type { OptionsData } from "@/lib/types"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Checkbox } from "@/components/ui/checkbox"
import { Slider } from "@/components/ui/slider"
import { FileText, BookOpen, ArrowRight, PenLine, List, FileJson } from "lucide-react"

const fetcher = async (url: string) => {
  const res = await fetch(url)
  if (!res.ok) throw new Error("Failed to load options")
  return res.json()
}

export interface AnalyzeParams {
  processId?: string
  processText?: string
  bpmn_file?: File
  processName?: string
  saveProcess?: boolean
  regulationId: string
  strictness: "conservative" | "pragmatic"
}

interface DocumentSelectorProps {
  onAnalyze: (params: AnalyzeParams) => void
}

export function DocumentSelector({ onAnalyze }: DocumentSelectorProps) {
  const { data, isLoading } = useSWR<OptionsData>("/api/options", fetcher)
  const [processMode, setProcessMode] = useState<"select" | "type" | "bpmn">("select")
  const [processId, setProcessId] = useState<string>("")
  const [processText, setProcessText] = useState<string>("")
  const [bpmn_file, setBpmn_file] = useState<File | null>(null)
  const [processName, setProcessName] = useState<string>("")
  const [saveProcess, setSaveProcess] = useState<boolean>(false)
  const [regulationId, setRegulationId] = useState<string>("")
  const [strictness, setStrictness] = useState<"conservative" | "pragmatic">("conservative")

  const hasProcess =
    processMode === "select" ? processId !== "" :
    processMode === "type" ? processText.trim().length > 0 :
    bpmn_file !== null
  const canAnalyze = hasProcess && regulationId !== ""

  const handleSubmit = () => {
    if (processMode === "select") {
      onAnalyze({ processId, regulationId, strictness })
    } else if (processMode === "type") {
      onAnalyze({
        processText: processText.trim(),
        processName: processName.trim() || undefined,
        saveProcess,
        regulationId,
        strictness,
      })
    } else if (processMode === "bpmn" && bpmn_file) {
      onAnalyze({
        bpmn_file,
        processName: bpmn_file.name.replace(".bpmn", ""),
        saveProcess,
        regulationId,
        strictness,
      })
    }
  }

  const handleBpmn_fileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && file.name.endsWith(".bpmn")) {
      setBpmn_file(file)
    } else {
      alert("Please select a valid .bpmn file")
    }
  }

  if (isLoading || !data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="w-full max-w-lg flex flex-col gap-6 px-6">
          <Skeleton className="h-8 w-64 mx-auto" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-32 mx-auto" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full items-center justify-center">
      <div className="w-full max-w-xl px-6">
        <div className="rounded-lg border bg-card p-8 flex flex-col gap-8">
          <div className="text-center">
            <h2 className="text-lg font-semibold text-foreground text-balance">
              Select Documents to Analyze
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Choose or type a process and select a regulation document to run compliance verification.
            </p>
          </div>

          <div className="flex flex-col gap-5">
            {/* ── Process section ── */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-foreground flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" />
                  Process
                </label>
                <div className="flex items-center rounded-md border bg-muted/50 p-0.5">
                  <button
                    type="button"
                    onClick={() => setProcessMode("select")}
                    className={`flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors ${
                      processMode === "select"
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <List className="h-3 w-3" />
                    Select
                  </button>
                  <button
                    type="button"
                    onClick={() => setProcessMode("type")}
                    className={`flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors ${
                      processMode === "type"
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <PenLine className="h-3 w-3" />
                    Type
                  </button>
                  <button
                    type="button"
                    onClick={() => setProcessMode("bpmn")}
                    className={`flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors ${
                      processMode === "bpmn"
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <FileJson className="h-3 w-3" />
                    BPMN
                  </button>
                </div>
              </div>

              {processMode === "select" ? (
                <>
                  <Select value={processId} onValueChange={setProcessId}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select a process..." />
                    </SelectTrigger>
                    <SelectContent>
                      {data.processes.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          <span>{p.name}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {processId && (
                    <p className="text-xs text-muted-foreground pl-6">
                      {data.processes.find((p) => p.id === processId)?.description}
                    </p>
                  )}
                </>
              ) : processMode === "type" ? (
                <div className="flex flex-col gap-3">
                  <input
                    type="text"
                    value={processName}
                    onChange={(e) => setProcessName(e.target.value)}
                    placeholder="Process name (e.g. Data Handling SOP)"
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                  <textarea
                    value={processText}
                    onChange={(e) => setProcessText(e.target.value)}
                    placeholder="Paste or type your process text here..."
                    rows={8}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-y"
                  />
                  <label className="flex items-center gap-2 cursor-pointer">
                    <Checkbox
                      checked={saveProcess}
                      onCheckedChange={(checked) =>
                        setSaveProcess(checked === true)
                      }
                    />
                    <span className="text-xs text-muted-foreground">
                      Save this process for future use in the dropdown
                    </span>
                  </label>
                </div>
              ) : (
                /* BPMN mode */
                <div className="flex flex-col gap-3">
                  <div className="relative">
                    <input
                      type="file"
                      accept=".bpmn"
                      onChange={handleBpmn_fileSelect}
                      className="hidden"
                      id="bpmn-file-input"
                    />
                    <label
                      htmlFor="bpmn-file-input"
                      className="flex items-center justify-center gap-2 cursor-pointer rounded-md border-2 border-dashed border-muted-foreground/50 px-3 py-6 text-center transition-colors hover:border-primary hover:bg-muted/50"
                    >
                      <FileJson className="h-5 w-5 text-muted-foreground" />
                      <div className="flex flex-col gap-1">
                        <span className="text-sm font-medium text-foreground">
                          {bpmn_file ? bpmn_file.name : "Click to upload BPMN file"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Only .bpmn files are supported
                        </span>
                      </div>
                    </label>
                  </div>
                  {bpmn_file && (
                    <label className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={saveProcess}
                        onCheckedChange={(checked) =>
                          setSaveProcess(checked === true)
                        }
                      />
                      <span className="text-xs text-muted-foreground">
                        Save the converted process for future use in the dropdown
                      </span>
                    </label>
                  )}
                </div>
              )}
            </div>

            {/* ── Regulation section ── */}
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-foreground flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-primary" />
                Regulation Document
              </label>
              <Select value={regulationId} onValueChange={setRegulationId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a regulation document..." />
                </SelectTrigger>
                <SelectContent>
                  {data.regulations.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      <span>{r.name}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {regulationId && (
                <p className="text-xs text-muted-foreground pl-6">
                  {data.regulations.find((r) => r.id === regulationId)?.description}
                </p>
              )}
            </div>
          </div>

          {/* ── Strictness Slider ── */}
          <div className="flex flex-col gap-3 border-t pt-6">
            <label className="text-sm font-medium text-foreground">
              Compliance Strictness
            </label>
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Pragmatic</span>
                <span className="text-xs font-medium text-muted-foreground">Conservative</span>
              </div>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => setStrictness("pragmatic")}
                  className={`h-3 w-3 rounded-full transition-all ${
                    strictness === "pragmatic"
                      ? "bg-primary shadow-sm"
                      : "bg-muted border border-muted-foreground/30"
                  }`}
                  aria-label="Pragmatic - No clear breach, no flag"
                  title="Pragmatic - No clear breach, no flag"
                />
                <div className={`flex-1 h-1 rounded-full bg-muted relative`}>
                  <div
                    className="absolute h-full bg-primary rounded-full transition-all"
                    style={{
                      width: strictness === "conservative" ? "100%" : "0%",
                    }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setStrictness("conservative")}
                  className={`h-3 w-3 rounded-full transition-all ${
                    strictness === "conservative"
                      ? "bg-primary shadow-sm"
                      : "bg-muted border border-muted-foreground/30"
                  }`}
                  aria-label="Conservative - Flag all doubt as non-compliant"
                  title="Conservative - Flag all doubt as non-compliant"
                />
              </div>
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-muted-foreground">No clear breach, no flag.</span>
                <span className="text-xs text-muted-foreground">Flag all doubt as non-compliant</span>
              </div>
              <div className="text-center">
                <span className="text-xs font-semibold text-foreground">
                  {strictness === "conservative" ? "Conservative" : "Pragmatic"}
                </span>
              </div>
            </div>
          </div>

          <Button
            className="w-full"
            size="lg"
            disabled={!canAnalyze}
            onClick={handleSubmit}
          >
            Analyze Compliance
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
