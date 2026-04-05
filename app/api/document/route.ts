import { NextResponse } from "next/server"
import { MOCK_DATA } from "@/lib/mock-data"

/**
 * This route proxies requests to your Python Flask backend.
 * Kept for backward compatibility. The new flow uses /api/analyze.
 */
const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

export async function GET() {
  try {
    const response = await fetch(`${FLASK_URL}/api/document`, {
      headers: { "Content-Type": "application/json" },
    })

    if (!response.ok) {
      return NextResponse.json(MOCK_DATA)
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json(MOCK_DATA)
  }
}
