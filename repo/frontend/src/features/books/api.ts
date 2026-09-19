import { apiRequest } from "@/lib/api"
import { withSearchParams } from "@/lib/search-params"
import type {
  BookCreate,
  BookDetail,
  BookSummary,
  BooksParams,
  BookUpdate,
  DeleteBookResult,
  IsbnLookupOut,
  Page,
} from "@/lib/types"

export const bookKeys = {
  all: ["books"] as const,
  lists: () => [...bookKeys.all, "list"] as const,
  list: (params: BooksParams) => [...bookKeys.lists(), params] as const,
  detail: (id: string) => [...bookKeys.all, "detail", id] as const,
  categories: () => [...bookKeys.all, "categories"] as const,
}

function bookPath(id: string) {
  return `/api/books/${encodeURIComponent(id)}`
}

export function fetchBooks(params: BooksParams, signal?: AbortSignal) {
  return apiRequest<Page<BookSummary>>(withSearchParams("/api/books", params), { signal })
}

/** The categories of the books in the catalog, alphabetically. */
export function fetchBookCategories(signal?: AbortSignal) {
  return apiRequest<string[]>("/api/books/categories", { signal })
}

export function fetchBook(id: string, signal?: AbortSignal) {
  return apiRequest<BookDetail>(bookPath(id), { signal })
}

export function createBook(body: BookCreate) {
  return apiRequest<BookDetail>("/api/books", { method: "POST", body })
}

export function updateBook(id: string, body: BookUpdate) {
  return apiRequest<BookDetail>(bookPath(id), { method: "PATCH", body })
}

export function deleteBook(id: string) {
  return apiRequest<DeleteBookResult>(bookPath(id), { method: "DELETE" })
}

export function addCopies(id: string, count: number) {
  return apiRequest<BookDetail>(`${bookPath(id)}/copies`, { method: "POST", body: { count } })
}

/** Title, author and year for a normalized ISBN, from the public book service the API asks. */
export function lookupIsbn(isbn: string) {
  return apiRequest<IsbnLookupOut>(`/api/isbn/${encodeURIComponent(isbn)}`)
}
