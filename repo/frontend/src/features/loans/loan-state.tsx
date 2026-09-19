import { Badge } from "@/components/ui/badge"
import { formatDate, formatOverdue } from "@/lib/format"
import type { LoanOut } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Where a loan stands: returned on a date, on loan, or how many days overdue. */
export function LoanState({ loan, className }: { loan: LoanOut; className?: string }) {
  if (loan.returned_at) {
    return (
      <span className={cn("text-muted-foreground", className)}>
        Returned <span className="whitespace-nowrap">{formatDate(loan.returned_at)}</span>
      </span>
    )
  }
  if (loan.is_overdue) {
    return (
      <Badge variant="overdue" className={className}>
        {formatOverdue(loan.days_overdue)}
      </Badge>
    )
  }
  return (
    <Badge variant="borrowed" className={className}>
      On loan
    </Badge>
  )
}
