import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import { plural } from "@/lib/format"

type PagerProps = {
  total: number
  limit: number
  offset: number
  /** What the list holds, singular and plural: ["book", "books"]. */
  noun: readonly [one: string, many: string]
  onPageChange: (page: number) => void
}

/** "Showing 21–40 of 57 books" with Previous and Next. Only the count shows when all fits on one page. */
export function Pager({ total, limit, offset, noun, onPageChange }: PagerProps) {
  const page = Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / limit))
  const first = Math.min(offset + 1, total)
  const last = Math.min(offset + limit, total)

  if (pages === 1) {
    return (
      <p className="pt-3 text-sm text-muted-foreground">
        {plural(total, ...noun)}
      </p>
    )
  }

  return (
    <nav
      aria-label="Pages"
      className="flex flex-col gap-3 pt-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between"
    >
      <p>
        Showing {first}–{last} of {total} {noun[1]}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft aria-hidden />
          Previous
        </Button>
        <span className="px-1 tabular-nums">
          Page {page} of {pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
          <ChevronRight aria-hidden />
        </Button>
      </div>
    </nav>
  )
}
