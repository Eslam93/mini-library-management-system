import type { QueryClient } from "@tanstack/react-query"

import { authKeys } from "@/features/auth/api"
import type { UserOut } from "@/lib/types"

export const SIGN_IN_PATH = "/sign-in"

/** What the sign-in guard tells the sign-in page through the navigation state. */
type SignInState = { sessionEnded: true }

export const SESSION_ENDED_STATE: SignInState = { sessionEnded: true }

export function isSessionEndedState(state: unknown): boolean {
  return typeof state === "object" && state !== null && "sessionEnded" in state
}

/**
 * A new person signed in on this tab. Every cached answer belonged to the
 * person before, and could show them data they may not see, so it all goes.
 */
export function startSession(queryClient: QueryClient, user: UserOut) {
  queryClient.removeQueries()
  queryClient.setQueryData(authKeys.me(), user)
}

/**
 * The API refused a request with 401: the session expired or was revoked
 * elsewhere. Marking nobody as signed in sends the sign-in guard to the
 * sign-in page. Only the first refusal acts, so requests that fail together
 * lead to one redirect.
 *
 * The session's cached data is left to expire on its own once no page uses
 * it: removing it here, under pages still mounted, would make them fetch it
 * again. startSession drops it before anyone else signs in.
 */
export function endSession(queryClient: QueryClient) {
  if (!queryClient.getQueryData(authKeys.me())) return
  queryClient.setQueryData(authKeys.me(), null)
}

/**
 * Where to go after signing in, or null when `raw` is not a page of this app.
 *
 * `next` arrives in a link anyone can write, so only a relative path with one
 * leading slash is kept. "//host" and "/\host" are read by browsers as another
 * site, control characters can hide a second slash from this check, and the
 * sign-in page itself would only loop. The parsed path is checked again,
 * because resolving "/.//host" yields "//host".
 */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return null
  for (const char of raw) {
    const code = char.charCodeAt(0)
    if (code < 0x20 || code === 0x7f) return null
  }

  const base = "http://library.invalid"
  let url: URL
  try {
    url = new URL(raw, base)
  } catch {
    return null
  }
  if (url.origin !== base || url.pathname.startsWith("//")) return null
  if (url.pathname === SIGN_IN_PATH || url.pathname.startsWith(`${SIGN_IN_PATH}/`)) return null
  return `${url.pathname}${url.search}${url.hash}`
}

/** The sign-in page, set to come back to `here` (a path with its query) afterwards. */
export function signInPath(here: string): string {
  const next = safeNextPath(here)
  if (!next || next === "/") return SIGN_IN_PATH
  return `${SIGN_IN_PATH}?${new URLSearchParams({ next })}`
}
