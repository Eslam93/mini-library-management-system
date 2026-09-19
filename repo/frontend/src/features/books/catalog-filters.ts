import { useSearchParams } from "react-router"

import type { BookSort } from "@/lib/types"

export const BOOK_SORTS: readonly { value: BookSort; label: string }[] = [
  { value: "title", label: "Title" },
  { value: "author", label: "Author" },
  { value: "year_desc", label: "Newest" },
  { value: "recent", label: "Recently added" },
]

const DEFAULT_SORT: BookSort = "title"

/** The URL parameters the catalog's filters and order live in. The search and the page have their own. */
export const CATALOG_FILTER_KEYS = ["category", "available_only", "sort"] as const

function readSort(value: string | null): BookSort {
  return BOOK_SORTS.find((sort) => sort.value === value)?.value ?? DEFAULT_SORT
}

/**
 * The catalog's filters and order, kept in the URL beside the search, so a
 * link or the back button brings them along. The URL uses the API's own
 * parameter names and leaves out a default. Any change starts again at page 1.
 */
export function useCatalogFilters() {
  const [searchParams, setSearchParams] = useSearchParams()
  const category = searchParams.get("category") ?? ""
  const availableOnly = searchParams.get("available_only") === "true"
  const sort = readSort(searchParams.get("sort"))
  const filtered = category !== "" || availableOnly

  function update(changes: Partial<Record<(typeof CATALOG_FILTER_KEYS)[number], string | null>>) {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(changes)) {
        if (value) params.set(key, value)
        else params.delete(key)
      }
      params.delete("page")
      return params
    })
  }

  return {
    category,
    availableOnly,
    sort,
    /** A filter narrows the list; the order does not. */
    filtered,
    /** Anything differs from the catalog as it first opens. */
    changed: filtered || sort !== DEFAULT_SORT,
    setCategory: (next: string) => update({ category: next || null }),
    setAvailableOnly: (next: boolean) => update({ available_only: next ? "true" : null }),
    setSort: (next: BookSort) => update({ sort: next === DEFAULT_SORT ? null : next }),
    clearFilters: () => update({ category: null, available_only: null }),
  }
}

export type CatalogFilters = ReturnType<typeof useCatalogFilters>
