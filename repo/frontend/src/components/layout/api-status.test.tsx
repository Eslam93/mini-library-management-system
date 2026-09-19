import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ApiStatus } from "@/components/layout/api-status"
import { jsonResponse, renderWithProviders } from "@/test/render"

describe("ApiStatus", () => {
  it.each<[string, () => Promise<Response>, string]>([
    [
      "the API and its database are up",
      async () => jsonResponse({ status: "ok", checks: { database: "ok" } }),
      "API ok",
    ],
    [
      "the database is down",
      async () => jsonResponse({ status: "degraded", checks: { database: "unavailable" } }, 503),
      "database unavailable",
    ],
    [
      "the API cannot be reached",
      async () => {
        throw new TypeError("Failed to fetch")
      },
      "API unreachable",
    ],
    [
      "the dev proxy cannot reach the API",
      async () => new Response(null, { status: 502 }),
      "API unreachable",
    ],
  ])("shows the right label when %s", async (_case, respond, label) => {
    const fetchMock = vi.fn(respond)
    vi.stubGlobal("fetch", fetchMock)

    renderWithProviders(<ApiStatus />)

    expect(screen.getByRole("status")).toHaveTextContent("Checking API")
    expect(await screen.findByText(label)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything())
  })
})
