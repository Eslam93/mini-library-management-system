import { useQuery } from "@tanstack/react-query"

import { fetchApiHealth, type ApiHealth } from "@/lib/health"
import { cn } from "@/lib/utils"

const labels: Record<ApiHealth, string> = {
  ok: "API ok",
  database_unavailable: "database unavailable",
  unreachable: "API unreachable",
}

const dotColors: Record<ApiHealth, string> = {
  ok: "bg-available",
  database_unavailable: "bg-borrowed",
  unreachable: "bg-destructive",
}

/** A small badge that shows whether the API and its database answer. */
export function ApiStatus() {
  const query = useQuery({
    queryKey: ["api-health"],
    queryFn: ({ signal }) => fetchApiHealth(signal),
    refetchInterval: 30_000,
    retry: false,
  })
  const health: ApiHealth | undefined = query.isError ? "unreachable" : query.data

  return (
    <div
      role="status"
      className="inline-flex items-center gap-2 rounded-full border bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground"
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          health ? dotColors[health] : "animate-pulse bg-muted-foreground/40",
        )}
      />
      {health ? labels[health] : "Checking API"}
    </div>
  )
}
