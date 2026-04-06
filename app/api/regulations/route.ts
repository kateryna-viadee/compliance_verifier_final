import { NextResponse } from "next/server"

const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

export async function GET() {
  try {
    const response = await fetch(`${FLASK_URL}/api/regulations`)
    const text = await response.text()
    let data
    try {
      data = JSON.parse(text)
    } catch {
      return NextResponse.json({ regulations: [] })
    }
    if (!response.ok) {
      return NextResponse.json({ regulations: [] })
    }
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ regulations: [] })
  }
}

export async function POST(request: Request) {
  try {
    const incoming = await request.formData()

    const pdfFile = incoming.get("pdf_file") as File | null
    const regulationName = incoming.get("regulation_name") as string | null

    if (!pdfFile || !regulationName) {
      return NextResponse.json(
        { error: "pdf_file and regulation_name are required" },
        { status: 400 }
      )
    }

    // Reconstruct FormData for Flask
    const flaskForm = new FormData()
    const bytes = await pdfFile.arrayBuffer()
    const blob = new Blob([bytes], { type: pdfFile.type || "application/pdf" })
    flaskForm.append("pdf_file", blob, pdfFile.name)
    flaskForm.append("regulation_name", regulationName)

    const response = await fetch(`${FLASK_URL}/api/regulations/upload`, {
      method: "POST",
      body: flaskForm,
    })

    const text = await response.text()
    let data
    try {
      data = JSON.parse(text)
    } catch {
      return NextResponse.json(
        { error: `Backend returned non-JSON response (status ${response.status})` },
        { status: 502 }
      )
    }

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Upload failed" },
      { status: 500 }
    )
  }
}
