import type { ReactNode } from "react"
import type { UseQueryResult } from "@tanstack/react-query"

import { EmptyState } from "@/components/states/empty-state"
import { ErrorState } from "@/components/states/error-state"
import { LoadingState } from "@/components/states/loading-state"

type QueryStateProps<T> = {
  query: Pick<UseQueryResult<T>, "data" | "error" | "isError" | "refetch">
  children: (data: T) => ReactNode
  /** Decides when data counts as empty. Defaults to an empty array. */
  isEmpty?: (data: T) => boolean
  loading?: ReactNode
  empty?: ReactNode
  errorTitle?: string
}

function isEmptyArray(data: unknown) {
  return Array.isArray(data) && data.length === 0
}

/**
 * Renders one of four states for a query: loading, error, empty or data.
 * Data already on screen stays visible when a background refresh fails.
 */
export function QueryState<T>({
  query,
  children,
  isEmpty = isEmptyArray,
  loading,
  empty,
  errorTitle,
}: QueryStateProps<T>) {
  if (query.data === undefined) {
    if (query.isError) {
      return (
        <ErrorState title={errorTitle} error={query.error} onRetry={() => void query.refetch()} />
      )
    }
    return loading ?? <LoadingState />
  }
  if (isEmpty(query.data)) return empty ?? <EmptyState title="Nothing here yet" />
  return children(query.data)
}
