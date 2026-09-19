/**
 * Calendar-date math. Date input values are YYYY-MM-DD strings in the
 * browser's time zone, which is what <input type="date"> reads and writes.
 */

const DAY_MS = 86_400_000

function pad(value: number) {
  return String(value).padStart(2, "0")
}

export function toDateInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function todayDateValue(): string {
  return toDateInputValue(new Date())
}

/** Adds whole days to a YYYY-MM-DD value. */
export function addDays(value: string, days: number): string {
  const [year, month, day] = value.split("-").map(Number)
  return toDateInputValue(new Date(year, month - 1, day + days))
}

/**
 * Whole days from today to a loan's due date: 0 on the due day, 1 the day
 * before, negative after it. The due date is its UTC date, as formatDueDate
 * shows it; today is the reader's calendar date.
 */
export function daysUntilDue(dueAt: string, now: number): number {
  const due = new Date(dueAt)
  const today = new Date(now)
  const dueDay = Date.UTC(due.getUTCFullYear(), due.getUTCMonth(), due.getUTCDate())
  const todayDay = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((dueDay - todayDay) / DAY_MS)
}
