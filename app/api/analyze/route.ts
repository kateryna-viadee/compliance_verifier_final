import { NextResponse } from "next/server"

const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

export async function POST(request: Request) {
  try {
    const contentType = request.headers.get("content-type")
    let flaskResponse: Response

    if (contentType?.includes("multipart/form-data")) {
      // Handle BPMN file upload
      const formData = await request.formData()
      const bpmn_file = formData.get("bpmn_file") as File
      const processName = formData.get("processName") as string
      const saveProcess = formData.get("saveProcess") === "true"
      const regulationId = formData.get("regulationId") as string

      if (!bpmn_file || !regulationId) {
        return NextResponse.json(
          { error: "BPMN file and regulationId are required" },
          { status: 400 }
        )
      }

      // Forward to Flask with FormData
      const flaskFormData = new FormData()
      const bytes = await bpmn_file.arrayBuffer()
      const blob = new Blob([bytes], { type: bpmn_file.type })
      flaskFormData.append("bpmn_file", blob, bpmn_file.name)
      flaskFormData.append("process_name", processName)
      flaskFormData.append("save_process", String(saveProcess))
      flaskFormData.append("regulation_id", regulationId)

      flaskResponse = await fetch(`${FLASK_URL}/api/analyze`, {
        method: "POST",
        body: flaskFormData,
      })
    } else {
      // Handle JSON body (processId or processText)
      const body = await request.json()
      const {
        processId, processText, processName, saveProcess,
        regulationId, regulationText, regulationName, saveRegulation,
      } = body

      if ((!processId && !processText) || (!regulationId && !regulationText)) {
        return NextResponse.json(
          {
            error:
              "Either processId or processText, plus regulationId or regulationText, are required",
          },
          { status: 400 }
        )
      }

      flaskResponse = await fetch(`${FLASK_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          process_id: processId,
          process_text: processText,
          process_name: processName,
          save_process: saveProcess,
          regulation_id: regulationId,
          regulation_text: regulationText,
          regulation_name: regulationName,
          save_regulation: saveRegulation,
        }),
      })
    }

    if (!flaskResponse.ok) {
      const text = await flaskResponse.text()
      return NextResponse.json(
        { error: `Backend error: ${text.slice(0, 200)}` },
        { status: flaskResponse.status }
      )
    }

    // Flask returns SSE — stream it through to the client
    if (
      flaskResponse.headers
        .get("content-type")
        ?.includes("text/event-stream")
    ) {
      return new Response(flaskResponse.body, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
          "X-Accel-Buffering": "no",
        },
      })
    }

    // Fallback: plain JSON response
    const text = await flaskResponse.text()
    try {
      const data = JSON.parse(text)
      return NextResponse.json(data)
    } catch {
      return NextResponse.json(
        { error: "Backend returned invalid response" },
        { status: 502 }
      )
    }
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Analysis failed" },
      { status: 500 }
    )
  }
}
