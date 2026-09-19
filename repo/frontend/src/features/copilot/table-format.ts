import type { TableCell, TableColumnFormat } from "@/features/copilot/types"
import { formatCount } from "@/lib/format"

/** What a cell with no value shows. */
export const NO_VALUE = "–"

// The server rounds every computed figure to one decimal, so one decimal
// always shows: "37.0%" and "37.1%" line up in a column.
const oneDecimal = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const signedOneDecimal = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
})
const axisNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

/**
 * A table cell as the panel writes it: "1,234", "37.1%", "+8.2 pts",
 * "-3.0%", "12.3 days". Text stays exactly as the server sent it, so a year
 * such as 2026 never gains a thousands separator.
 */
export function formatTableValue(value: TableCell, format: TableColumnFormat): string {
  if (value === null) return NO_VALUE
  if (typeof value === "string" || format === "text") return String(value)
  switch (format) {
    case "count":
      return formatCount(value)
    case "percent":
      return `${oneDecimal.format(value)}%`
    case "points":
      return `${signedOneDecimal.format(value)} pts`
    case "change_percent":
      return `${signedOneDecimal.format(value)}%`
    case "days":
      return `${oneDecimal.format(value)} days`
  }
}

/** A chart axis tick: shorter than a cell, with no trailing ".0" and no unit except "%". */
export function formatAxisValue(value: number, format: TableColumnFormat): string {
  const number = axisNumber.format(value)
  return format === "percent" || format === "change_percent" ? `${number}%` : number
}
