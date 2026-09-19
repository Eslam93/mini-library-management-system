import { describe, expect, it, vi } from "vitest"

import { ApiError, apiRequest } from "@/lib/api"
import { jsonResponse } from "@/test/render"

function stubFetch(implementation: typeof fetch) {
  const fetchMock = vi.fn(implementation)
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

async function captureError(promise: Promise<unknown>) {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error("Expected the request to fail.")
}

describe("apiRequest", () => {
  it("sends JSON with the session cookie and returns the parsed body", async () => {
    const fetchMock = stubFetch(async () => jsonResponse({ id: 1 }, 201))

    const result = await apiRequest<{ id: number }>("/api/books", {
      method: "POST",
      body: { title: "Dune" },
    })

    expect(result).toEqual({ id: 1 })
    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe("/api/books")
    expect(init?.method).toBe("POST")
    expect(init?.credentials).toBe("include")
    expect(init?.body).toBe(JSON.stringify({ title: "Dune" }))
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json")
  })

  it("returns undefined for an empty success body", async () => {
    stubFetch(async () => new Response(null, { status: 204 }))

    await expect(apiRequest("/api/loans/1", { method: "DELETE" })).resolves.toBeUndefined()
  })

  it("turns the error envelope into an ApiError", async () => {
    stubFetch(async () =>
      jsonResponse(
        {
          error: {
            code: "copy_unavailable",
            message: "This copy is already borrowed.",
            details: { copy: "CP-0001" },
          },
          meta: { request_id: "req-42" },
        },
        409,
      ),
    )

    const error = await captureError(apiRequest("/api/loans"))

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      code: "copy_unavailable",
      message: "This copy is already borrowed.",
      details: { copy: "CP-0001" },
      requestId: "req-42",
    })
  })

  it("reports a failure without the envelope as an HTTP error", async () => {
    stubFetch(
      async () => new Response("<html>Bad gateway</html>", {
        status: 502,
        headers: { "X-Request-ID": "req-7" },
      }),
    )

    const error = await captureError(apiRequest("/api/books"))

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 502, code: "http_error", requestId: "req-7" })
  })

  it("times out a request that gets no answer", async () => {
    stubFetch(
      (_path, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("The operation was aborted.", "AbortError")),
          )
        }),
    )

    const error = await captureError(apiRequest("/api/books", { timeoutMs: 20 }))

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 0, code: "timeout" })
  })

  it("reports a network failure", async () => {
    stubFetch(async () => {
      throw new TypeError("Failed to fetch")
    })

    const error = await captureError(apiRequest("/api/books"))

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 0, code: "network_error" })
  })

  it("passes a cancel from the caller through unchanged", async () => {
    stubFetch(
      (_path, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("The operation was aborted.", "AbortError")),
          )
        }),
    )
    const controller = new AbortController()

    const pending = captureError(apiRequest("/api/books", { signal: controller.signal }))
    controller.abort()
    const error = await pending

    expect(error).not.toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ name: "AbortError" })
  })
})
