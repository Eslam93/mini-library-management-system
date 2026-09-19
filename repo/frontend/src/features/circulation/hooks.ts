import { useQuery } from "@tanstack/react-query"

import { copyKeys, fetchCopyByCode } from "@/features/circulation/api"

/**
 * The copy behind a code typed or scanned at the desk. Every lookup asks the
 * API again and nothing is kept once the page moves on, so a copy scanned a
 * second time never shows the state it had before.
 */
export function useCopyLookup(code: string | null) {
  return useQuery({
    queryKey: copyKeys.byCode(code ?? ""),
    queryFn: ({ signal }) => fetchCopyByCode(code ?? "", signal),
    enabled: code !== null,
    staleTime: 0,
    gcTime: 0,
  })
}
