import type { ReactNode } from "react"
import { useLocation } from "react-router"

import { ErrorBoundary } from "@/components/states/error-boundary"

/** An error boundary that clears itself when the user moves to another page. */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  return <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>
}
