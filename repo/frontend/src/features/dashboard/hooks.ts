import { useQuery } from "@tanstack/react-query"

import { dashboardKeys, fetchDashboard } from "@/features/dashboard/api"

/** The dashboard's counts and lists, all from one request. */
export function useDashboard() {
  return useQuery({
    queryKey: dashboardKeys.all,
    queryFn: ({ signal }) => fetchDashboard(signal),
  })
}
