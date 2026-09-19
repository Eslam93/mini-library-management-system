import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query"

import { ApiError } from "@/lib/api"

type QueryClientOptions = {
  /**
   * Called when the API refuses a query or a mutation with 401, which means
   * the session is over. The session check itself reads 401 as "signed out"
   * and never gets here.
   */
  onUnauthorized?: (queryClient: QueryClient) => void
}

export function createQueryClient({ onUnauthorized }: QueryClientOptions = {}) {
  const reportUnauthorized = (error: Error) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized?.(queryClient)
  }

  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: reportUnauthorized }),
    mutationCache: new MutationCache({ onError: reportUnauthorized }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // A 4xx answer will not change on retry. Other failures get two more tries.
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
          return failureCount < 2
        },
      },
    },
  })
  return queryClient
}
