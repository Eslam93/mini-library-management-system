import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query"

import { activityKeys } from "@/features/activity/api"
import {
  addCopies,
  bookKeys,
  createBook,
  deleteBook,
  fetchBook,
  fetchBookCategories,
  fetchBooks,
  lookupIsbn,
  updateBook,
} from "@/features/books/api"
import { ApiError } from "@/lib/api"
import type { BookDetail, BooksParams, BookUpdate } from "@/lib/types"

/** Refreshes what a changed book appears in: the lists, the category filter and the activity. */
function refreshAround(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: bookKeys.lists() })
  void queryClient.invalidateQueries({ queryKey: bookKeys.categories() })
  void queryClient.invalidateQueries({ queryKey: activityKeys.all })
}

/** Stores the book the API sent back and refreshes everything that includes it. */
function storeBook(queryClient: QueryClient, book: BookDetail) {
  queryClient.setQueryData(bookKeys.detail(book.id), book)
  refreshAround(queryClient)
}

export function useBooks(params: BooksParams, { enabled = true } = {}) {
  return useQuery({
    queryKey: bookKeys.list(params),
    queryFn: ({ signal }) => fetchBooks(params, signal),
    // Keep the current page on screen while the next search or page loads.
    placeholderData: keepPreviousData,
    enabled,
  })
}

/** The categories for the catalog's filter. */
export function useBookCategories() {
  return useQuery({
    queryKey: bookKeys.categories(),
    queryFn: ({ signal }) => fetchBookCategories(signal),
  })
}

export function useBook(id: string, { enabled = true } = {}) {
  return useQuery({
    queryKey: bookKeys.detail(id),
    queryFn: ({ signal }) => fetchBook(id, signal),
    enabled,
  })
}

export function useCreateBook() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createBook,
    onSuccess: (book) => storeBook(queryClient, book),
  })
}

export function useUpdateBook(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: BookUpdate) => updateBook(id, changes),
    onSuccess: (book) => storeBook(queryClient, book),
  })
}

export function useAddCopies(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (count: number) => addCopies(id, count),
    onSuccess: (book) => storeBook(queryClient, book),
  })
}

export function useDeleteBook(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => deleteBook(id),
    onSuccess: () => {
      // The page moves away next, so mark the book stale without fetching it again.
      void queryClient.invalidateQueries({ queryKey: bookKeys.detail(id), refetchType: "none" })
      refreshAround(queryClient)
    },
    onError: (error) => {
      // A copy went out on loan since the page loaded: show the current copies.
      if (error instanceof ApiError && error.code === "book_has_active_loans") {
        void queryClient.invalidateQueries({ queryKey: bookKeys.detail(id) })
      }
    },
  })
}

/**
 * Asks the API what book an ISBN belongs to. A mutation rather than a query,
 * because it runs when staff press Look up, not when a page shows.
 */
export function useIsbnLookup() {
  return useMutation({ mutationFn: lookupIsbn })
}
