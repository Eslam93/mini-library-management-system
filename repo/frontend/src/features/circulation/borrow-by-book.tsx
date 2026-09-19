import { useState, type RefObject } from "react"
import { BookUp, Search } from "lucide-react"

import { FormAlert } from "@/components/forms/form-alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { AvailabilityBadge } from "@/features/books/availability-badge"
import { useBooks } from "@/features/books/hooks"
import { BorrowBookDialog } from "@/features/loans/borrow-book-dialog"
import { useBorrowByBookId } from "@/features/loans/hooks"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { useDialogSession } from "@/hooks/use-dialog-session"
import { ApiError } from "@/lib/api"
import { plural } from "@/lib/format"
import type { BookSummary } from "@/lib/types"

const RESULT_LIMIT = 8
const SEARCH_DELAY_MS = 250

/**
 * "Borrow by book": find the book in the catalog, then the usual borrow
 * dialog opens with its first available copy chosen.
 */
export function BorrowByBook({ returnFocusTo }: { returnFocusTo: RefObject<HTMLElement | null> }) {
  const [finding, setFinding] = useState(false)
  const session = useDialogSession(finding)
  const borrow = useBorrowByBookId()

  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          borrow.clearLoadError()
          setFinding(true)
        }}
      >
        <BookUp aria-hidden />
        Borrow by book
      </Button>
      <Dialog open={finding} onOpenChange={setFinding}>
        <FindBookContent
          key={session}
          choosing={borrow.loading}
          error={borrow.loadError}
          onChoose={(book) => borrow.start(book.id, null, () => setFinding(false))}
          returnFocusTo={returnFocusTo}
          bookChosen={borrow.target.open}
        />
      </Dialog>
      <BorrowBookDialog
        target={borrow.target}
        onOpenChange={borrow.setOpen}
        returnFocusTo={returnFocusTo}
      />
    </>
  )
}

type FindBookContentProps = {
  choosing: boolean
  error: Error | null
  onChoose: (book: BookSummary) => void
  returnFocusTo: RefObject<HTMLElement | null>
  /** The borrow dialog took over, so focus stays with it. */
  bookChosen: boolean
}

function FindBookContent({ choosing, error, onChoose, returnFocusTo, bookChosen }: FindBookContentProps) {
  const [search, setSearch] = useState("")
  const q = useDebouncedValue(search.trim(), SEARCH_DELAY_MS)
  const books = useBooks({ q, limit: RESULT_LIMIT }, { enabled: q !== "" })
  const items = q ? (books.data?.items ?? []) : []

  let status: string
  if (!q) status = "Type part of a title, an author or an ISBN."
  else if (books.isError) status = "Could not search the catalog. Try again."
  else if (!books.data) status = "Searching…"
  else if (items.length === 0) status = `No book matches "${q}".`
  else if (books.data.total > items.length)
    status = `Showing ${items.length} of ${books.data.total} books. Type more to narrow the list.`
  else status = plural(items.length, "book", "books")

  return (
    <DialogContent
      className="sm:max-w-lg"
      onCloseAutoFocus={(event) => {
        event.preventDefault()
        if (!bookChosen) returnFocusTo.current?.focus()
      }}
    >
      <DialogHeader>
        <DialogTitle>Borrow by book</DialogTitle>
        <DialogDescription>
          Find the book, then choose the member and the due date.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="find-book">Book</Label>
        <div className="relative">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            id="find-book"
            type="search"
            autoFocus
            autoComplete="off"
            placeholder="Search by title, author or ISBN"
            className="pl-8"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <p aria-live="polite" className="text-xs text-muted-foreground">
          {status}
        </p>
      </div>
      <FormAlert title="Could not open the borrow form" message={error && errorMessage(error)} />
      {items.length > 0 && (
        <ul aria-label="Books" className="max-h-80 divide-y overflow-y-auto rounded-md border">
          {items.map((book) => {
            const lendable = book.copies_available > 0
            return (
              <li key={book.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0 space-y-1">
                  <p className="truncate text-sm font-medium">{book.title}</p>
                  <p className="truncate text-xs text-muted-foreground">{book.author}</p>
                  <AvailabilityBadge book={book} />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!lendable || choosing}
                  aria-label={`Borrow ${book.title}`}
                  onClick={() => onChoose(book)}
                >
                  Borrow
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </DialogContent>
  )
}

function errorMessage(error: Error) {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again."
}
