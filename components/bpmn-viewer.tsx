"use client"

import { useEffect, useRef, useState } from "react"
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer"

interface BpmnViewerProps {
  bpmnXml?: string | null
  highlightedElementId?: string | null
}

export function BpmnViewer({ bpmnXml, highlightedElementId }: BpmnViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewerRef = useRef<any>(null)
  const [previousHighlight, setPreviousHighlight] = useState<string | null>(null)

  // Initialize viewer and load BPMN
  useEffect(() => {
    if (!containerRef.current) return

    if (!viewerRef.current) {
      viewerRef.current = new NavigatedViewer({
        container: containerRef.current,
      })
    }

    const render = async () => {
      if (!bpmnXml) return
      try {
        await viewerRef.current.importXML(bpmnXml)
        const canvas = viewerRef.current.get("canvas")
        canvas.zoom("fit-viewport")
      } catch (err) {
        console.error("Failed to render BPMN XML:", err)
      }
    }

    render()
  }, [bpmnXml])

  // Handle element highlighting
  useEffect(() => {
    if (!viewerRef.current || !bpmnXml) return

    try {
      const canvas = viewerRef.current.get("canvas")
      const elementRegistry = viewerRef.current.get("elementRegistry")

      // Clear previous highlight
      if (previousHighlight) {
        canvas.removeMarker(previousHighlight, "highlight")
      }

      // Add new highlight
      if (highlightedElementId) {
        const element = elementRegistry.get(highlightedElementId)
        if (element) {
          canvas.addMarker(highlightedElementId, "highlight")

          // Scroll to element (with some padding)
          canvas.scrollToElement(element, { top: 100, bottom: 100, left: 100, right: 100 })

          console.log(`[BPMN Viewer] Highlighted element: ${highlightedElementId}`)
        } else {
          console.warn(`[BPMN Viewer] Element not found: ${highlightedElementId}`)
        }
      }

      setPreviousHighlight(highlightedElementId)
    } catch (err) {
      console.error("[BPMN Viewer] Highlighting error:", err)
    }
  }, [highlightedElementId, bpmnXml, previousHighlight])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy()
        viewerRef.current = null
      }
    }
  }, [])

  if (!bpmnXml) {
    return (
      <div className="h-full w-full flex items-center justify-center text-xs text-muted-foreground">
        Kein BPMN-Diagramm vorhanden.
      </div>
    )
  }

  return <div ref={containerRef} className="h-full w-full bg-white" />
}


