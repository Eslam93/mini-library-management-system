import { RefreshCw, TriangleAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

type ErrorStateProps = {
  error?: unknown
  title?: string
  onRetry?: () => void
  className?: string
}

/**
 * Shows a failure with a way to try again. Messages from the API are shown
 * as sent. Any other error gets a generic message, so internal details stay
 * out of the page.
 */
export function ErrorState({
  error,
  title = "Something went wrong",
  onRetry,
  className,
}: ErrorStateProps) {
  const apiError = error instanceof ApiError ? error : undefined
  const message = apiError?.message ?? "An unexpected error stopped this view from loading."

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-4 rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-12 text-center",
        className,
      )}
    >
      <div className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <TriangleAlert className="size-6" aria-hidden />
      </div>
      <div className="max-w-md space-y-1">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw aria-hidden />
          Try again
        </Button>
      )}
      {apiError?.requestId && (
        <p className="text-xs text-muted-foreground">
          Request ID: <code className="font-mono">{apiError.requestId}</code>
        </p>
      )}
    </div>
  )
}
