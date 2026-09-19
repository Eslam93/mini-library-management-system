import { useState, type ReactNode } from "react"
import { QueryClientProvider } from "@tanstack/react-query"

import { Toaster } from "@/components/ui/sonner"
import { endSession } from "@/features/auth/session"
import { createQueryClient } from "@/lib/query-client"

/** App-wide providers: server data through TanStack Query, and toasts. */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => createQueryClient({ onUnauthorized: endSession }))

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster position="bottom-right" closeButton />
    </QueryClientProvider>
  )
}
