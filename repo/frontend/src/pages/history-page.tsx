import { History } from "lucide-react"

import { PageHeader } from "@/components/layout/page-header"
import { Pager } from "@/components/list/pager"
import { EmptyState } from "@/components/states/empty-state"
import { LoadingState } from "@/components/states/loading-state"
import { QueryState } from "@/components/states/query-state"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BookLink } from "@/features/loans/book-link"
import { useMyLoans } from "@/features/loans/hooks"
import { useUrlSearch } from "@/hooks/use-url-search"
import { formatDate } from "@/lib/format"
import type { LoanOut } from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 20

/** The signed-in member's returned loans, most recently returned first. */
export function HistoryPage() {
  const { page, setPage } = useUrlSearch()
  const offset = (page - 1) * PAGE_SIZE
  const loans = useMyLoans({ status: "returned", limit: PAGE_SIZE, offset })

  const empty =
    (loans.data?.total ?? 0) > 0 ? (
      <EmptyState icon={History} title="This page is empty" description="The list is shorter now.">
        <Button variant="outline" size="sm" onClick={() => setPage(1)}>
          Go to the first page
        </Button>
      </EmptyState>
    ) : (
      <EmptyState
        icon={History}
        title="No history yet"
        description="Books you return will appear here with the dates you had them."
      />
    )

  return (
    <>
      <PageHeader title="History" description="Books you borrowed and returned, newest first." />
      <QueryState
        query={loans}
        isEmpty={(result) => result.items.length === 0}
        empty={empty}
        loading={<LoadingState rows={5} label="Loading your history" />}
        errorTitle="Could not load your history"
      >
        {(result) => (
          <div
            className={cn("transition-opacity", loans.isPlaceholderData && "opacity-60")}
            aria-busy={loans.isPlaceholderData || undefined}
          >
            <Card className="py-0">
              <ReturnedLoansTable loans={result.items} />
            </Card>
            <Pager
              total={result.total}
              limit={result.limit}
              offset={result.offset}
              noun={["loan", "loans"]}
              onPageChange={setPage}
            />
          </div>
        )}
      </QueryState>
    </>
  )
}

function ReturnedLoansTable({ loans }: { loans: LoanOut[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Book</TableHead>
          <TableHead className="hidden sm:table-cell">Copy</TableHead>
          <TableHead>Borrowed</TableHead>
          <TableHead>Returned</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loans.map((loan) => (
          <TableRow key={loan.id}>
            <TableCell className="max-w-0 min-w-32 md:w-2/5">
              <BookLink book={loan.book} />
              <span className="block truncate text-xs text-muted-foreground">
                {loan.book.author}
              </span>
            </TableCell>
            <TableCell className="hidden font-mono text-xs whitespace-nowrap sm:table-cell">
              {loan.copy.code}
            </TableCell>
            <TableCell className="whitespace-nowrap text-muted-foreground">
              {formatDate(loan.borrowed_at)}
            </TableCell>
            <TableCell className="whitespace-nowrap">
              {loan.returned_at && formatDate(loan.returned_at)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
