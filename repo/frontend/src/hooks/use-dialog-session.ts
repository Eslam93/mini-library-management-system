import { useState } from "react"

/**
 * A number that changes each time `open` turns true. Used as a React key, it
 * gives a dialog's form a fresh state on every opening while still letting
 * the closing animation play with the old content.
 */
export function useDialogSession(open: boolean): number {
  const [session, setSession] = useState(0)
  const [wasOpen, setWasOpen] = useState(open)
  if (open !== wasOpen) {
    setWasOpen(open)
    if (open) setSession(session + 1)
  }
  return session
}
