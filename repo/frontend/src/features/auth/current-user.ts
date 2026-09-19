import { createContext, useContext } from "react"

import type { UserOut } from "@/lib/types"

/** The signed-in user. The sign-in guard provides it to every page behind it. */
export const CurrentUserContext = createContext<UserOut | null>(null)

/** The signed-in user, for pages behind the sign-in guard. */
export function useCurrentUser(): UserOut {
  const user = useContext(CurrentUserContext)
  if (!user) throw new Error("useCurrentUser was called outside the signed-in part of the app.")
  return user
}

export function useIsStaff(): boolean {
  return useCurrentUser().role === "staff"
}
