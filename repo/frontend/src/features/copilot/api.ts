import { createEventParser, type RawEvent } from "@/features/copilot/event-stream"
import type {
  CopilotChatRequest,
  CopilotConfig,
  CopilotEvent,
  CopilotEventName,
  ProposalOut,
} from "@/features/copilot/types"
import { ApiError, apiRequest, CLIENT_ERROR_CODES, errorFromResponse, readJsonBody } from "@/lib/api"

export const copilotKeys = {
  all: ["copilot"] as const,
  config: () => [...copilotKeys.all, "config"] as const,
  proposals: () => [...copilotKeys.all, "proposal"] as const,
  proposal: (id: string) => [...copilotKeys.proposals(), id] as const,
}

export function fetchCopilotConfig(signal?: AbortSignal) {
  return apiRequest<CopilotConfig>("/api/copilot/config", { signal })
}

function proposalPath(id: string) {
  return `/api/copilot/proposals/${encodeURIComponent(id)}`
}

/** A proposal's current state. 404 not_found when it is unknown or another user's. */
export function fetchProposal(id: string, signal?: AbortSignal) {
  return apiRequest<ProposalOut>(proposalPath(id), { signal })
}

/**
 * Carries out the proposal. Answers with it confirmed and its loan set. A
 * proposal that can no longer go ahead is refused with 409: proposal_expired,
 * proposal_resolved, or the reason the Borrow or Return failed.
 */
export function confirmProposal(id: string) {
  return apiRequest<ProposalOut>(`${proposalPath(id)}/confirm`, { method: "POST" })
}

/** Drops the proposal. 409 proposal_expired or proposal_resolved when it is no longer pending. */
export function cancelProposal(id: string) {
  return apiRequest<void>(`${proposalPath(id)}/cancel`, { method: "POST" })
}

/**
 * How long the stream may stay silent before the turn counts as lost. The
 * server ends every turn well within this, with an error event if it must.
 */
const IDLE_TIMEOUT_MS = 60_000

const EVENT_NAMES: ReadonlySet<string> = new Set<CopilotEventName>([
  "conversation",
  "status",
  "result",
  "message",
  "error",
  "done",
])

function unreadableError() {
  return new ApiError({
    status: 200,
    code: CLIENT_ERROR_CODES.invalidResponse,
    message: "The server sent a response the app could not read.",
  })
}

/** A known event with its JSON data, or null for an event this app does not know. */
function toCopilotEvent({ event, data }: RawEvent): CopilotEvent | null {
  if (!EVENT_NAMES.has(event)) return null
  let payload: unknown
  try {
    payload = data === "" ? {} : JSON.parse(data)
  } catch {
    throw unreadableError()
  }
  if (typeof payload !== "object" || payload === null) throw unreadableError()
  return { event, data: payload } as CopilotEvent
}

type StreamChatOptions = {
  /** Aborting it stops the turn: the request and the reading both end. */
  signal: AbortSignal
  onEvent: (event: CopilotEvent) => void
  idleTimeoutMs?: number
}

/**
 * Sends one message and hands over the turn's events as they arrive. It
 * resolves once the turn ends (a `done` event, or an `error` event and the
 * end of the body).
 *
 * A refusal before the stream starts, such as 503 when the assistant is not
 * configured, throws the API's error. A lost connection, a stream that goes
 * silent, a body that ends mid-turn or an unreadable event throws an ApiError
 * too. Aborting `signal` throws the abort error, so the caller can tell a stop
 * from a failure.
 */
export async function streamCopilotChat(
  request: CopilotChatRequest,
  { signal, onEvent, idleTimeoutMs = IDLE_TIMEOUT_MS }: StreamChatOptions,
): Promise<void> {
  let response: Response
  try {
    response = await fetch("/api/copilot/chat", {
      method: "POST",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify(request),
      credentials: "include",
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError({
      status: 0,
      code: CLIENT_ERROR_CODES.network,
      message: "Could not reach the server.",
      cause: error,
    })
  }
  if (!response.ok) throw errorFromResponse(response, await readJsonBody(response))
  if (!response.body) throw unreadableError()

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let finished = false
  let sawError = false
  let timedOut = false
  let timer: ReturnType<typeof setTimeout> | undefined

  // Cancelling the reader ends a pending read, whatever the body's source.
  const stopReading = () => {
    reader.cancel().catch(() => undefined)
  }
  const restartTimer = () => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      timedOut = true
      stopReading()
    }, idleTimeoutMs)
  }

  const parser = createEventParser((raw) => {
    if (finished) return
    const event = toCopilotEvent(raw)
    if (!event) return
    if (event.event === "done") finished = true
    if (event.event === "error") sawError = true
    onEvent(event)
  })

  signal.addEventListener("abort", stopReading, { once: true })
  restartTimer()
  try {
    while (!finished) {
      const { done, value } = await reader.read()
      if (done) break
      restartTimer()
      parser.push(decoder.decode(value, { stream: true }))
    }
    if (!finished && !signal.aborted && !timedOut) {
      parser.push(decoder.decode())
      parser.end()
    }
  } catch (error) {
    if (signal.aborted || error instanceof ApiError) throw error
    throw new ApiError({
      status: 0,
      code: CLIENT_ERROR_CODES.network,
      message: "The connection to the server was lost.",
      cause: error,
    })
  } finally {
    clearTimeout(timer)
    signal.removeEventListener("abort", stopReading)
    stopReading()
  }

  if (signal.aborted) throw signal.reason
  if (timedOut) {
    throw new ApiError({
      status: 0,
      code: CLIENT_ERROR_CODES.timeout,
      message: "The assistant stopped responding.",
    })
  }
  if (!finished && !sawError) {
    throw new ApiError({
      status: 0,
      code: CLIENT_ERROR_CODES.network,
      message: "The answer was cut off before it finished.",
    })
  }
}
