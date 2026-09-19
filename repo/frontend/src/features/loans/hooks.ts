import { useState } from "react"
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query"

import { activityKeys } from "@/features/activity/api"
import { bookKeys, fetchBook } from "@/features/books/api"
import { copyKeys } from "@/features/circulation/api"
import { dashboardKeys } from "@/features/dashboard/api"
import { borrowCopy, fetchLoans, fetchMyLoans, loanKeys, returnLoan } from "@/features/loans/api"
import { memberKeys } from "@/features/members/api"
import { ApiError } from "@/lib/api"
import type { LoansParams, MyLoansParams } from "@/lib/types"

/** Everything that shows loans or counts them, apart from the book itself. */
function refreshLoanViews(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: bookKeys.lists() })
  void queryClient.invalidateQueries({ queryKey: loanKeys.all })
  void queryClient.invalidateQueries({ queryKey: copyKeys.all })
  void queryClient.invalidateQueries({ queryKey: dashboardKeys.all })
}

/**
 * A loan changes the book's copies, the catalog's availability, the loans
 * lists, the member's page and counts, the dashboard and the activity.
 */
export function refreshAfterLoanChange(queryClient: QueryClient, bookId: string) {
  void queryClient.invalidateQueries({ queryKey: bookKeys.detail(bookId) })
  void queryClient.invalidateQueries({ queryKey: memberKeys.all })
  void queryClient.invalidateQueries({ queryKey: activityKeys.all })
  refreshLoanViews(queryClient)
}

/** Conflicts that mean the page showed an old state of the book or the loan. */
const STALE_LOAN_CODES = new Set(["copy_unavailable", "book_archived", "loan_already_returned"])

function refreshOnConflict(queryClient: QueryClient, bookId: string, error: Error) {
  if (error instanceof ApiError && STALE_LOAN_CODES.has(error.code)) {
    void queryClient.invalidateQueries({ queryKey: bookKeys.detail(bookId) })
    void queryClient.invalidateQueries({ queryKey: memberKeys.all })
    refreshLoanViews(queryClient)
  }
}

/** Borrows a copy of the book `bookId`. */
export function useBorrowCopy(bookId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: borrowCopy,
    onSuccess: (loan) => refreshAfterLoanChange(queryClient, loan.book.id),
    onError: (error) => refreshOnConflict(queryClient, bookId, error),
  })
}

/** Returns a loan on a copy of the book `bookId`. */
export function useReturnLoan(bookId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: returnLoan,
    onSuccess: (loan) => refreshAfterLoanChange(queryClient, loan.book.id),
    onError: (error) => refreshOnConflict(queryClient, bookId, error),
  })
}

/** The signed-in member's loans, active or returned, one page at a time. */
export function useMyLoans(params: MyLoansParams) {
  return useQuery({
    queryKey: loanKeys.mine(params),
    queryFn: ({ signal }) => fetchMyLoans(params, signal),
    // Keep the current page on screen while the next one loads.
    placeholderData: keepPreviousData,
  })
}

/** Loans of every member, for staff, one page at a time. */
export function useLoans(params: LoansParams) {
  return useQuery({
    queryKey: loanKeys.list(params),
    queryFn: ({ signal }) => fetchLoans(params, signal),
    // Keep the current page on screen while the next search, tab or page loads.
    placeholderData: keepPreviousData,
  })
}

/** The book and copy the borrow dialog is for. Kept while the dialog closes, so its closing animation still shows them. */
export type BorrowTarget = {
  open: boolean
  bookId: string | null
  copyId: string | null
}

/**
 * Borrowing for a book known only by its id, such as one found by copy code
 * or by a search. `start` loads the book with its copies first, so the
 * dialog opens with the copy choice ready, and a failure to load shows where
 * staff asked for it.
 */
export function useBorrowByBookId() {
  const queryClient = useQueryClient()
  const [target, setTarget] = useState<BorrowTarget>({ open: false, bookId: null, copyId: null })
  const loadBook = useMutation({
    mutationFn: (bookId: string) =>
      // Always fresh: the dialog offers only the copies available now.
      queryClient.fetchQuery({
        queryKey: bookKeys.detail(bookId),
        queryFn: ({ signal }) => fetchBook(bookId, signal),
        staleTime: 0,
      }),
  })

  /** Loads the book, then opens the dialog and calls `onOpened`. `copyId` preselects a copy. */
  function start(bookId: string, copyId: string | null = null, onOpened?: () => void) {
    loadBook.mutate(bookId, {
      onSuccess: () => {
        setTarget({ open: true, bookId, copyId })
        onOpened?.()
      },
    })
  }

  function setOpen(open: boolean) {
    setTarget((current) => ({ ...current, open }))
  }

  return {
    target,
    start,
    setOpen,
    loading: loadBook.isPending,
    loadError: loadBook.error,
    clearLoadError: loadBook.reset,
  }
}
