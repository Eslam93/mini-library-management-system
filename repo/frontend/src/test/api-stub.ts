import { vi } from "vitest"

import { jsonResponse } from "@/test/render"

export type StubRequest = {
  method: string
  path: string
  search: URLSearchParams
  body: unknown
}

/** Returns a Response, or any other value to send as JSON with status 200. */
type StubHandler = (request: StubRequest) => unknown

/**
 * Replaces fetch with answers keyed by "METHOD /path", for example
 * "GET /api/books". A request with no matching key gets a 501, so a missing
 * stub fails the test visibly instead of hanging.
 */
export function stubApi(routes: Record<string, StubHandler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost")
    const method = (init?.method ?? "GET").toUpperCase()
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined
    const handler = routes[`${method} ${url.pathname}`]
    if (!handler) {
      return errorResponse(501, "no_stub", `No test stub for ${method} ${url.pathname}`)
    }
    const reply = await handler({ method, path: url.pathname, search: url.searchParams, body })
    return reply instanceof Response ? reply : jsonResponse(reply)
  })
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

/** A response in the API's error envelope. */
export function errorResponse(status: number, code: string, message: string, details: unknown = {}) {
  return jsonResponse({ error: { code, message, details }, meta: { request_id: "req-test" } }, status)
}

/** The requests the stub received, in order. */
export function requestsTo(fetchMock: ReturnType<typeof stubApi>, key: string): StubRequest[] {
  return fetchMock.mock.calls
    .map(([input, init]) => {
      const url = new URL(String(input), "http://localhost")
      const method = (init?.method ?? "GET").toUpperCase()
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined
      return { method, path: url.pathname, search: url.searchParams, body }
    })
    .filter((request) => `${request.method} ${request.path}` === key)
}
