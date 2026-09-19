import type { CopyOut } from "@/lib/types"

/**
 * Whether a copy's loan is past its due time. Staff get the API's answer with
 * the loan; members see only the due time, so it is compared with `now`, the
 * same rule the API uses.
 */
export function isCopyOverdue(copy: CopyOut, now: number): boolean {
  if (copy.active_loan) return copy.active_loan.is_overdue
  return copy.due_at !== null && Date.parse(copy.due_at) < now
}
