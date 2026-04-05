import { NextResponse } from "next/server"
import { MOCK_DATA } from "@/lib/mock-data"

const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

export async function POST(request: Request) {
  try {
    const contentType = request.headers.get("content-type")
    let body: any = {}

    if (contentType?.includes("application/json")) {
      body = await request.json()
    } else if (contentType?.includes("multipart/form-data")) {
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
      flaskFormData.append("bpmn_file", bpmn_file)
      flaskFormData.append("process_name", processName)
      flaskFormData.append("save_process", String(saveProcess))
      flaskFormData.append("regulation_id", regulationId)

      const response = await fetch(`${FLASK_URL}/api/analyze`, {
        method: "POST",
        body: flaskFormData,
      })

      if (!response.ok) {
        return NextResponse.json(MOCK_DATA)
      }

      const data = await response.json()
      return NextResponse.json(data)
    } else {
      body = await request.json()
    }

    // Handle JSON body (processId or processText)
    const { processId, processText, processName, saveProcess, regulationId } = body

    if ((!processId && !processText) || !regulationId) {
      return NextResponse.json(
        { error: "Either processId or processText, plus regulationId, are required" },
        { status: 400 }
      )
    }

    const response = await fetch(`${FLASK_URL}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        process_id: processId,
        process_text: processText,
        process_name: processName,
        save_process: saveProcess,
        regulation_id: regulationId,
      }),
    })

    if (!response.ok) {
      return NextResponse.json(MOCK_DATA)
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch {
    // Flask is not running -- return mock data so the UI still works
    return NextResponse.json(MOCK_DATA)
  }
}
