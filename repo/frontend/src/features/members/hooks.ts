import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { activityKeys } from "@/features/activity/api"
import { createMember, fetchMember, fetchMembers, memberKeys } from "@/features/members/api"
import type { ListParams } from "@/lib/types"

export function useMembers(params: ListParams, { enabled = true } = {}) {
  return useQuery({
    queryKey: memberKeys.list(params),
    queryFn: ({ signal }) => fetchMembers(params, signal),
    placeholderData: keepPreviousData,
    enabled,
  })
}

/** One member with their loan count. A missing member is a 404 not_found. */
export function useMember(id: string) {
  return useQuery({
    queryKey: memberKeys.detail(id),
    queryFn: ({ signal }) => fetchMember(id, signal),
  })
}

export function useCreateMember() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createMember,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: memberKeys.all })
      void queryClient.invalidateQueries({ queryKey: activityKeys.all })
    },
  })
}
