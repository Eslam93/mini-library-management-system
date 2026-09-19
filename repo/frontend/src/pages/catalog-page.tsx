import { useState } from "react"
import { BookOpen, Plus, SearchX } from "lucide-react"

import { PageHeader } from "@/components/layout/page-header"
import { Pager } from "@/components/list/pager"
import { SearchField } from "@/components/list/search-field"
import { EmptyState } from "@/components/states/empty-state"
import { LoadingState } from "@/components/states/loading-state"
import { QueryState } from "@/components/states/query-state"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { useIsStaff } from "@/features/auth/current-user"
import { BookFormDialog } from "@/features/books/book-form-dialog"
import { BooksTable } from "@/features/books/books-table"
import { CatalogFilterBar } from "@/features/books/catalog-filter-bar"
import { CATALOG_FILTER_KEYS, useCatalogFilters } from "@/features/books/catalog-filters"
import { useBooks } from "@/features/books/hooks"
import { useUrlSearch } from "@/hooks/use-url-search"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 20

/** The catalog for everyone, with its search, filters and order in the URL. Only staff can add books. */
export function CatalogPage() {
  const isStaff = useIsStaff()
  const search = useUrlSearch()
  const filters = useCatalogFilters()
  const [adding, setAdding] = useState(false)
  const offset = (search.page - 1) * PAGE_SIZE
  const books = useBooks({
    q: search.q || undefined,
    category: filters.category || undefined,
    available_only: filters.availableOnly || undefined,
    sort: filters.sort === "title" ? undefined : filters.sort,
    limit: PAGE_SIZE,
    offset,
  })

  const addBook = (
    <Button onClick={() => setAdding(true)}>
      <Plus aria-hidden />
      Add book
    </Button>
  )

  function emptyState(total: number) {
    if (filters.filtered && total === 0) {
      return (
        <EmptyState
          icon={SearchX}
          title={search.q ? `No books match "${search.q}" with these filters` : "No books match these filters"}
          description="Clear the filters to see the rest of the catalog."
        >
          <Button variant="outline" size="sm" onClick={filters.clearFilters}>
            Clear filters
          </Button>
        </EmptyState>
      )
    }
    if (search.q && total === 0) {
      return (
        <EmptyState
          icon={SearchX}
          title={`No books match "${search.q}"`}
          description="Search looks at titles, authors and ISBNs, and matches parts of words. Check the spelling or try fewer letters."
        >
          <Button variant="outline" size="sm" onClick={search.clear}>
            Clear search
          </Button>
        </EmptyState>
      )
    }
    if (total > 0) {
      return (
        <EmptyState icon={BookOpen} title="This page is empty" description="The list is shorter now.">
          <Button variant="outline" size="sm" onClick={() => search.setPage(1)}>
            Go to the first page
          </Button>
        </EmptyState>
      )
    }
    if (!isStaff) {
      return (
        <EmptyState
          icon={BookOpen}
          title="No books yet"
          description="The library has not added any books yet. Books will show here with whether a copy can be borrowed."
        />
      )
    }
    return (
      <EmptyState
        icon={BookOpen}
        title="No books yet"
        description="Add the first book. Each book shows here with how many of its copies can be borrowed."
      >
        <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          Add book
        </Button>
      </EmptyState>
    )
  }

  return (
    <>
      <PageHeader
        title="Catalog"
        description="Books in the library and whether a copy can be borrowed."
        actions={isStaff && addBook}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SearchField
          label="Search the catalog"
          placeholder="Search by title, author or ISBN"
          value={search.draft}
          onChange={search.changeDraft}
          onClear={search.clear}
          busy={books.isFetching && books.isPlaceholderData}
          className="min-w-56 flex-1 basis-64 sm:max-w-sm"
        />
        <CatalogFilterBar filters={filters} />
        {(search.q || filters.changed) && (
          <Button variant="ghost" onClick={() => search.reset(CATALOG_FILTER_KEYS)}>
            Clear all
          </Button>
        )}
      </div>
      <QueryState
        query={books}
        isEmpty={(page) => page.items.length === 0}
        empty={emptyState(books.data?.total ?? 0)}
        loading={<LoadingState rows={5} label="Loading books" />}
        errorTitle="Could not load the catalog"
      >
        {(page) => (
          <div
            className={cn("transition-opacity", books.isPlaceholderData && "opacity-60")}
            aria-busy={books.isPlaceholderData || undefined}
          >
            <Card className="py-0">
              <BooksTable books={page.items} />
            </Card>
            <Pager
              total={page.total}
              limit={page.limit}
              offset={page.offset}
              noun={["book", "books"]}
              onPageChange={search.setPage}
            />
          </div>
        )}
      </QueryState>
      {isStaff && <BookFormDialog open={adding} onOpenChange={setAdding} />}
    </>
  )
}
