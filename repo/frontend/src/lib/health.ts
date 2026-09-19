import { ApiError, apiRequest } from "@/lib/api"

export type ApiHealth = "ok" | "database_unavailable" | "unreachable"

/**
 * Asks the backend whether it is up.
 *
 * GET /api/health answers 2xx when the API and its database are up, and 503
 * when the API is up but cannot reach the database. Any other answer, or no
 * answer at all, means the API is unreachable.
 */
export async function fetchApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  try {
    await apiRequest<unknown>("/api/health", { signal, timeoutMs: 5_000 })
    return "ok"
  } catch (error) {
    if (error instanceof ApiError) {
      return error.status === 503 ? "database_unavailable" : "unreachable"
    }
    // The query was cancelled. The query library handles that itself.
    throw error
  }
}
