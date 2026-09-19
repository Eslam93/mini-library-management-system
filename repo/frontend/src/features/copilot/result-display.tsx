import { Button } from "@/components/ui/button"
import { AvailabilityBadge } from "@/features/books/availability-badge"
import { BookCover } from "@/features/books/book-cover"
import { isCopyOverdue } from "@/features/books/copy-status"
import { CopyStatusBadge } from "@/features/books/copy-status-badge"
import { CopyLookupBadge } from "@/features/circulation/copy-lookup-badge"
import { BookTitleLink } from "@/features/copilot/book-title-link"
import { ProposalCard } from "@/features/copilot/proposal-card"
import { ResultTable } from "@/features/copilot/result-table"
import type { CopilotDisplay, CopilotFace } from "@/features/copilot/types"
import { DueState } from "@/features/loans/due-state"
import { LoanState } from "@/features/loans/loan-state"
import { MemberLink } from "@/features/members/member-link"
import { useNow } from "@/hooks/use-now"
import { formatDueDate, plural } from "@/lib/format"
import type { BookDetail, BookSummary, CopyLookupOut, LoanOut, MemberOut } from "@/lib/types"

type ResultDisplayProps = {
  display: CopilotDisplay
  /** Staff see whose loan each loan row is; a member only ever sees their own loans. */
  face: CopilotFace
  /** A link inside is leaving for a page, so the panel can close. */
  onNavigate: () => void
  /** Sends a follow-up message, for chips that run a search. */
  onAsk: (message: string) => void
  /** A turn is running, so chips that send wait for it. */
  busy: boolean
}

/** What a tool found, shown with the product's own book, copy, member and loan components, or as a table of figures. */
export function ResultDisplay({ display, face, onNavigate, onAsk, busy }: ResultDisplayProps) {
  switch (display.kind) {
    case "books":
      return <BookCards books={display.items} onNavigate={onNavigate} />
    case "book":
      return <BookSummaryCard book={display.book} onNavigate={onNavigate} />
    case "loans":
      return <LoanRows loans={display.items} showMember={face === "staff"} onNavigate={onNavigate} />
    case "categories":
      return <CategoryChips categories={display.items} onAsk={onAsk} busy={busy} />
    case "members":
      return <MemberRows members={display.items} onNavigate={onNavigate} />
    case "copy":
      return <CopySummary lookup={display.lookup} onNavigate={onNavigate} />
    case "proposal":
      return <ProposalCard proposal={display.proposal} onNavigate={onNavigate} />
    case "table":
      return <ResultTable table={display} />
    default:
      // A kind this version of the app does not know yet: the reply text still explains it.
      return null
  }
}

