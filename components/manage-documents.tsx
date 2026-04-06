"use client"

import { useState, useCallback } from "react"
import useSWR, { mutate } from "swr"
import type { RegulationsListData, RegulationChunk } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Upload, Trash2, Eye, FileText, ArrowLeft, Loader2 } from "lucide-react"

const fetcher = (url: string) => fetch(url).then((r) => r.json())

interface ManageDocumentsProps {
  onBack: () => void
}

export function ManageDocuments({ onBack }: ManageDocumentsProps) {
  const { data, isLoading } = useSWR<RegulationsListData>(
    "/api/regulations",
    fetcher
  )

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [regulationName, setRegulationName] = useState("")

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewName, setPreviewName] = useState("")
  const [previewChunks, setPreviewChunks] = useState<RegulationChunk[]>([])
  const [previewLoading, setPreviewLoading] = useState(false)

  const [deleting, setDeleting] = useState<string | null>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && file.name.endsWith(".pdf")) {
      setPdfFile(file)
      setUploadError(null)
    } else {
      alert("Please select a valid PDF file")
    }
  }

  const handleUpload = useCallback(async () => {
    if (!pdfFile || !regulationName.trim()) return

    setUploading(true)
    setUploadError(null)

    try {
      const formData = new FormData()
      formData.append("pdf_file", pdfFile)
      formData.append("regulation_name", regulationName.trim())

      const res = await fetch("/api/regulations", {
        method: "POST",
        body: formData,
      })

      const result = await res.json()

      if (!res.ok) {
        setUploadError(result.error || "Upload failed")
        return
      }

      // Reset form and refresh list
      setPdfFile(null)
      setRegulationName("")
      // Reset the file input
      const fileInput = document.getElementById(
        "pdf-upload-input"
      ) as HTMLInputElement
      if (fileInput) fileInput.value = ""

      // Refresh regulations list and options (so dropdown updates too)
      mutate("/api/regulations")
      mutate("/api/options")
    } catch (err) {
      setUploadError(
        err instanceof Error ? err.message : "Upload failed"
      )
    } finally {
      setUploading(false)
    }
  }, [pdfFile, regulationName])

  const handlePreview = useCallback(async (id: string, name: string) => {
    setPreviewName(name)
    setPreviewChunks([])
    setPreviewOpen(true)
    setPreviewLoading(true)

    try {
      const res = await fetch(`/api/regulations/${encodeURIComponent(id)}/chunks`)
      const result = await res.json()
      if (res.ok) {
        setPreviewChunks(result.chunks || [])
      }
    } catch {
      // ignore
    } finally {
      setPreviewLoading(false)
    }
  }, [])

  const handleDelete = useCallback(async (id: string) => {
    if (!confirm("Are you sure you want to delete this regulation?")) return

    setDeleting(id)
    try {
      const res = await fetch(`/api/regulations/${encodeURIComponent(id)}`, {
        method: "DELETE",
      })
      if (res.ok) {
        mutate("/api/regulations")
        mutate("/api/options")
      }
    } catch {
      // ignore
    } finally {
      setDeleting(null)
    }
  }, [])

  return (
    <div className="flex h-full items-start justify-center overflow-y-auto">
      <div className="w-full max-w-4xl px-6 py-8 flex flex-col gap-8">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              Manage Documents
            </h2>
            <p className="text-sm text-muted-foreground">
              Upload PDF regulations, preview chunks, and manage your document
              library.
            </p>
          </div>
        </div>

        {/* Upload Section */}
        <div className="rounded-lg border bg-card p-6 flex flex-col gap-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Upload className="h-4 w-4 text-primary" />
            Upload New Regulation
          </h3>

          <div className="flex flex-col gap-3">
            <input
              type="text"
              value={regulationName}
              onChange={(e) => setRegulationName(e.target.value)}
              placeholder="Regulation name (e.g. GDPR, ISO 27001)"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />

            <div className="relative">
              <input
                type="file"
                accept=".pdf"
                onChange={handleFileSelect}
                className="hidden"
                id="pdf-upload-input"
              />
              <label
                htmlFor="pdf-upload-input"
                className="flex items-center justify-center gap-2 cursor-pointer rounded-md border-2 border-dashed border-muted-foreground/50 px-3 py-6 text-center transition-colors hover:border-primary hover:bg-muted/50"
              >
                <FileText className="h-5 w-5 text-muted-foreground" />
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-medium text-foreground">
                    {pdfFile ? pdfFile.name : "Click to select a PDF file"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Only .pdf files are supported
                  </span>
                </div>
              </label>
            </div>

            {uploadError && (
              <p className="text-sm text-destructive">{uploadError}</p>
            )}

            <Button
              onClick={handleUpload}
              disabled={!pdfFile || !regulationName.trim() || uploading}
              className="self-end"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Processing PDF...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Upload & Chunk
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Regulations Table */}
        <div className="rounded-lg border bg-card p-6 flex flex-col gap-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            Regulation Documents
          </h3>

          {isLoading ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : !data?.regulations?.length ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No regulation documents found. Upload a PDF to get started.
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="w-[100px] text-center">
                      Chunks
                    </TableHead>
                    <TableHead className="w-[140px] text-right">
                      Actions
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.regulations.map((reg) => (
                    <TableRow key={reg.id}>
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium text-sm">
                            {reg.name}
                          </span>
                          <span className="text-xs text-muted-foreground truncate max-w-[400px]">
                            {reg.description}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant="secondary">{reg.chunk_count}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handlePreview(reg.id, reg.name)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(reg.id)}
                            disabled={deleting === reg.id}
                            className="text-destructive hover:text-destructive"
                          >
                            {deleting === reg.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        {/* Chunk Preview Dialog */}
        <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
          <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
            <DialogHeader>
              <DialogTitle>{previewName} — Chunks</DialogTitle>
            </DialogHeader>
            <div className="flex-1 overflow-y-auto pr-2">
              {previewLoading ? (
                <div className="flex flex-col gap-2 py-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              ) : previewChunks.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No chunks found.
                </p>
              ) : (
                <div className="flex flex-col gap-3 py-2">
                  {previewChunks.map((chunk, idx) => (
                    <div
                      key={idx}
                      className="rounded-md border p-3 flex flex-col gap-1"
                    >
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          #{chunk.chunk_id}
                        </Badge>
                      </div>
                      <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                        {chunk.chunk_text}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
