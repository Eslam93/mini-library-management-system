import { apiRequest } from "@/lib/api"
import type { DashboardOut } from "@/lib/types"

export const dashboardKeys = {
  all: ["dashboard"] as const,
}

export function fetchDashboard(signal?: AbortSignal) {
  return apiRequest<DashboardOut>("/api/dashboard", { signal })
}