function BookCards({ books, onNavigate }: { books: BookSummary[]; onNavigate: () => void }) {
  if (books.length === 0) return <p className="text-sm text-muted-foreground">No books matched.</p>
  return (
    <ul aria-label={plural(books.length, "book", "books")} className="space-y-2">
      {books.map((book) => (
        <li key={book.id} className="flex gap-3 rounded-lg border bg-card p-3 shadow-xs">
          <BookCover book={book} size="S" />
          <div className="min-w-0">
            <BookTitleLink book={book} onNavigate={onNavigate} />
            <p className="text-xs text-muted-foreground">
              {book.author}
              {book.category && ` · ${book.category}`}
            </p>
            <div className="mt-2">
              <AvailabilityBadge book={book} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

function BookSummaryCard({ book, onNavigate }: { book: BookDetail; onNavigate: () => void }) {
  const now = useNow()
  const details = [book.author, book.category, book.published_year].filter(Boolean).join(" · ")

  return (
    <article className="rounded-lg border bg-card p-3 shadow-xs">
      <div className="flex gap-3">
        <BookCover book={book} size="S" />
        <div className="min-w-0">
          <BookTitleLink book={book} onNavigate={onNavigate} />
          <p className="text-xs text-muted-foreground">{details}</p>
          <div className="mt-2">
            <AvailabilityBadge book={book} />
          </div>
        </div>
      </div>
      {book.copies.length > 0 && (
        <ul aria-label="Copies" className="mt-3 divide-y border-t text-sm">
          {book.copies.map((copy) => {
            const overdue = isCopyOverdue(copy, now)
            return (
              <li key={copy.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className="font-mono text-xs font-medium">{copy.code}</span>
                <CopyStatusBadge status={copy.status} overdue={overdue} />
                {copy.status === "borrowed" && copy.due_at && (
                  <span className="text-xs text-muted-foreground">
                    Due back {formatDueDate(copy.due_at)}
                  </span>
                )}
                {/* Only staff get the active loan; for members it is always null. */}
                {copy.active_loan && (
                  <span className="text-xs text-muted-foreground">
                    ·{" "}
                    <MemberLink member={copy.active_loan.member} onClick={onNavigate} className="font-medium" />
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </article>
  )
}

type LoanRowsProps = {
  loans: LoanOut[]
  /** Show each loan's member, linking to the member's page. */
  showMember: boolean
  onNavigate: () => void
}

function LoanRows({ loans, showMember, onNavigate }: LoanRowsProps) {
  const now = useNow()
  if (loans.length === 0) return <p className="text-sm text-muted-foreground">No loans to show.</p>

  return (
    <ul aria-label={plural(loans.length, "loan", "loans")} className="divide-y rounded-lg border bg-card shadow-xs">
      {loans.map((loan) => (
        <li key={loan.id} className="flex items-start justify-between gap-3 p-3">
          <div className="min-w-0">
            <BookTitleLink book={loan.book} onNavigate={onNavigate} />
            {showMember && (
              <p className="text-sm">
                <MemberLink member={loan.member} onClick={onNavigate} />
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">{loan.copy.code}</span>
              {!loan.returned_at && ` · Due ${formatDueDate(loan.due_at)}`}
            </p>
          </div>
          <div className="shrink-0 text-right text-sm">
            {loan.returned_at ? <LoanState loan={loan} /> : <DueState loan={loan} now={now} />}
          </div>
        </li>
      ))}
    </ul>
  )
}

function MemberRows({ members, onNavigate }: { members: MemberOut[]; onNavigate: () => void }) {
  if (members.length === 0) return <p className="text-sm text-muted-foreground">No members matched.</p>

  return (
    <ul
      aria-label={plural(members.length, "member", "members")}
      className="divide-y rounded-lg border bg-card shadow-xs"
    >
      {members.map((member) => (
        <li key={member.id} className="flex items-start justify-between gap-3 p-3">
          <div className="min-w-0">
            <MemberLink member={member} onClick={onNavigate} className="font-medium" />
            {member.email && <p className="truncate text-xs text-muted-foreground">{member.email}</p>}
          </div>
          <span className="shrink-0 text-sm whitespace-nowrap text-muted-foreground">
            {member.active_loans === 0
              ? "No active loans"
              : plural(member.active_loans, "active loan", "active loans")}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** One copy found by its code: its book, where it stands, and who has it. */
function CopySummary({ lookup, onNavigate }: { lookup: CopyLookupOut; onNavigate: () => void }) {
  const loan = lookup.active_loan
  return (
    <article aria-label={`Copy ${lookup.copy.code}`} className="rounded-lg border bg-card p-3 shadow-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-medium">{lookup.copy.code}</span>
        <CopyLookupBadge lookup={lookup} />
      </div>
      <div className="mt-2">
        <BookTitleLink book={lookup.book} onNavigate={onNavigate} />
        <p className="text-xs text-muted-foreground">{lookup.book.author}</p>
      </div>
      {loan && (
        <p className="mt-2 text-sm">
          Borrowed by <MemberLink member={loan.member} onClick={onNavigate} className="font-medium" />
          <span className="text-muted-foreground"> · Due {formatDueDate(loan.due_at)}</span>
        </p>
      )}
    </article>
  )
}

function CategoryChips({
  categories,
  onAsk,
  busy,
}: {
  categories: string[]
  onAsk: (message: string) => void
  busy: boolean
}) {
  return (
    <ul aria-label="Categories" className="flex flex-wrap gap-2">
      {categories.map((category) => (
        <li key={category}>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
            disabled={busy}
            aria-label={`Show me ${category} books`}
            onClick={() => onAsk(`Show me ${category} books`)}
          >
            {category}
          </Button>
        </li>
      ))}
    </ul>
  )
}
