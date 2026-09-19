import { Link } from "react-router"

import type { LoanOut } from "@/lib/types"

/** A loan's book title, linking to the book's page. */
export function BookLink({ book }: { book: LoanOut["book"] }) {
  return (
    <Link
      to={`/books/${book.id}`}
      className="block truncate rounded-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {book.title}
    </Link>
  )
}
