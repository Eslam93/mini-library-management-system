import type { BookDetail, CopyOut } from "@/lib/types"

/** What the dialog shows about the loan it returns. A LoanOut has all of it. */
export type ReturnableLoan = {
  id: string
  book: { id: string; title: string }
  copy: { code: string }
  member: { full_name: string }
  borrowed_at: string
  due_at: string
  is_overdue: boolean
}

/** The active loan of a copy on a book's page, in the shape the dialog takes. */
export function loanOfCopy(book: BookDetail, copy: CopyOut): ReturnableLoan | null {
  const loan = copy.active_loan
  if (!loan) return null
  return {
    id: loan.id,
    book: { id: book.id, title: book.title },
    copy: { code: copy.code },
    member: loan.member,
    borrowed_at: loan.borrowed_at,
    due_at: loan.due_at,
    is_overdue: loan.is_overdue,
  }
}
