import { NextResponse } from "next/server"

const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ regulationId: string }> }
) {
  const { regulationId } = await params
  try {
    const response = await fetch(
      `${FLASK_URL}/api/regulations/${encodeURIComponent(regulationId)}`,
      { method: "DELETE" }
    )
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
      { error: err instanceof Error ? err.message : "Delete failed" },
      { status: 500 }
    )
  }
}
