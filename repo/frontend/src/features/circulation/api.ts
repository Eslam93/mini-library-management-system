import { apiRequest } from "@/lib/api"
import type { CopyLookupOut } from "@/lib/types"

export const copyKeys = {
  all: ["copies"] as const,
  byCode: (code: string) => [...copyKeys.all, "by-code", code] as const,
}

/** A copy by its code, with its book and its active loan. 404 not_found for an unknown code. */
export function fetchCopyByCode(code: string, signal?: AbortSignal) {
  return apiRequest<CopyLookupOut>(`/api/copies/by-code/${encodeURIComponent(code)}`, { signal })
}
