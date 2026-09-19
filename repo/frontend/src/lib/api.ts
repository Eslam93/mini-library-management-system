/**
 * The one way the app talks to the backend.
 *
 * Requests go to the same origin and carry the session cookie. Any failure
 * becomes an ApiError, so callers handle one error type.
 */

const DEFAULT_TIMEOUT_MS = 15_000

/** Error codes the client sets itself when there is no usable server answer. */
export const CLIENT_ERROR_CODES = {
  network: "network_error",
  timeout: "timeout",
  http: "http_error",
  invalidResponse: "invalid_response",
} as const

type ApiErrorInit = {
  status: number
  code: string
  message: string
  details?: unknown
  requestId?: string
  cause?: unknown
}

export class ApiError extends Error {
  /** HTTP status, or 0 when no response arrived. */
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | undefined

  constructor({ status, code, message, details, requestId, cause }: ApiErrorInit) {
    super(message, { cause })
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

/** The body the backend sends with every error response. */
type ErrorEnvelope = {
  error: { code: string; message: string; details?: unknown }
  meta?: { request_id?: string }
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) return false
  const error = (value as { error: unknown }).error
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  )
}

const INVALID_JSON = Symbol("invalid-json")

/** Empty bodies (such as 204) parse to undefined. */
function parseJson(text: string): unknown {
  if (text === "") return undefined
  try {
    return JSON.parse(text)
  } catch {
    return INVALID_JSON
  }
}

export type ApiRequestOptions = Omit<RequestInit, "body"> & {
  /** Sent as JSON. */
  body?: unknown
  timeoutMs?: number
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { body, timeoutMs = DEFAULT_TIMEOUT_MS, headers, signal, ...init } = options

  const requestHeaders = new Headers(headers)
  requestHeaders.set("Accept", "application/json")
  if (body !== undefined) requestHeaders.set("Content-Type", "application/json")

  // One controller covers both the timeout and a cancel from the caller.
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const cancel = () => controller.abort()
  signal?.addEventListener("abort", cancel, { once: true })

  let response: Response
  let text: string
  try {
    response = await fetch(path, {
      ...init,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      signal: controller.signal,
    })
    text = await response.text()
  } catch (error) {
    if (timedOut) {
      throw new ApiError({
        status: 0,
        code: CLIENT_ERROR_CODES.timeout,
        message: "The server took too long to respond.",
        cause: error,
      })
    }
    // A cancel from the caller is not an error the user needs to see.
    if (signal?.aborted) throw error
    throw new ApiError({
      status: 0,
      code: CLIENT_ERROR_CODES.network,
      message: "Could not reach the server.",
      cause: error,
    })
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener("abort", cancel)
  }

  const payload = parseJson(text)

  if (response.ok) {
    if (payload === INVALID_JSON) {
      throw new ApiError({
        status: response.status,
        code: CLIENT_ERROR_CODES.invalidResponse,
        message: "The server sent a response the app could not read.",
        requestId: response.headers.get("x-request-id") ?? undefined,
      })
    }
    return payload as T
  }

  throw errorFromResponse(response, payload)
}

/** The ApiError for a refused request: the API's own error envelope when it sent one. */
export function errorFromResponse(response: Response, payload: unknown): ApiError {
  const headerRequestId = response.headers.get("x-request-id") ?? undefined
  if (isErrorEnvelope(payload)) {
    return new ApiError({
      status: response.status,
      code: payload.error.code,
      message: payload.error.message,
      details: payload.error.details,
      requestId: payload.meta?.request_id ?? headerRequestId,
    })
  }
  return new ApiError({
    status: response.status,
    code: CLIENT_ERROR_CODES.http,
    message: `The request failed with status ${response.status}.`,
    requestId: headerRequestId,
  })
}

/** A response body as JSON, or undefined when it is empty or not JSON. */
export async function readJsonBody(response: Response): Promise<unknown> {
  const payload = parseJson(await response.text())
  return payload === INVALID_JSON ? undefined : payload
}
