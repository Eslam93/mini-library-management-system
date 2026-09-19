import { useEffect, useRef, useState } from "react"
import { partialMatchKey, useQuery, useQueryClient } from "@tanstack/react-query"

import { endSession } from "@/features/auth/session"
import { copilotKeys, fetchCopilotConfig, streamCopilotChat } from "@/features/copilot/api"
import {
  EMPTY_CONVERSATION,
  lastUserIndex,
  loadConversation,
  saveConversation,
  withId,
  withoutSupersededCard,
  withProposal,
  type ChatItem,
  type Conversation,
  type NewChatItem,
} from "@/features/copilot/conversation"
import { COPILOT_ERROR_CODES, type CopilotEvent, type ProposalOut } from "@/features/copilot/types"
import { ApiError } from "@/lib/api"

/** Whether the assistant is available and which face it has. Fetched when the panel first opens. */
export function useCopilotConfig({ enabled }: { enabled: boolean }) {
  return useQuery({
    queryKey: copilotKeys.config(),
    queryFn: ({ signal }) => fetchCopilotConfig(signal),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export type CopilotChat = {
  items: ChatItem[]
  /** A turn is streaming. */
  running: boolean
  /** The server refused the chat as unavailable since the conversation started. */
  unavailable: boolean
  send: (message: string) => void
  /** Sends the last message again, dropping what its failed turn left. */
  retry: () => void
  /** Ends the running turn, keeping what already arrived. */
  stop: () => void
  /** Starts a new conversation. */
  reset: () => void
}

function append(conversation: Conversation, item: NewChatItem): Conversation {
  return { ...conversation, items: [...conversation.items, withId(item)] }
}

function withoutStatus(conversation: Conversation): Conversation {
  return { ...conversation, items: conversation.items.filter((item) => item.kind !== "status") }
}

/**
 * One conversation with the Copilot, kept in the tab's session storage so it
 * survives page changes and reloads. Only one turn runs at a time.
 */
export function useCopilotChat(userId: string): CopilotChat {
  const queryClient = useQueryClient()
  const [conversation, setConversation] = useState(() => loadConversation(userId))
  const [running, setRunning] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  // The running turn. A turn that is no longer here was replaced by a new
  // conversation, so whatever it still receives is dropped.
  const turnRef = useRef<AbortController | null>(null)

  useEffect(() => {
    saveConversation(userId, conversation)
  }, [userId, conversation])

  // Leaving the signed-in pages ends the turn.
  useEffect(() => () => turnRef.current?.abort(), [])

  // A proposal card keeps its state in the query cache. Each new state is
  // written into the conversation too, so the stored card shows how it ended.
  useEffect(
    () =>
      queryClient.getQueryCache().subscribe((event) => {
        if (event.type !== "updated" || event.action.type !== "success") return
        if (!partialMatchKey(event.query.queryKey, copilotKeys.proposals())) return
        const proposal = event.query.state.data as ProposalOut
        setConversation((current) => withProposal(current, proposal))
      }),
    [queryClient],
  )

  async function runTurn(message: string, conversationId: string | null) {
    const turn = new AbortController()
    turnRef.current = turn
    setRunning(true)

    const update = (change: (current: Conversation) => Conversation) => {
      if (turnRef.current === turn) setConversation(change)
    }
    const add = (item: NewChatItem) => update((current) => append(current, item))

    const onEvent = (event: CopilotEvent) => {
      switch (event.event) {
        case "conversation":
          update((current) => ({ ...current, conversationId: event.data.conversation_id }))
          return
        case "status":
          add({ kind: "status", text: event.data.text })
          return
        case "result": {
          const { tool, display } = event.data
          update((current) => {
            const items = withoutSupersededCard(current.items, display)
            return append({ ...current, items }, { kind: "result", tool, display })
          })
          // The server has just made this proposal, so its card starts from it without reading it again.
          if (display.kind === "proposal") {
            queryClient.setQueryData(copilotKeys.proposal(display.proposal.id), display.proposal)
          }
          return
        }
        case "message":
          add({ kind: "assistant", text: event.data.text })
          return
        case "error":
          if (event.data.code === COPILOT_ERROR_CODES.unavailable) setUnavailable(true)
          else add({ kind: "error", code: event.data.code, message: event.data.message })
          return
        case "done":
          return
      }
    }

    try {
      const request = conversationId ? { conversation_id: conversationId, message } : { message }
      await streamCopilotChat(request, { signal: turn.signal, onEvent })
    } catch (error) {
      if (turn.signal.aborted) {
        add({ kind: "stopped" })
      } else if (!(error instanceof ApiError)) {
        add({ kind: "error", code: COPILOT_ERROR_CODES.failed, message: "Something went wrong." })
      } else if (error.status === 401) {
        // The session ended: the sign-in guard takes over.
        endSession(queryClient)
      } else if (error.code === COPILOT_ERROR_CODES.unavailable) {
        setUnavailable(true)
      } else if (error.status === 404) {
        // The server no longer has this conversation, so the next try starts a new one.
        update((current) => ({ ...current, conversationId: null }))
        add({
          kind: "error",
          code: error.code,
          message: "This conversation is no longer available. Try again to continue in a new one.",
        })
      } else {
        add({ kind: "error", code: error.code, message: error.message })
      }
    } finally {
      if (turnRef.current === turn) {
        turnRef.current = null
        setRunning(false)
        setConversation(withoutStatus)
      }
    }
  }

  function send(text: string) {
    const message = text.trim()
    // The ref, not `running`, so two quick sends in one render cannot both start.
    if (!message || turnRef.current || unavailable) return
    setConversation((current) => append(current, { kind: "user", text: message }))
    void runTurn(message, conversation.conversationId)
  }

  function retry() {
    const index = lastUserIndex(conversation.items)
    const last = conversation.items[index]
    if (turnRef.current || last?.kind !== "user") return
    setConversation((current) => ({
      ...current,
      items: current.items.slice(0, lastUserIndex(current.items) + 1),
    }))
    void runTurn(last.text, conversation.conversationId)
  }

  function stop() {
    turnRef.current?.abort()
  }

  function reset() {
    const turn = turnRef.current
    turnRef.current = null
    turn?.abort()
    setRunning(false)
    setUnavailable(false)
    setConversation(EMPTY_CONVERSATION)
  }

  return { items: conversation.items, running, unavailable, send, retry, stop, reset }
}
