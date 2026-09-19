import { ApiError, apiRequest } from "@/lib/api"
import { withSearchParams } from "@/lib/search-params"
import type { AuthConfigOut, Role, UserOut } from "@/lib/types"

export const authKeys = {
  all: ["auth"] as const,
  me: () => [...authKeys.all, "me"] as const,
  config: () => [...authKeys.all, "config"] as const,
}

/** Who is signed in, or null when nobody is: a 401 here is an answer, not a failure. */
export async function fetchMe(signal?: AbortSignal): Promise<UserOut | null> {
  try {
    return await apiRequest<UserOut>("/api/auth/me", { signal })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function fetchAuthConfig(signal?: AbortSignal) {
  return apiRequest<AuthConfigOut>("/api/auth/config", { signal })
}

export function demoSignIn(role: Role) {
  return apiRequest<UserOut>("/api/auth/demo", { method: "POST", body: { role } })
}

export function signOut() {
  return apiRequest<void>("/api/auth/logout", { method: "POST" })
}

/**
 * The Google sign-in start. It is a full page load, not a fetch: the API
 * redirects to Google and, after the callback, back to `next`.
 */
export function googleSignInUrl(next: string | null) {
  return withSearchParams("/api/auth/google/login", { next: next ?? undefined })
}
