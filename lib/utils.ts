import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Derive hex color from the category string */
export function getCategoryColor(category: string): string {
  switch (category) {
    case "COMPLIANT":
      return "#10b981"
    case "NON-COMPLIANT":
      return "#ef4444"
    case "NO EVIDENCE":
      return "#f97316"
    default:
      return "#f97316"
  }
}

/** Map internal category keys to user-facing display labels */
export function categoryLabel(category: string): string {
  switch (category) {
    case "COMPLIANT":
      return "Compliance"
    case "NON-COMPLIANT":
      return "Violation"
    case "NO EVIDENCE":
      return "Omission"
    default:
      return category
  }
}
