import type { RefObject } from "react"

import { useBook } from "@/features/books/hooks"
import { BorrowDialog } from "@/features/loans/borrow-dialog"
import type { BorrowTarget } from "@/features/loans/hooks"
import type { LoanOut } from "@/lib/types"

type BorrowBookDialogProps = {
  /** From useBorrowByBookId, which loads the book before it opens the dialog. */
  target: BorrowTarget
  onOpenChange: (open: boolean) => void
  onBorrowed?: (loan: LoanOut) => void
  returnFocusTo?: RefObject<HTMLElement | null>
}

/** The borrow dialog for a book known by its id. The book stays current while the dialog is open. */
export function BorrowBookDialog({ target, ...dialog }: BorrowBookDialogProps) {
  const book = useBook(target.bookId ?? "", { enabled: target.bookId !== null })
  if (!book.data) return null
  return <BorrowDialog book={book.data} copyId={target.copyId} open={target.open} {...dialog} />
}
