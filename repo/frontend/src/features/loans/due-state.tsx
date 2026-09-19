import { Badge } from "@/components/ui/badge"
import { daysUntilDue } from "@/lib/dates"
import { formatDueIn } from "@/lib/format"
import type { LoanOut } from "@/lib/types"

/** A loan due within this many days gets a highlighted "due in" badge. */
const DUE_SOON_DAYS = 3

/** An active loan's state for its borrower: overdue, or how long is left, highlighted when close. */
export function DueState({ loan, now }: { loan: LoanOut; now: number }) {
  if (loan.is_overdue) return <Badge variant="overdue">Overdue</Badge>
  const days = daysUntilDue(loan.due_at, now)
  if (days <= DUE_SOON_DAYS) return <Badge variant="borrowed">{formatDueIn(days)}</Badge>
  return <span className="text-sm whitespace-nowrap text-muted-foreground">{formatDueIn(days)}</span>
}
