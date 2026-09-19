import { useState } from "react"
import { Loader2 } from "lucide-react"
import { Navigate, Outlet, useLocation } from "react-router"

import { ErrorState } from "@/components/states/error-state"
import { CurrentUserContext } from "@/features/auth/current-user"
import { useMe } from "@/features/auth/hooks"
import { SESSION_ENDED_STATE, signInPath } from "@/features/auth/session"

/**
 * Lets signed-in users through to the routes under it and gives them the
 * current user. Anyone else goes to the sign-in page, which brings them back
 * to the page they asked for.
 */
export function RequireSignIn() {
  const me = useMe()
  const location = useLocation()
  // Losing a user this guard already let in means the session ended while in
  // use, which the sign-in page says. A first visit is just not signed in yet.
  const [admitted, setAdmitted] = useState(false)
  if (me.data && !admitted) setAdmitted(true)

  if (me.data) {
    return (
      <CurrentUserContext value={me.data}>
        <Outlet />
      </CurrentUserContext>
    )
  }

  if (me.data === null) {
    return (
      <Navigate
        to={signInPath(`${location.pathname}${location.search}`)}
        replace
        state={admitted ? SESSION_ENDED_STATE : undefined}
      />
    )
  }

  return (
    <div className="flex min-h-dvh items-center justify-center p-4">
      {me.isError ? (
        <ErrorState
          title="Could not check your sign-in"
          error={me.error}
          onRetry={() => void me.refetch()}
          className="w-full max-w-md"
        />
      ) : (
        <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
          Checking your sign-in
        </div>
      )}
    </div>
  )
}
