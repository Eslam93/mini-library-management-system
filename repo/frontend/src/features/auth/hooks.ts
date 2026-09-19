import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router"

import {
  authKeys,
  demoSignIn,
  fetchAuthConfig,
  fetchMe,
  signOut,
} from "@/features/auth/api"
import { SIGN_IN_PATH, startSession } from "@/features/auth/session"
import { forgetConversations } from "@/features/copilot/conversation"

/**
 * The signed-in user, or null for nobody. Only signing in and out change the
 * answer, and both write it here themselves. A session that ends in between
 * shows up as a 401 on the next request, which the query client turns into
 * a sign-out (see endSession).
 */
export function useMe() {
  return useQuery({
    queryKey: authKeys.me(),
    queryFn: ({ signal }) => fetchMe(signal),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

/** The sign-in methods the API offers. They change only with a server restart. */
export function useAuthConfig() {
  return useQuery({
    queryKey: authKeys.config(),
    queryFn: ({ signal }) => fetchAuthConfig(signal),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

/** Signs in as the demo staff or member user. The caller decides where to go next. */
export function useDemoSignIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: demoSignIn,
    onSuccess: (user) => startSession(queryClient, user),
  })
}

/**
 * Signs out on the server, goes to the sign-in page and clears the query
 * cache and the tab's Copilot conversation, so nothing of this session stays
 * for the next person.
 */
export function useSignOut() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return useMutation({
    mutationFn: signOut,
    onSuccess: () => {
      // Leave the signed-in pages first: were the cache cleared under them,
      // the guard could read the gap as an ended session.
      navigate(SIGN_IN_PATH, { replace: true })
      queryClient.removeQueries()
      forgetConversations()
    },
  })
}
