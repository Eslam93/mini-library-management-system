import { Badge } from "@/components/ui/badge"
import type { BookSummary } from "@/lib/types"

type AvailabilityBadgeProps = {
  book: Pick<BookSummary, "availability" | "copies_available" | "copies_total">
}

/** Whether a book can be borrowed right now: "2 of 3 available", "All copies borrowed" or "No copies". */
export function AvailabilityBadge({ book }: AvailabilityBadgeProps) {
  switch (book.availability) {
    case "available":
      return (
        <Badge variant="available">
          {book.copies_available} of {book.copies_total} available
        </Badge>
      )
    case "all_borrowed":
      return <Badge variant="borrowed">All copies borrowed</Badge>
    case "no_copies":
      return <Badge variant="outline">No copies</Badge>
  }
}
