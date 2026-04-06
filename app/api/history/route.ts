import { NextResponse } from "next/server"

const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

export async function GET() {
  try {
    const response = await fetch(`${FLASK_URL}/api/history`)
    const text = await response.text()
    let data
    try {
      data = JSON.parse(text)
    } catch {
      return NextResponse.json({ items: [] })
    }
    if (!response.ok) {
      return NextResponse.json({ items: [] })
    }
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ items: [] })
  }
}
