import type { ReactElement } from "react"
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import { render } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router"

import { authKeys } from "@/features/auth/api"
import { CurrentUserContext } from "@/features/auth/current-user"
import { endSession } from "@/features/auth/session"
import { createQueryClient } from "@/lib/query-client"
import type { UserOut } from "@/lib/types"
import { staffUser } from "@/test/fixtures"

type RenderOptions = {
  route?: string
  /**
   * Who is signed in: a signed-in staff user unless given. null means nobody.
   * Pass undefined on purpose to leave the session unknown, so the app asks
   * GET /api/auth/me (stub it).
   */
  user?: UserOut | null
  /** Runs before the first render, such as to put an answer in the cache. */
  prepare?: (queryClient: QueryClient) => void
}

/**
 * Renders with the app's query client (no retries, and the same 401 handling)
 * and an in-memory router. Pages rendered alone get the user as the sign-in
 * guard would give it to them.
 */
export function renderWithProviders(ui: ReactElement, options: RenderOptions = {}) {
  const { route = "/" } = options
  const user = "user" in options ? options.user : staffUser()

  const queryClient = createQueryClient({ onUnauthorized: endSession })
  queryClient.setDefaultOptions({ queries: { retry: false } })
  if (user !== undefined) queryClient.setQueryData(authKeys.me(), user)
  options.prepare?.(queryClient)

  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <CurrentUserContext value={user ?? null}>
          {ui}
          <CurrentLocation />
        </CurrentUserContext>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}

/** The router's current path and query, for tests that check where the app went. */
function CurrentLocation() {
  const { pathname, search } = useLocation()
  return <div data-testid="location" hidden>{`${pathname}${search}`}</div>
}

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}
