import { Link } from "react-router"

import type { BookRef } from "@/lib/types"

type BookTitleLinkProps = {
  book: Pick<BookRef, "id" | "title">
  /** Following the link leaves for a page, so the panel closes. */
  onNavigate: () => void
}

/** A book's title in a Copilot card, linking to the book's page. */
export function BookTitleLink({ book, onNavigate }: BookTitleLinkProps) {
  return (
    <Link
      to={`/books/${book.id}`}
      onClick={onNavigate}
      className="rounded-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {book.title}
    </Link>
  )
}
