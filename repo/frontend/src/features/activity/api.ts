import { apiRequest } from "@/lib/api"
import { withSearchParams } from "@/lib/search-params"
import type { ActivityOut } from "@/lib/types"

export const activityKeys = {
  all: ["activity"] as const,
  list: (limit: number) => [...activityKeys.all, { limit }] as const,
}

export function fetchActivity(limit: number, signal?: AbortSignal) {
  return apiRequest<ActivityOut[]>(withSearchParams("/api/activity", { limit }), { signal })
}
