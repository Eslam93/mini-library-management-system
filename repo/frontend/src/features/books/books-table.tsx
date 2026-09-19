import { Link, useNavigate } from "react-router"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AvailabilityBadge } from "@/features/books/availability-badge"
import { BookCover } from "@/features/books/book-cover"
import type { BookSummary } from "@/lib/types"

/**
 * The catalog list. The title is the link for keyboard and screen reader
 * users; a click anywhere on the row opens the book too.
 */
export function BooksTable({ books }: { books: BookSummary[] }) {
  const navigate = useNavigate()

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Title</TableHead>
          <TableHead className="hidden md:table-cell">Author</TableHead>
          <TableHead className="hidden lg:table-cell">Category</TableHead>
          <TableHead className="hidden sm:table-cell">Year</TableHead>
          <TableHead>Availability</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {books.map((book) => (
          <TableRow
            key={book.id}
            className="cursor-pointer"
            onClick={(event) => {
              // The title link navigates by itself.
              if ((event.target as HTMLElement).closest("a")) return
              navigate(`/books/${book.id}`)
            }}
          >
            <TableCell className="max-w-0 min-w-44 md:w-2/5">
              <div className="flex items-center gap-3">
                <BookCover book={book} size="S" />
                <div className="min-w-0">
                  <Link
                    to={`/books/${book.id}`}
                    className="block truncate rounded-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    {book.title}
                  </Link>
                  <span className="block truncate text-xs text-muted-foreground md:hidden">
                    {book.author}
                  </span>
                </div>
              </div>
            </TableCell>
            <TableCell className="hidden md:table-cell">{book.author}</TableCell>
            <TableCell className="hidden text-muted-foreground lg:table-cell">
              {book.category}
            </TableCell>
            <TableCell className="hidden text-muted-foreground tabular-nums sm:table-cell">
              {book.published_year}
            </TableCell>
            <TableCell>
              <AvailabilityBadge book={book} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
