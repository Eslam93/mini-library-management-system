import { apiRequest } from "@/lib/api"
import { withSearchParams } from "@/lib/search-params"
import type { ListParams, MemberCreate, MemberDetailOut, MemberOut, Page } from "@/lib/types"

export const memberKeys = {
  all: ["members"] as const,
  list: (params: ListParams) => [...memberKeys.all, "list", params] as const,
  detail: (id: string) => [...memberKeys.all, "detail", id] as const,
}

export function fetchMembers(params: ListParams, signal?: AbortSignal) {
  return apiRequest<Page<MemberOut>>(withSearchParams("/api/members", params), { signal })
}

export function fetchMember(id: string, signal?: AbortSignal) {
  return apiRequest<MemberDetailOut>(`/api/members/${encodeURIComponent(id)}`, { signal })
}

export function createMember(body: MemberCreate) {
  return apiRequest<MemberOut>("/api/members", { method: "POST", body })
}
