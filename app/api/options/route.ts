import { NextResponse } from "next/server"

const FLASK_URL = process.env.FLASK_BACKEND_URL || "http://localhost:5005"

const MOCK_OPTIONS = {
  processes: [
    {
      id: "data-handling-sop",
      name: "Data Handling SOP",
      description:
        "Standard operating procedure for customer personal data handling across all departments",
    },
    {
      id: "employee-onboarding",
      name: "Employee Onboarding Process",
      description:
        "HR onboarding workflow including data collection and system access provisioning",
    },
  ],
  regulations: [
    {
      id: "gdpr",
      name: "GDPR Compliance Rules",
      description:
        "EU General Data Protection Regulation - key articles and requirements",
    },
    {
      id: "iso-27001",
      name: "ISO 27001 Controls",
      description:
        "Information security management standard - Annex A controls",
    },
  ],
}

export async function GET() {
  try {
    const response = await fetch(`${FLASK_URL}/api/options`, {
      headers: { "Content-Type": "application/json" },
    })

    if (!response.ok) {
      return NextResponse.json(MOCK_OPTIONS)
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json(MOCK_OPTIONS)
  }
}
