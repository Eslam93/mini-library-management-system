import { useQuery } from "@tanstack/react-query"

import { activityKeys, fetchActivity } from "@/features/activity/api"

/** The newest actions first. The API returns at most 200. */
export function useActivity(limit = 50) {
  return useQuery({
    queryKey: activityKeys.list(limit),
    queryFn: ({ signal }) => fetchActivity(limit, signal),
  })
}
